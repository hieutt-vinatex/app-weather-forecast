"""Tests for alert evaluation, idempotency and channel orchestration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.notification_router import router as notification_router
from app.notifications.channels import DeliveryResult, NotificationTarget
from app.notifications.channels import NotificationDispatcher
from app.notifications.models import (
    evaluate_snapshot,
    evaluate_snapshot_now,
    format_alert_message,
    format_immediate_report_message,
)
from app.notifications.service import NotificationService
from app.notifications.state_store import NotificationStateStore
from app.realtime.state import RealtimeState
from app.services.gdb_service import DayOutcome, GdbService
from app.utils.parser import PRIZE_COUNTS, PRIZE_KEYS
from tests.conftest import FakeFetcher, make_settings, status_result
from app.utils.fetcher import FetchStatus


TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _snapshot(*, incomplete_offset: int | None = None):
    settings = make_settings()
    gdb = GdbService(
        settings,
        FakeFetcher(lambda url, cond: status_result(FetchStatus.TIMEOUT)),
    )
    reference = date(2026, 10, 14)
    outcomes = []
    for offset in range(89, -1, -1):
        day = reference - timedelta(days=offset)
        prizes = {
            prize: tuple("00" for _ in range(PRIZE_COUNTS[prize]))
            for prize in PRIZE_KEYS
        }
        if offset == 19:
            prizes["db"] = ("19",)
        outcomes.append(
            DayOutcome(
                day=day,
                source_url=f"https://example.test/{day.isoformat()}",
                gdb=prizes["db"][0],
                prizes=prizes,
                complete=offset != incomplete_offset,
                ok=True,
            )
        )
    state = RealtimeState(poll_interval_seconds=30.0, realtime_enabled=True)
    return gdb._assemble(90, outcomes, state), reference


def test_evaluate_snapshot_finds_exact_absence_and_due_time():
    snapshot, reference = _snapshot()
    evaluation = evaluate_snapshot(
        snapshot,
        now=datetime(2026, 10, 15, 9, 1, tzinfo=TZ),
        min_days=19,
        max_days=25,
        send_time=datetime.strptime("09:00", "%H:%M").time(),
    )

    assert evaluation.status == "ready"
    assert evaluation.reference_date == reference
    assert [(item.number, item.days_absent) for item in evaluation.candidates] == [
        ("19", 19)
    ]
    message = format_alert_message(evaluation, min_days=19, max_days=25)
    assert "19 ngày: 19" in message
    assert "14/10/2026" in message


def test_evaluate_snapshot_waits_when_required_history_is_incomplete():
    snapshot, _ = _snapshot(incomplete_offset=10)
    evaluation = evaluate_snapshot(
        snapshot,
        now=datetime(2026, 10, 15, 9, 1, tzinfo=TZ),
        min_days=19,
        max_days=25,
        send_time=datetime.strptime("09:00", "%H:%M").time(),
    )

    assert evaluation.status == "waiting"
    assert evaluation.reason is not None
    assert evaluation.reason.startswith("incomplete_coverage")


def test_evaluate_snapshot_now_ignores_schedule_and_formats_report():
    snapshot, reference = _snapshot()
    checked_at = datetime(2026, 10, 20, 14, 30, tzinfo=TZ)
    evaluation = evaluate_snapshot_now(
        snapshot,
        now=checked_at,
        min_days=19,
        max_days=25,
    )

    assert evaluation.status == "ready"
    assert evaluation.reference_date == reference
    assert [(item.number, item.days_absent) for item in evaluation.candidates] == [
        ("19", 19)
    ]
    message = format_immediate_report_message(
        evaluation,
        checked_at=checked_at,
        min_days=19,
        max_days=25,
    )
    assert "19 ngày: 19" in message
    assert "Kiểm tra lúc: 20/10/2026 14:30:00" in message


async def test_state_store_persists_sent_targets(tmp_path):
    path = tmp_path / "notification-state.json"
    first = NotificationStateStore(str(path))
    now = datetime(2026, 10, 15, 9, 1, tzinfo=TZ)
    await first.mark_sent("2026-10-14:19-25", "telegram:one", now)

    second = NotificationStateStore(str(path))
    assert await second.sent_targets("2026-10-14:19-25") == {"telegram:one"}


def test_dispatcher_discovers_configured_destinations(tmp_path):
    settings = make_settings(
        telegram_bot_token="telegram-secret",
        telegram_chat_ids="123,123,456",
        zalo_access_token="zalo-secret",
        zalo_recipient_ids="zalo-user",
        facebook_page_access_token="facebook-secret",
        facebook_page_id="page-1",
        facebook_messenger_recipient_ids="psid-1",
        facebook_publish_to_page=True,
    )
    dispatcher = NotificationDispatcher(
        settings, NotificationStateStore(str(tmp_path / "state.json"))
    )

    targets = dispatcher.targets()
    assert [(target.channel, target.kind) for target in targets] == [
        ("telegram", "chat"),
        ("telegram", "chat"),
        ("zalo", "oa_user"),
        ("facebook", "messenger"),
        ("facebook", "page_feed"),
    ]
    assert all("secret" not in target.display for target in targets)


def test_dispatcher_hmac_target_identifier_changes_with_secret(tmp_path):
    settings = make_settings(
        telegram_bot_token="telegram-secret",
        telegram_chat_ids="123456789",
    )
    state = NotificationStateStore(str(tmp_path / "state.json"))
    first = NotificationDispatcher(
        settings,
        state,
        allowed_channels=frozenset({"telegram"}),
        target_key_secret="ledger-secret",
    ).targets()[0]
    second = NotificationDispatcher(
        settings,
        state,
        allowed_channels=frozenset({"telegram"}),
        target_key_secret="different-secret",
    ).targets()[0]

    assert first.key == (
        "telegram:chat:"
        "a22a051196d83c49225db05dc40fdad69b501b2c29301214805246eaebc7d78d"
    )
    assert second.key != first.key
    assert "123456789" not in first.key
    assert "6789" not in first.key


async def test_zalo_can_bootstrap_access_token_from_refresh_token(
    tmp_path, monkeypatch
):
    settings = make_settings(
        zalo_refresh_token="refresh-token",
        zalo_app_id="app-id",
        zalo_app_secret="app-secret",
        zalo_recipient_ids="zalo-user",
    )
    dispatcher = NotificationDispatcher(
        settings, NotificationStateStore(str(tmp_path / "state.json"))
    )

    async def fake_refresh(stale_access_token):
        assert stale_access_token == ""
        return "new-access-token"

    monkeypatch.setattr(dispatcher, "_refresh_zalo_token", fake_refresh)
    assert await dispatcher._get_zalo_access_token() == "new-access-token"


class _FakeRealtime:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0

    async def get_snapshot(self, days):
        assert days == 90
        self.calls += 1
        return self.snapshot

    async def manual_refresh(self):
        return False, 1


class _FakeDispatcher:
    def __init__(self):
        self.target = NotificationTarget(
            key="telegram:chat:test",
            channel="telegram",
            kind="chat",
            recipient="1234",
            display="chat:…1234",
        )
        self.sent = []

    async def start(self):
        pass

    async def close(self):
        pass

    def targets(self):
        return [self.target]

    async def send(self, target, message):
        self.sent.append((target, message))
        return DeliveryResult(target=target, success=True, provider_id="1")


async def test_notification_service_does_not_send_same_event_twice(tmp_path):
    snapshot, _ = _snapshot()
    settings = make_settings(
        notifications_enabled=True,
        notification_dry_run=False,
        notification_state_path=str(tmp_path / "state.json"),
        notification_min_days=19,
        notification_max_days=25,
    )
    dispatcher = _FakeDispatcher()
    realtime = _FakeRealtime(snapshot)
    fixed_now = datetime(2026, 10, 15, 9, 1, tzinfo=TZ)
    service = NotificationService(
        settings,
        realtime,
        dispatcher=dispatcher,
        clock=lambda: fixed_now,
    )

    first = await service.run_once()
    second = await service.run_once()

    assert len(first) == 1
    assert second == []
    assert len(dispatcher.sent) == 1
    assert service.last_status == "delivered"


async def test_immediate_notification_sends_on_every_explicit_click(tmp_path):
    snapshot, _ = _snapshot()
    settings = make_settings(
        notifications_enabled=True,
        notification_dry_run=False,
        notification_state_path=str(tmp_path / "state.json"),
        notification_min_days=19,
        notification_max_days=25,
    )
    dispatcher = _FakeDispatcher()
    service = NotificationService(
        settings,
        _FakeRealtime(snapshot),
        dispatcher=dispatcher,
        clock=lambda: datetime(2026, 10, 20, 14, 30, tzinfo=TZ),
    )

    first = await service.send_now()
    second = await service.send_now()

    assert first.status == "delivered"
    assert first.reference_date == "2026-10-14"
    assert [(item.number, item.days_absent) for item in first.candidates] == [
        ("19", 19)
    ]
    assert second.status == "delivered"
    assert len(dispatcher.sent) == 2
    assert all("Kiểm tra lúc: 20/10/2026 14:30:00" in item[1] for item in dispatcher.sent)


def test_notification_operational_endpoints_are_protected(tmp_path):
    snapshot, _ = _snapshot()
    settings = make_settings(
        notification_admin_token="admin-secret",
        notification_dry_run=True,
        telegram_bot_token="telegram-secret",
        telegram_chat_ids="1234",
    )
    service = NotificationService(
        settings,
        _FakeRealtime(snapshot),
        dispatcher=_FakeDispatcher(),
        clock=lambda: datetime(2026, 10, 15, 9, 1, tzinfo=TZ),
    )
    app = FastAPI()
    app.include_router(notification_router)
    app.state.settings = settings
    app.state.notifications = service
    client = TestClient(app)

    status = client.get("/api/notifications/status")
    assert status.status_code == 200
    assert "admin-secret" not in status.text

    denied = client.post("/api/notifications/test")
    assert denied.status_code == 401

    sent = client.post(
        "/api/notifications/test",
        headers={"X-Notification-Token": "admin-secret"},
    )
    assert sent.status_code == 200
    assert sent.json()["dryRun"] is True
    assert sent.json()["success"] is True

    send_now_denied = client.post("/api/notifications/send-now")
    assert send_now_denied.status_code == 401

    send_now = client.post(
        "/api/notifications/send-now",
        headers={"X-Notification-Token": "admin-secret"},
    )
    assert send_now.status_code == 200
    assert send_now.json()["status"] == "dry_run"
    assert send_now.json()["candidateCount"] == 1
    assert send_now.json()["candidates"][0] == {
        "number": "19",
        "daysAbsent": 19,
        "lastSeen": "2026-09-25",
    }
