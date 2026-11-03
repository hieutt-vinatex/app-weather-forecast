"""Finite full and incremental snapshot jobs for scheduled cloud runners."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Sequence
from urllib.parse import urlparse
from uuid import UUID

from app.cloud.contracts import (
    DAILY_DATA_UPDATE_KEY,
    DATA_JOB_STATUS_KEY,
    MANIFEST_KEY,
    DailyDataUpdateState,
    JobRecord,
    JsonStore,
    OperationRecord,
    PublicationManifest,
    operation_key,
)
from app.cloud.publisher import SnapshotPublisher
from app.config import Settings
from app.services.gdb_service import DayOutcome, GdbService
from app.services.snapshot_builder import SnapshotBuildContext
from app.utils.date_helper import date_range
from app.utils.fetcher import Fetcher

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class DataJobResult:
    status: str
    mode: str
    version: str | None
    record_count: int
    reason: str | None = None


async def full_sync(
    settings: Settings,
    store: JsonStore,
    *,
    clock: Clock,
) -> DataJobResult:
    return await _sync(settings, store, mode="full", clock=clock)


async def incremental_sync(
    settings: Settings,
    store: JsonStore,
    *,
    clock: Clock,
) -> DataJobResult:
    return await _sync(settings, store, mode="incremental", clock=clock)


async def run_scheduled_data_job(
    settings: Settings,
    store: JsonStore,
    *,
    clock: Clock,
) -> DataJobResult:
    now = _now(settings, clock)
    if not _inside_scheduled_window(now):
        return DataJobResult(
            status="outside_window",
            mode="scheduled",
            version=None,
            record_count=0,
        )

    business_date = now.date()
    state = await _load_daily_state(store)
    manifest = await _load_manifest(store)
    if (
        manifest is not None
        and manifest.source_reference_date == business_date
    ):
        healed = _successful_daily_state(
            state,
            business_date=business_date,
            attempted_at=now,
            version=manifest.version,
            source_reference_date=manifest.source_reference_date,
            increment_attempt=False,
        )
        await _persist_daily_state(store, healed)
        return DataJobResult(
            status="already_succeeded",
            mode="scheduled",
            version=manifest.version,
            record_count=manifest.last_job.record_count,
        )

    if (
        state is not None
        and state.business_date == business_date
        and state.status == "succeeded"
    ):
        # A succeeded state without a matching manifest is not authoritative.
        # Continue with a new attempt so publication and state converge again.
        state = state.model_copy(
            update={
                "status": "failed",
                "last_reason": "publication_mismatch",
                "published_version": None,
                "source_reference_date": None,
                "initial_failure_at": state.initial_failure_at or now,
            }
        )

    pending = _pending_daily_state(
        state,
        business_date=business_date,
        attempted_at=now,
    )
    await _persist_daily_state(store, pending)
    frozen_clock = lambda: now
    try:
        result = await incremental_sync(settings, store, clock=frozen_clock)
    except asyncio.CancelledError:
        await _persist_daily_state(
            store,
            _failed_daily_state(pending, failed_at=now, reason="job_timeout"),
        )
        raise

    if result.status != "succeeded":
        await _persist_daily_state(
            store,
            _failed_daily_state(
                pending,
                failed_at=now,
                reason=result.reason or "job_failed",
            ),
        )
        return result

    published = await _load_manifest(store)
    if published is None or published.source_reference_date != business_date:
        failed = _failed_daily_state(
            pending,
            failed_at=now,
            reason="publication_mismatch",
        )
        await _persist_daily_state(store, failed)
        return DataJobResult(
            status="failed",
            mode=result.mode,
            version=None,
            record_count=0,
            reason="publication_mismatch",
        )

    succeeded = _successful_daily_state(
        pending,
        business_date=business_date,
        attempted_at=now,
        version=published.version,
        source_reference_date=published.source_reference_date,
        increment_attempt=False,
    )
    await _persist_daily_state(store, succeeded)
    return result


async def run_data_job(
    settings: Settings,
    store: JsonStore,
    *,
    mode: str,
    clock: Clock,
    request_id: str | None = None,
) -> DataJobResult:
    created_at = _now(settings, clock)
    normalized_request_id: str | None = None
    if request_id is not None:
        normalized_request_id = str(UUID(request_id))
        queued = OperationRecord(
            request_id=normalized_request_id,
            kind="data_refresh",
            status="queued",
            created_at=created_at,
            updated_at=created_at,
            message="Yêu cầu cập nhật dữ liệu đã được xếp hàng.",
        )
        await _persist_operation(settings, store, queued)
        await _persist_operation(
            settings,
            store,
            queued.model_copy(
                update={
                    "status": "running",
                    "updated_at": _now(settings, clock),
                    "message": "Đang cập nhật dữ liệu trên cloud.",
                }
            ),
        )

    try:
        if mode == "full":
            result = await full_sync(settings, store, clock=clock)
        elif mode == "incremental":
            result = await incremental_sync(settings, store, clock=clock)
        else:
            raise ValueError("mode must be full or incremental")
    except asyncio.CancelledError:
        if normalized_request_id is not None:
            await _persist_operation(
                settings,
                store,
                OperationRecord(
                    request_id=normalized_request_id,
                    kind="data_refresh",
                    status="failed",
                    created_at=created_at,
                    updated_at=_now(settings, clock),
                    message="Tác vụ cập nhật dữ liệu đã quá thời gian xử lý.",
                ),
            )
        raise

    if normalized_request_id is not None:
        succeeded = result.status in {"succeeded", "no_change"}
        terminal = OperationRecord(
            request_id=normalized_request_id,
            kind="data_refresh",
            status="succeeded" if succeeded else "failed",
            created_at=created_at,
            updated_at=_now(settings, clock),
            message=(
                "Dữ liệu cloud đã được cập nhật."
                if succeeded
                else "Không thể cập nhật dữ liệu; bản gần nhất vẫn được giữ."
            ),
        )
        await _persist_operation(settings, store, terminal)
    if result.status in {"succeeded", "no_change"}:
        await _record_manual_recovery(
            store,
            business_date=created_at.date(),
            attempted_at=created_at,
        )
    return result


async def _sync(
    settings: Settings,
    store: JsonStore,
    *,
    mode: str,
    clock: Clock,
) -> DataJobResult:
    started_at = _now(settings, clock)
    running = JobRecord(
        kind="data",
        mode=mode,
        status="running",
        started_at=started_at,
    )
    await _persist_job(store, running)
    try:
        publisher = _publisher(settings, store)
        active = await publisher.load_active_history()
        if mode == "full":
            refreshed = await _full_outcomes(settings, started_at.date())
            if not any(item.ok and item.result_count > 0 for item in refreshed):
                raise InvalidSourceDataError("no valid draw records")
            outcomes = _merge_preserving_quality(active, refreshed)
        else:
            if not active:
                mode = "full"
                refreshed = await _full_outcomes(settings, started_at.date())
                if not any(item.ok and item.result_count > 0 for item in refreshed):
                    raise InvalidSourceDataError("no valid draw records")
                outcomes = refreshed
            else:
                outcomes = await _incremental_outcomes(
                    settings, active, started_at.date()
                )

        if not any(item.ok and item.result_count > 0 for item in outcomes):
            raise InvalidSourceDataError("no valid draw records")
        finished_at = _now(settings, clock)
        completed_job = JobRecord(
            kind="data",
            mode=mode,
            status="succeeded",
            started_at=started_at,
            finished_at=finished_at,
            record_count=len(outcomes),
        )
        context = _build_context(settings, finished_at)
        manifest = await publisher.publish(outcomes, context, completed_job)
        terminal_job = manifest.last_job
        await _persist_job(store, terminal_job)
        return DataJobResult(
            status="succeeded",
            mode=mode,
            version=manifest.version,
            record_count=len(outcomes),
        )
    except asyncio.CancelledError:
        await _persist_job(
            store,
            JobRecord(
                kind="data",
                mode=mode,
                status="failed",
                started_at=started_at,
                finished_at=_now(settings, clock),
                reason="job_timeout",
            ),
        )
        raise
    except Exception as exc:
        failed_job = JobRecord(
            kind="data",
            mode=mode,
            status="failed",
            started_at=started_at,
            finished_at=_now(settings, clock),
            reason=_safe_reason(exc),
        )
        await _persist_job(store, failed_job)
        return DataJobResult(
            status="failed",
            mode=mode,
            version=None,
            record_count=0,
            reason=failed_job.reason,
        )


class InvalidSourceDataError(RuntimeError):
    pass


async def _full_outcomes(settings: Settings, end: date) -> list[DayOutcome]:
    days = date_range(90, settings.tzinfo, end=end)
    return await _fetch_outcomes(settings, days)


async def _incremental_outcomes(
    settings: Settings,
    active: Sequence[DayOutcome],
    today: date,
) -> list[DayOutcome]:
    refresh_days = [today - timedelta(days=1), today]
    refreshed = await _fetch_outcomes(settings, refresh_days)
    by_day = {item.day: item for item in active}
    refreshed_by_day = {item.day: item for item in refreshed}
    current = refreshed_by_day.get(today)
    if current is None or not current.ok or current.result_count == 0:
        raise InvalidSourceDataError("current draw is invalid")
    for item in refreshed:
        if item.ok and item.result_count > 0:
            previous = by_day.get(item.day)
            by_day[item.day] = _prefer_higher_quality(previous, item)
    wanted = date_range(90, settings.tzinfo, end=today)
    return [by_day[day] for day in wanted if day in by_day]


def _merge_preserving_quality(
    active: Sequence[DayOutcome], refreshed: Sequence[DayOutcome]
) -> list[DayOutcome]:
    active_by_day = {item.day: item for item in active}
    return [
        _prefer_higher_quality(active_by_day.get(item.day), item)
        for item in refreshed
    ]


def _prefer_higher_quality(
    previous: DayOutcome | None, refreshed: DayOutcome
) -> DayOutcome:
    if previous is None or not previous.ok or previous.result_count == 0:
        return refreshed
    if not refreshed.ok or refreshed.result_count == 0:
        return previous
    if previous.complete and not refreshed.complete:
        return previous
    if previous.result_count > refreshed.result_count:
        return previous
    return refreshed


async def _fetch_outcomes(
    settings: Settings,
    days: Sequence[date],
) -> list[DayOutcome]:
    fetcher = Fetcher(
        total_timeout=settings.source_timeout_seconds,
        connect_timeout=settings.source_connect_timeout_seconds,
        max_retries=settings.source_max_retries,
        max_concurrency=settings.source_max_concurrency,
    )
    await fetcher.start()
    try:
        service = GdbService(settings, fetcher)
        return list(
            await asyncio.gather(
                *(service.fetch_day(day, use_cache=False) for day in days)
            )
        )
    finally:
        await fetcher.close()


def _publisher(settings: Settings, store: JsonStore) -> SnapshotPublisher:
    return SnapshotPublisher(
        store,
        max_value_bytes=settings.publication_max_value_bytes,
    )


def _build_context(settings: Settings, now: datetime) -> SnapshotBuildContext:
    source = urlparse(settings.source_base_url).netloc or settings.source_base_url
    return SnapshotBuildContext(
        fetched_at=now,
        last_source_check_at=now,
        last_successful_check_at=now,
        last_changed_at=now,
        snapshot_version=int(now.timestamp()),
        source=source,
        cached=False,
    )


def _now(settings: Settings, clock: Clock) -> datetime:
    value = clock()
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(settings.tzinfo)


def _inside_scheduled_window(now: datetime) -> bool:
    return (now.hour, now.minute) >= (18, 30)


async def _load_daily_state(store: JsonStore) -> DailyDataUpdateState | None:
    raw = await store.get_json(DAILY_DATA_UPDATE_KEY)
    if raw is None:
        return None
    return DailyDataUpdateState.model_validate(raw)


async def _load_manifest(store: JsonStore) -> PublicationManifest | None:
    raw = await store.get_json(MANIFEST_KEY)
    if raw is None:
        return None
    return PublicationManifest.model_validate(raw)


def _pending_daily_state(
    previous: DailyDataUpdateState | None,
    *,
    business_date: date,
    attempted_at: datetime,
) -> DailyDataUpdateState:
    same_day = previous is not None and previous.business_date == business_date
    return DailyDataUpdateState(
        business_date=business_date,
        status="pending",
        attempt_count=(previous.attempt_count if same_day else 0) + 1,
        first_attempt_at=(
            previous.first_attempt_at if same_day else attempted_at
        ),
        last_attempt_at=attempted_at,
        initial_failure_at=(
            previous.initial_failure_at if same_day else None
        ),
        last_reason=previous.last_reason if same_day else None,
    )


def _failed_daily_state(
    pending: DailyDataUpdateState,
    *,
    failed_at: datetime,
    reason: str,
) -> DailyDataUpdateState:
    return DailyDataUpdateState(
        business_date=pending.business_date,
        status="failed",
        attempt_count=pending.attempt_count,
        first_attempt_at=pending.first_attempt_at,
        last_attempt_at=failed_at,
        initial_failure_at=pending.initial_failure_at or failed_at,
        last_reason=reason,
    )


def _successful_daily_state(
    previous: DailyDataUpdateState | None,
    *,
    business_date: date,
    attempted_at: datetime,
    version: str,
    source_reference_date: date,
    increment_attempt: bool,
) -> DailyDataUpdateState:
    same_day = previous is not None and previous.business_date == business_date
    prior_attempts = previous.attempt_count if same_day else 0
    return DailyDataUpdateState(
        business_date=business_date,
        status="succeeded",
        attempt_count=prior_attempts + (1 if increment_attempt else 0),
        first_attempt_at=(
            previous.first_attempt_at if same_day else attempted_at
        ),
        last_attempt_at=attempted_at,
        initial_failure_at=(
            previous.initial_failure_at if same_day else None
        ),
        published_version=version,
        source_reference_date=source_reference_date,
    )


async def _record_manual_recovery(
    store: JsonStore,
    *,
    business_date: date,
    attempted_at: datetime,
) -> None:
    manifest = await _load_manifest(store)
    if manifest is None or manifest.source_reference_date != business_date:
        return
    previous = await _load_daily_state(store)
    state = _successful_daily_state(
        previous,
        business_date=business_date,
        attempted_at=attempted_at,
        version=manifest.version,
        source_reference_date=manifest.source_reference_date,
        increment_attempt=True,
    )
    await _persist_daily_state(store, state)


async def _persist_daily_state(
    store: JsonStore,
    state: DailyDataUpdateState,
) -> None:
    await store.put_json(
        DAILY_DATA_UPDATE_KEY,
        state.model_dump(mode="json", by_alias=True),
    )


async def _persist_job(store: JsonStore, job: JobRecord) -> None:
    await store.put_json(
        DATA_JOB_STATUS_KEY,
        job.model_dump(mode="json", by_alias=True),
    )


async def _persist_operation(
    settings: Settings,
    store: JsonStore,
    operation: OperationRecord,
) -> None:
    await store.put_json(
        operation_key(operation.request_id),
        operation.model_dump(mode="json", by_alias=True),
        expiration_ttl=settings.publication_operation_ttl_seconds,
    )


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, InvalidSourceDataError):
        return "invalid_upstream_data"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "job_timeout"
    if exc.__class__.__module__.startswith("app.cloud"):
        return "cloud_storage_error"
    return "job_failed"
