"""Finite full and incremental snapshot jobs for scheduled cloud runners."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Sequence
from urllib.parse import urlparse
from uuid import UUID

from app.cloud.contracts import (
    DATA_JOB_STATUS_KEY,
    JobRecord,
    JsonStore,
    OperationRecord,
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
