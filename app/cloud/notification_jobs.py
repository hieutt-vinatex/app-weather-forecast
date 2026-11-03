"""Finite scheduled and manual notification jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable
from uuid import UUID

from pydantic import ValidationError

from app.cloud.contracts import (
    DAILY_DATA_UPDATE_KEY,
    MANIFEST_KEY,
    TELEGRAM_JOB_STATUS_KEY,
    DailyDataUpdateState,
    JobRecord,
    JsonStore,
    OperationRecord,
    PublicationManifest,
    operation_key,
)
from app.cloud.notification_store import JsonNotificationStateStore
from app.cloud.publisher import StorageReadError
from app.config import Settings
from app.notifications.channels import NotificationDispatcher
from app.notifications.models import (
    DailyUpdateWarning,
    evaluate_snapshot_now,
    format_daily_report_message,
    format_data_failure_message,
    format_immediate_report_message,
    format_no_data_daily_message,
)
from app.notifications.state_store import NotificationStateProtocol
from app.schemas.gdb import SnapshotResponse

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CloudNotificationResult:
    status: str
    mode: str
    reference_date: str | None = None
    delivered_count: int = 0
    failed_count: int = 0
    reason: str | None = None


async def run_daily_report(
    settings: Settings,
    store: JsonStore,
    *,
    clock: Clock,
) -> CloudNotificationResult:
    now = _now(settings, clock)
    if not (9 <= now.hour <= 12):
        return CloudNotificationResult(status="outside_window", mode="daily")
    return await _run_automatic_notification(
        settings,
        store,
        mode="daily",
        now=now,
        clock=clock,
        worker=lambda state, dispatcher: _run_daily(
            settings, store, state, dispatcher, now
        ),
    )


async def run_data_failure_notification(
    settings: Settings,
    store: JsonStore,
    *,
    clock: Clock,
) -> CloudNotificationResult:
    now = _now(settings, clock)
    return await _run_automatic_notification(
        settings,
        store,
        mode="data-failure",
        now=now,
        clock=clock,
        worker=lambda state, dispatcher: _run_data_failure(
            settings, store, state, dispatcher, now
        ),
    )


async def _run_automatic_notification(
    settings: Settings,
    store: JsonStore,
    *,
    mode: str,
    now: datetime,
    clock: Clock,
    worker: Callable[
        [NotificationStateProtocol, NotificationDispatcher],
        Awaitable[CloudNotificationResult],
    ],
) -> CloudNotificationResult:
    running = JobRecord(
        kind="telegram",
        mode=mode,
        status="running",
        started_at=now,
    )
    await _persist_job(store, running)
    state = JsonNotificationStateStore(store)
    dispatcher = _build_dispatcher(settings, state)
    try:
        await dispatcher.start()
        result = await worker(state, dispatcher)
    except asyncio.CancelledError:
        await _persist_job(
            store,
            JobRecord(
                kind="telegram",
                mode=mode,
                status="failed",
                started_at=now,
                finished_at=_now(settings, clock),
                reason="job_timeout",
            ),
        )
        raise
    except Exception as exc:
        await _persist_job(
            store,
            JobRecord(
                kind="telegram",
                mode=mode,
                status="failed",
                started_at=now,
                finished_at=_now(settings, clock),
                reason=_safe_reason(exc),
            ),
        )
        raise
    finally:
        await dispatcher.close()

    await _persist_job(
        store,
        JobRecord(
            kind="telegram",
            mode=mode,
            status=result.status,
            started_at=now,
            finished_at=_now(settings, clock),
            record_count=result.delivered_count,
            reason=result.reason,
        ),
    )
    return result


async def run_manual_notification(
    settings: Settings,
    store: JsonStore,
    request_id: str,
    *,
    clock: Clock,
) -> CloudNotificationResult:
    normalized_request_id = str(UUID(request_id))
    now = _now(settings, clock)
    existing = await store.get_json(operation_key(normalized_request_id))
    created_at = now
    if isinstance(existing, dict):
        try:
            created_at = OperationRecord.model_validate(existing).created_at
        except ValidationError:
            pass
    await _persist_operation(
        settings,
        store,
        OperationRecord(
            request_id=normalized_request_id,
            kind="telegram_send",
            status="running",
            created_at=created_at,
            updated_at=now,
            message="Đang tạo và gửi báo cáo Telegram trên cloud.",
        ),
    )
    await _persist_job(
        store,
        JobRecord(
            kind="telegram",
            mode="manual",
            status="running",
            started_at=now,
        ),
    )

    state = JsonNotificationStateStore(store)
    dispatcher = _build_dispatcher(settings, state)
    try:
        await dispatcher.start()
        result = await _run_manual(settings, store, dispatcher, now)
    except asyncio.CancelledError:
        await _persist_manual_failure(
            settings,
            store,
            normalized_request_id,
            created_at,
            now,
            _now(settings, clock),
            TimeoutError("notification job timed out"),
        )
        raise
    except Exception as exc:
        await _persist_manual_failure(
            settings,
            store,
            normalized_request_id,
            created_at,
            now,
            _now(settings, clock),
            exc,
        )
        raise
    finally:
        await dispatcher.close()

    succeeded = result.status in {"delivered", "dry_run"}
    await _persist_operation(
        settings,
        store,
        OperationRecord(
            request_id=normalized_request_id,
            kind="telegram_send",
            status="succeeded" if succeeded else "failed",
            created_at=created_at,
            updated_at=_now(settings, clock),
            message=(
                "Báo cáo Telegram đã được xử lý."
                if succeeded
                else "Không thể gửi đầy đủ báo cáo Telegram."
            ),
        ),
    )
    await _persist_job(
        store,
        JobRecord(
            kind="telegram",
            mode="manual",
            status=result.status,
            started_at=now,
            finished_at=_now(settings, clock),
            record_count=result.delivered_count,
            reason=result.reason,
        ),
    )
    return result


async def _run_daily(
    settings: Settings,
    store: JsonStore,
    state: NotificationStateProtocol,
    dispatcher: NotificationDispatcher,
    now: datetime,
) -> CloudNotificationResult:
    report_date = now.date()
    expected_date = report_date - timedelta(days=1)
    event_key = (
        f"daily-report:{report_date.isoformat()}:"
        f"{settings.notification_min_days}-plus"
    )
    daily_state = await _load_daily_state_optional(store)
    manifest, snapshot = await _load_snapshot_optional(store)
    fresh = (
        daily_state is not None
        and daily_state.business_date == expected_date
        and daily_state.status == "succeeded"
        and manifest is not None
        and manifest.source_reference_date == expected_date
    )
    warning: DailyUpdateWarning | None = None
    if not fresh:
        if daily_state is not None and daily_state.business_date == expected_date:
            attempt_count = daily_state.attempt_count
            reason = daily_state.last_reason or "publication_mismatch"
        else:
            attempt_count = 0
            reason = "update_state_missing"
        warning = DailyUpdateWarning(
            expected_date=expected_date,
            attempt_count=attempt_count,
            last_reason=reason,
        )

    if snapshot is None:
        message = format_no_data_daily_message(
            report_date=report_date,
            expected_date=expected_date,
            attempt_count=warning.attempt_count if warning is not None else 0,
            last_reason=(
                warning.last_reason if warning is not None else "publication_mismatch"
            ),
        )
        return await _deliver_event(
            settings,
            state,
            dispatcher,
            event_key=event_key,
            message=message,
            mode="daily",
            now=now,
            reference_date=None,
        )

    evaluation = evaluate_snapshot_now(
        snapshot,
        now=now,
        min_days=settings.notification_min_days,
    )
    if evaluation.status == "waiting" or evaluation.reference_date is None:
        message = format_no_data_daily_message(
            report_date=report_date,
            expected_date=expected_date,
            attempt_count=warning.attempt_count if warning is not None else 0,
            last_reason=(
                warning.last_reason if warning is not None else "publication_mismatch"
            ),
        )
        return await _deliver_event(
            settings,
            state,
            dispatcher,
            event_key=event_key,
            message=message,
            mode="daily",
            now=now,
            reference_date=None,
        )
    message = format_daily_report_message(
        evaluation,
        report_date=report_date,
        min_days=settings.notification_min_days,
        warning=warning,
    )
    return await _deliver_event(
        settings,
        state,
        dispatcher,
        event_key=event_key,
        message=message,
        mode="daily",
        now=now,
        reference_date=evaluation.reference_date.isoformat(),
    )


async def _run_data_failure(
    settings: Settings,
    store: JsonStore,
    state: NotificationStateProtocol,
    dispatcher: NotificationDispatcher,
    now: datetime,
) -> CloudNotificationResult:
    daily_state = await _load_daily_state_optional(store)
    eligible_dates = {now.date(), now.date() - timedelta(days=1)}
    if (
        daily_state is None
        or daily_state.status != "failed"
        or daily_state.initial_failure_at is None
        or daily_state.business_date not in eligible_dates
    ):
        return CloudNotificationResult(status="not_due", mode="data-failure")
    manifest = await _load_manifest_optional(store)
    latest_reference = manifest.source_reference_date if manifest is not None else None
    message = format_data_failure_message(
        daily_state,
        latest_reference_date=latest_reference,
    )
    return await _deliver_event(
        settings,
        state,
        dispatcher,
        event_key=f"data-update-failure:{daily_state.business_date.isoformat()}",
        message=message,
        mode="data-failure",
        now=now,
        reference_date=(
            latest_reference.isoformat() if latest_reference is not None else None
        ),
    )


async def _deliver_event(
    settings: Settings,
    state: NotificationStateProtocol,
    dispatcher: NotificationDispatcher,
    *,
    event_key: str,
    message: str,
    mode: str,
    now: datetime,
    reference_date: str | None,
) -> CloudNotificationResult:
    targets = dispatcher.targets()
    if not targets:
        return CloudNotificationResult(
            status="not_configured",
            mode=mode,
            reference_date=reference_date,
            reason="no_notification_targets",
        )
    sent = await state.sent_targets(event_key)
    pending = [target for target in targets if target.key not in sent]
    if not pending:
        return CloudNotificationResult(
            status="already_delivered",
            mode=mode,
            reference_date=reference_date,
        )
    if settings.notification_dry_run:
        return CloudNotificationResult(
            status="dry_run",
            mode=mode,
            reference_date=reference_date,
        )

    delivered = 0
    failed = 0
    for target in pending:
        result = await dispatcher.send(target, message)
        if result.success:
            await state.mark_sent(event_key, target.key, now)
            delivered += 1
        else:
            failed += 1
    return CloudNotificationResult(
        status="partial_failure" if failed else "delivered",
        mode=mode,
        reference_date=reference_date,
        delivered_count=delivered,
        failed_count=failed,
        reason="delivery_failed" if failed else None,
    )


async def _run_manual(
    settings: Settings,
    store: JsonStore,
    dispatcher: NotificationDispatcher,
    now: datetime,
) -> CloudNotificationResult:
    snapshot = await _load_snapshot(store)
    evaluation = evaluate_snapshot_now(
        snapshot,
        now=now,
        min_days=settings.notification_min_days,
    )
    reference_date = (
        evaluation.reference_date.isoformat()
        if evaluation.reference_date is not None
        else None
    )
    if evaluation.status == "waiting":
        return CloudNotificationResult(
            status="waiting",
            mode="manual",
            reference_date=reference_date,
            reason=evaluation.reason,
        )
    targets = dispatcher.targets()
    if not targets:
        return CloudNotificationResult(
            status="not_configured",
            mode="manual",
            reference_date=reference_date,
            reason="no_notification_targets",
        )
    message = format_immediate_report_message(
        evaluation,
        checked_at=now,
        min_days=settings.notification_min_days,
    )
    if settings.notification_dry_run:
        return CloudNotificationResult(
            status="dry_run",
            mode="manual",
            reference_date=reference_date,
        )

    delivered = 0
    failed = 0
    for target in targets:
        result = await dispatcher.send(target, message)
        if result.success:
            delivered += 1
        else:
            failed += 1
    return CloudNotificationResult(
        status="partial_failure" if failed else "delivered",
        mode="manual",
        reference_date=reference_date,
        delivered_count=delivered,
        failed_count=failed,
        reason="delivery_failed" if failed else None,
    )


async def _load_daily_state_optional(
    store: JsonStore,
) -> DailyDataUpdateState | None:
    raw = await store.get_json(DAILY_DATA_UPDATE_KEY)
    if raw is None:
        return None
    try:
        return DailyDataUpdateState.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        return None


async def _load_manifest_optional(
    store: JsonStore,
) -> PublicationManifest | None:
    raw = await store.get_json(MANIFEST_KEY)
    if raw is None:
        return None
    try:
        return PublicationManifest.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        return None


async def _load_snapshot_optional(
    store: JsonStore,
) -> tuple[PublicationManifest | None, SnapshotResponse | None]:
    manifest = await _load_manifest_optional(store)
    if manifest is None:
        return None, None
    key = manifest.snapshot_keys.get(90)
    if key is None:
        return manifest, None
    raw_snapshot = await store.get_json(key)
    try:
        return manifest, SnapshotResponse.model_validate(raw_snapshot)
    except (ValidationError, TypeError, ValueError):
        return manifest, None


async def _load_snapshot(store: JsonStore) -> SnapshotResponse:
    _, snapshot = await _load_snapshot_optional(store)
    if snapshot is None:
        raise StorageReadError("active notification snapshot is invalid")
    return snapshot


def _build_dispatcher(
    settings: Settings,
    state_store: NotificationStateProtocol,
) -> NotificationDispatcher:
    return NotificationDispatcher(
        settings,
        state_store,
        allowed_channels=frozenset({"telegram"}),
        target_key_secret=settings.require_notification_ledger_hmac_key(),
    )


def _now(settings: Settings, clock: Clock) -> datetime:
    value = clock()
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(settings.tzinfo)


async def _persist_job(store: JsonStore, job: JobRecord) -> None:
    await store.put_json(
        TELEGRAM_JOB_STATUS_KEY,
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


async def _persist_manual_failure(
    settings: Settings,
    store: JsonStore,
    request_id: str,
    created_at: datetime,
    started_at: datetime,
    finished_at: datetime,
    exc: Exception,
) -> None:
    await _persist_operation(
        settings,
        store,
        OperationRecord(
            request_id=request_id,
            kind="telegram_send",
            status="failed",
            created_at=created_at,
            updated_at=finished_at,
            message="Không thể xử lý báo cáo Telegram.",
        ),
    )
    await _persist_job(
        store,
        JobRecord(
            kind="telegram",
            mode="manual",
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            reason=_safe_reason(exc),
        ),
    )


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "job_timeout"
    if isinstance(exc, StorageReadError):
        return "invalid_snapshot"
    if exc.__class__.__module__.startswith("app.cloud"):
        return "cloud_storage_error"
    return "notification_failed"
