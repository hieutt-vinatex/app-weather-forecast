"""Finite scheduled and manual notification jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import UUID

from pydantic import ValidationError

from app.cloud.contracts import (
    MANIFEST_KEY,
    TELEGRAM_JOB_STATUS_KEY,
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
    evaluate_snapshot_now,
    format_alert_message,
    format_immediate_report_message,
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


async def run_scheduled_notification(
    settings: Settings,
    store: JsonStore,
    *,
    clock: Clock,
) -> CloudNotificationResult:
    now = _now(settings, clock)
    running = JobRecord(
        kind="telegram",
        mode="scheduled",
        status="running",
        started_at=now,
    )
    await _persist_job(store, running)
    state = JsonNotificationStateStore(store)
    dispatcher = _build_dispatcher(settings, state)
    try:
        await dispatcher.start()
        result = await _run_scheduled(settings, store, state, dispatcher, now)
    except asyncio.CancelledError:
        await _persist_job(
            store,
            JobRecord(
                kind="telegram",
                mode="scheduled",
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
                mode="scheduled",
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
            mode="scheduled",
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


async def _run_scheduled(
    settings: Settings,
    store: JsonStore,
    state: NotificationStateProtocol,
    dispatcher: NotificationDispatcher,
    now: datetime,
) -> CloudNotificationResult:
    snapshot = await _load_snapshot(store)
    evaluation = evaluate_snapshot_now(
        snapshot,
        now=now,
        min_days=settings.notification_min_days,
        max_days=settings.notification_max_days,
    )
    reference_date = (
        evaluation.reference_date.isoformat()
        if evaluation.reference_date is not None
        else None
    )
    if evaluation.status in {"not_due", "waiting", "expired"}:
        return CloudNotificationResult(
            status=evaluation.status,
            mode="scheduled",
            reference_date=reference_date,
            reason=evaluation.reason,
        )
    if evaluation.event_key is None:
        raise NotificationDataError("evaluation event key is missing")
    event_key = (
        f"{evaluation.event_key}:"
        f"{settings.notification_min_days}-{settings.notification_max_days}"
    )
    if evaluation.status == "no_match":
        if not await state.is_no_match(event_key):
            await state.mark_no_match(event_key, now)
        return CloudNotificationResult(
            status="no_match",
            mode="scheduled",
            reference_date=reference_date,
        )

    targets = dispatcher.targets()
    if not targets:
        return CloudNotificationResult(
            status="not_configured",
            mode="scheduled",
            reference_date=reference_date,
            reason="no_notification_targets",
        )
    sent = await state.sent_targets(event_key)
    pending = [target for target in targets if target.key not in sent]
    if not pending:
        return CloudNotificationResult(
            status="already_delivered",
            mode="scheduled",
            reference_date=reference_date,
        )
    message = format_alert_message(
        evaluation,
        min_days=settings.notification_min_days,
        max_days=settings.notification_max_days,
    )
    if settings.notification_dry_run:
        return CloudNotificationResult(
            status="dry_run",
            mode="scheduled",
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
        mode="scheduled",
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
        max_days=settings.notification_max_days,
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
        max_days=settings.notification_max_days,
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


class NotificationDataError(RuntimeError):
    pass


async def _load_snapshot(store: JsonStore) -> SnapshotResponse:
    try:
        raw_manifest = await store.get_json(MANIFEST_KEY)
        manifest = PublicationManifest.model_validate(raw_manifest)
        key = manifest.snapshot_keys.get(90)
        if key is None:
            raise NotificationDataError("90-day snapshot key is missing")
        raw_snapshot = await store.get_json(key)
        return SnapshotResponse.model_validate(raw_snapshot)
    except NotificationDataError:
        raise
    except (ValidationError, TypeError, ValueError) as exc:
        raise StorageReadError("active notification snapshot is invalid") from exc


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
    if isinstance(exc, (NotificationDataError, StorageReadError)):
        return "invalid_snapshot"
    if exc.__class__.__module__.startswith("app.cloud"):
        return "cloud_storage_error"
    return "notification_failed"
