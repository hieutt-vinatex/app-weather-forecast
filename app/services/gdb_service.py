"""Data service: fetch, parse, cache and assemble full XSMB snapshots.

Responsibilities:

* Fetch + parse a single day, with per-day conditional-request validators.
* Cache historical (non-today) days in a TTL cache, protected by single-flight
  so concurrent misses hit the upstream only once.
* Assemble a :class:`SnapshotResponse` for a 30/60/90 day range, injecting the
  live "today" outcome supplied by the realtime poller so the snapshot always
  reflects the freshest state.

The service never fabricates a record: a day that cannot be parsed is reported
as a failure with a specific reason and contributes to ``missingDates``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from app.cache.simple_cache import SingleFlight, TTLCache
from app.config import Settings
from app.realtime.state import RealtimeState
from app.schemas.gdb import SnapshotResponse
from app.services.snapshot_builder import SnapshotBuildContext, assemble_snapshot
from app.utils.date_helper import (
    build_source_url,
    date_range,
    to_iso,
    today_in_tz,
)
from app.utils.fetcher import ConditionalHeaders, Fetcher, FetchStatus
from app.utils.parser import PRIZE_KEYS, ParseStatus, parse_gdb

logger = logging.getLogger("app.gdb_service")

# Human/machine-friendly failure reason codes.
REASON_NO_RESULT = "no_result"
REASON_TIMEOUT = "timeout"
REASON_NETWORK = "network_error"
REASON_HTTP = "http_error"
REASON_RATE_LIMITED = "rate_limited"
REASON_PARSE = "parse_failure"
REASON_INVALID = "invalid_data"


@dataclass
class DayOutcome:
    """Result of resolving one calendar day."""

    day: date
    source_url: str
    gdb: str | None = None
    prizes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    complete: bool = False
    ok: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        # Compatibility for callers/tests that still construct an outcome with
        # only the former two-digit ``gdb`` value.
        if self.gdb is not None and not self.prizes:
            self.prizes = {"db": (self.gdb,)}

    @property
    def date_iso(self) -> str:
        return to_iso(self.day)

    @property
    def result_count(self) -> int:
        return sum(len(values) for values in self.prizes.values())

    @property
    def signature(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Stable business signature used by the realtime change detector."""
        return tuple((prize, self.prizes.get(prize, ())) for prize in PRIZE_KEYS)


class GdbService:
    def __init__(self, settings: Settings, fetcher: Fetcher) -> None:
        self._settings = settings
        self._fetcher = fetcher
        self._tz = settings.tzinfo
        self._history_cache: TTLCache[str, DayOutcome] = TTLCache(
            ttl_seconds=settings.history_cache_ttl_seconds
        )
        self._conditional: dict[str, ConditionalHeaders] = {}
        self._single_flight: SingleFlight[str, DayOutcome] = SingleFlight()

    # ------------------------------------------------------------------ #
    # Single-day resolution
    # ------------------------------------------------------------------ #
    async def fetch_day(self, day: date, *, use_cache: bool = True) -> DayOutcome:
        """Resolve a single day, optionally serving from the history cache."""
        key = to_iso(day)
        if use_cache:
            cached = self._history_cache.get_fresh(key)
            if cached is not None:
                return cached
            return await self._single_flight.do(key, lambda: self._load_and_cache(day))
        return await self._load_day(day)

    async def _load_and_cache(self, day: date) -> DayOutcome:
        outcome = await self._load_day(day)
        # Cache only a complete board. A live, partially published draw must be
        # fetched again so newly arriving prize values are not hidden by TTL.
        if outcome.ok and outcome.complete:
            self._history_cache.set(to_iso(day), outcome)
        return outcome

    async def _load_day(self, day: date) -> DayOutcome:
        url = build_source_url(self._settings.source_base_url, day)
        key = to_iso(day)
        conditional = self._conditional.get(key)
        result = await self._fetcher.fetch(url, conditional=conditional)

        if result.status is FetchStatus.NOT_MODIFIED:
            stale = self._history_cache.get_stale(key)
            if stale is not None:
                return stale
            # 304 but we have nothing cached: refetch unconditionally once.
            result = await self._fetcher.fetch(url)

        # Persist validators for future conditional requests.
        if result.etag or result.last_modified:
            self._conditional[key] = ConditionalHeaders(result.etag, result.last_modified)

        if result.status is FetchStatus.OK and result.body is not None:
            return self._parse_body(day, url, result.body)

        reason = _map_failure(result.status)
        logger.info(
            "day fetch failed date=%s status=%s reason=%s attempts=%d",
            key, result.status.value, reason, result.attempts,
        )
        return DayOutcome(day=day, source_url=url, ok=False, reason=reason)

    def _parse_body(self, day: date, url: str, body: str) -> DayOutcome:
        parsed = parse_gdb(body)
        if parsed.ok:
            return DayOutcome(
                day=day,
                source_url=url,
                gdb=parsed.gdb,
                prizes=parsed.prizes,
                complete=parsed.complete,
                ok=True,
            )
        reason = (
            REASON_NO_RESULT
            if parsed.status is ParseStatus.MISSING_SELECTOR
            else REASON_PARSE
        )
        logger.info("parse failed date=%s status=%s", to_iso(day), parsed.status.value)
        return DayOutcome(day=day, source_url=url, ok=False, reason=reason)

    # ------------------------------------------------------------------ #
    # Snapshot assembly
    # ------------------------------------------------------------------ #
    async def build_snapshot(
        self,
        days: int,
        state: RealtimeState,
        *,
        today_outcome: DayOutcome | None = None,
    ) -> SnapshotResponse:
        """Assemble a full snapshot for an N-day range.

        ``today_outcome`` (from the poller) overrides the cache for the current
        day so the snapshot reflects live state. Other days come from cache /
        single-flight fetches run concurrently.
        """
        today = today_in_tz(self._tz)
        wanted = date_range(days, self._tz, end=today)

        async def resolve(day: date) -> DayOutcome:
            if day == today and today_outcome is not None and today_outcome.day == today:
                return today_outcome
            return await self.fetch_day(day)

        outcomes = await asyncio.gather(*(resolve(d) for d in wanted))
        return self._assemble(days, outcomes, state)

    def _assemble(
        self, days: int, outcomes: list[DayOutcome], state: RealtimeState
    ) -> SnapshotResponse:
        context = SnapshotBuildContext(
            fetched_at=datetime.now(self._tz),
            last_source_check_at=state.last_source_check_at,
            last_successful_check_at=state.last_successful_check_at,
            last_changed_at=state.last_changed_at,
            snapshot_version=state.snapshot_version,
            source=_source_host(self._settings.source_base_url),
            poll_interval_seconds=state.poll_interval_seconds,
            realtime_enabled=state.realtime_enabled,
            cached=len(self._history_cache) > 0,
        )
        return assemble_snapshot(days, outcomes, context)

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def history_cache_entries(self) -> int:
        return len(self._history_cache)

    def clear_today_cache(self, day: date) -> None:
        self._history_cache.invalidate(to_iso(day))


def _map_failure(status: FetchStatus) -> str:
    return {
        FetchStatus.NOT_FOUND: REASON_NO_RESULT,
        FetchStatus.TIMEOUT: REASON_TIMEOUT,
        FetchStatus.NETWORK_ERROR: REASON_NETWORK,
        FetchStatus.HTTP_ERROR: REASON_HTTP,
        FetchStatus.RATE_LIMITED: REASON_RATE_LIMITED,
    }.get(status, REASON_INVALID)


def _source_host(base_url: str) -> str:
    return base_url.replace("https://", "").replace("http://", "").rstrip("/")
