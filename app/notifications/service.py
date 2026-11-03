"""Scheduler and orchestration for absence notifications."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import Settings
from app.notifications.channels import DeliveryResult, NotificationDispatcher
from app.notifications.models import (
    AbsenceCandidate,
    evaluate_snapshot,
    evaluate_snapshot_now,
    format_alert_message,
    format_immediate_report_message,
)
from app.notifications.state_store import NotificationStateStore
from app.services.realtime_service import RealtimeService, RefreshCooldownError
from app.utils.date_helper import now_in_tz

logger = logging.getLogger("app.notifications")


@dataclass(frozen=True)
class ImmediateNotificationOutcome:
    status: str
    checked_at: datetime
    reference_date: str | None = None
    candidates: tuple[AbsenceCandidate, ...] = ()
    deliveries: tuple[DeliveryResult, ...] = ()
    reason: str | None = None


class NotificationService:
    def __init__(
        self,
        settings: Settings,
        realtime: RealtimeService,
        *,
        state_store: NotificationStateStore | None = None,
        dispatcher: NotificationDispatcher | None = None,
        clock=None,
    ) -> None:
        self._settings = settings
        self._realtime = realtime
        self._clock = clock or (lambda: now_in_tz(settings.tzinfo))
        self._state_store = state_store or NotificationStateStore(
            settings.notification_state_path
        )
        self._dispatcher = dispatcher or NotificationDispatcher(
            settings, self._state_store
        )
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._run_lock = asyncio.Lock()
        self._send_now_lock = asyncio.Lock()
        self._dry_run_events: set[str] = set()
        self._next_retry_at: datetime | None = None

        self.last_check_at: datetime | None = None
        self.last_delivery_at: datetime | None = None
        self.last_reference_date: str | None = None
        self.last_error: str | None = None
        self.last_status: str = "disabled"

    async def start(self) -> None:
        if not self._settings.notifications_enabled:
            logger.info("Server-side notifications disabled")
            return
        await self._dispatcher.start()
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._run_loop(), name="absence-notification-scheduler"
        )
        self.last_status = "starting"
        logger.info(
            "Notification scheduler started time=%s threshold=%d-plus dry_run=%s targets=%d",
            self._settings.notification_send_time,
            self._settings.notification_min_days,
            self._settings.notification_dry_run,
            len(self._dispatcher.targets()),
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._dispatcher.close()
        logger.info("Notification scheduler stopped")

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep scheduler alive
                self.last_error = f"scheduler:{type(exc).__name__}"
                self.last_status = "error"
                logger.exception("Notification scheduler iteration failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._settings.notification_check_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    async def run_once(self) -> list[DeliveryResult]:
        """Evaluate and deliver one due event. Safe to call concurrently."""
        if not self._settings.notifications_enabled:
            self.last_status = "disabled"
            return []

        async with self._run_lock:
            now = self._clock()
            self.last_check_at = now
            if self._next_retry_at is not None and now < self._next_retry_at:
                self.last_status = "retry_wait"
                return []

            targets = self._dispatcher.targets()
            if not targets:
                self.last_status = "not_configured"
                self.last_error = "Không có kênh nhận nào được cấu hình."
                return []

            snapshot = await self._realtime.get_snapshot(90)
            evaluation = evaluate_snapshot(
                snapshot,
                now=now,
                min_days=self._settings.notification_min_days,
                send_time=self._settings.notification_send_time_value,
            )
            self.last_reference_date = (
                evaluation.reference_date.isoformat()
                if evaluation.reference_date is not None
                else None
            )
            self.last_status = evaluation.status

            if evaluation.status in {"not_due", "waiting", "expired"}:
                self.last_error = evaluation.reason
                return []

            assert evaluation.event_key is not None
            event_key = (
                f"{evaluation.event_key}:"
                f"{self._settings.notification_min_days}-plus"
            )

            sent_targets = await self._state_store.sent_targets(event_key)
            pending = [target for target in targets if target.key not in sent_targets]
            if not pending:
                self.last_status = "delivered"
                self.last_error = None
                return []

            message = format_alert_message(
                evaluation,
                min_days=self._settings.notification_min_days,
            )

            if self._settings.notification_dry_run:
                if event_key not in self._dry_run_events:
                    logger.info(
                        "Notification dry-run event=%s targets=%d message=%r",
                        event_key,
                        len(pending),
                        message,
                    )
                    self._dry_run_events.add(event_key)
                self.last_status = "dry_run"
                self.last_error = None
                return []

            results = await asyncio.gather(
                *(self._dispatcher.send(target, message) for target in pending)
            )
            failures: list[str] = []
            for result in results:
                if result.success:
                    await self._state_store.mark_sent(event_key, result.target.key, now)
                    self.last_delivery_at = now
                    logger.info(
                        "Notification delivered event=%s channel=%s target=%s",
                        event_key,
                        result.target.channel,
                        result.target.display,
                    )
                else:
                    failures.append(
                        f"{result.target.channel}/{result.target.display}:"
                        f"{result.error or 'unknown'}"
                    )
                    logger.warning(
                        "Notification delivery failed event=%s channel=%s target=%s error=%s",
                        event_key,
                        result.target.channel,
                        result.target.display,
                        result.error,
                    )

            if failures:
                self.last_status = "partial_failure"
                self.last_error = "; ".join(failures)[:500]
                self._next_retry_at = now + timedelta(
                    seconds=self._settings.notification_retry_interval_seconds
                )
            else:
                self.last_status = "delivered"
                self.last_error = None
                self._next_retry_at = None
            return list(results)

    async def send_test(self) -> list[DeliveryResult]:
        now = self._clock()
        targets = self._dispatcher.targets()
        if self._settings.notification_dry_run:
            return [
                DeliveryResult(
                    target=target,
                    success=True,
                    provider_id="dry-run",
                )
                for target in targets
            ]
        message = (
            "🧪 Kiểm tra thông báo XSMB\n"
            f"Thời gian: {now.strftime('%d/%m/%Y %H:%M:%S')}\n"
            "Kết nối kênh thông báo đang hoạt động."
        )
        return list(
            await asyncio.gather(
                *(self._dispatcher.send(target, message) for target in targets)
            )
        )

    async def send_now(self) -> ImmediateNotificationOutcome:
        """Refresh, evaluate and send an absence report immediately.

        Manual sends deliberately do not use the scheduler idempotency store:
        each authenticated click is an explicit request for a new report.
        """
        async with self._send_now_lock:
            now = self._clock()
            self.last_check_at = now
            targets = self._dispatcher.targets()
            if not targets:
                self.last_status = "not_configured"
                self.last_error = "Không có kênh nhận nào được cấu hình."
                return ImmediateNotificationOutcome(
                    status="not_configured",
                    checked_at=now,
                    reason=self.last_error,
                )

            # Ask the central poller to check today's source at click time. A
            # concurrent/recent manual refresh may be in cooldown; its latest
            # shared state is still safe to use for the report.
            try:
                await self._realtime.manual_refresh()
            except RefreshCooldownError:
                pass
            except Exception as exc:  # noqa: BLE001 - fall back to latest snapshot
                logger.warning(
                    "Immediate notification refresh failed type=%s",
                    type(exc).__name__,
                )

            snapshot = await self._realtime.get_snapshot(90)
            evaluation = evaluate_snapshot_now(
                snapshot,
                now=now,
                min_days=self._settings.notification_min_days,
            )
            reference_date = (
                evaluation.reference_date.isoformat()
                if evaluation.reference_date is not None
                else None
            )
            self.last_reference_date = reference_date

            if evaluation.status == "waiting":
                self.last_status = "manual_waiting"
                self.last_error = evaluation.reason
                return ImmediateNotificationOutcome(
                    status="waiting",
                    checked_at=now,
                    reference_date=reference_date,
                    reason=evaluation.reason,
                )

            message = format_immediate_report_message(
                evaluation,
                checked_at=now,
                min_days=self._settings.notification_min_days,
            )
            if self._settings.notification_dry_run:
                deliveries = tuple(
                    DeliveryResult(
                        target=target,
                        success=True,
                        provider_id="dry-run",
                    )
                    for target in targets
                )
                self.last_status = "manual_dry_run"
                self.last_error = None
                return ImmediateNotificationOutcome(
                    status="dry_run",
                    checked_at=now,
                    reference_date=reference_date,
                    candidates=evaluation.candidates,
                    deliveries=deliveries,
                )

            deliveries = tuple(
                await asyncio.gather(
                    *(self._dispatcher.send(target, message) for target in targets)
                )
            )
            failures = [result for result in deliveries if not result.success]
            if failures:
                self.last_status = "manual_partial_failure"
                self.last_error = "; ".join(
                    f"{result.target.channel}/{result.target.display}:"
                    f"{result.error or 'unknown'}"
                    for result in failures
                )[:500]
                status = "partial_failure"
            else:
                self.last_status = "manual_delivered"
                self.last_delivery_at = now
                self.last_error = None
                status = "delivered"

            return ImmediateNotificationOutcome(
                status=status,
                checked_at=now,
                reference_date=reference_date,
                candidates=evaluation.candidates,
                deliveries=deliveries,
                reason=self.last_error,
            )

    def status(self) -> dict:
        targets = self._dispatcher.targets()
        return {
            "enabled": self._settings.notifications_enabled,
            "running": self._task is not None and not self._task.done(),
            "dryRun": self._settings.notification_dry_run,
            "sendTime": self._settings.notification_send_time,
            "timezone": self._settings.realtime_timezone,
            "minDays": self._settings.notification_min_days,
            "maxDays": None,
            "threshold": f"{self._settings.notification_min_days}-plus",
            "configuredChannels": sorted({target.channel for target in targets}),
            "configuredTargetCount": len(targets),
            "lastStatus": self.last_status,
            "lastCheckAt": self._iso(self.last_check_at),
            "lastDeliveryAt": self._iso(self.last_delivery_at),
            "lastReferenceDate": self.last_reference_date,
            "lastError": self.last_error,
        }

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None
