"""Tests for alert evaluation, idempotency and channel orchestration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.notification_router import router as notification_router
from app.cloud.contracts import DailyDataUpdateState
from app.notifications.channels import DeliveryResult, NotificationTarget
from app.notifications.channels import NotificationDispatcher
from app.notifications.models import (
    DailyUpdateWarning,
    evaluate_snapshot,
    evaluate_snapshot_now,
    format_daily_report_message,
    format_data_failure_message,
    format_alert_message,
    format_immediate_report_message,
    format_no_data_daily_message,
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


def _minimum_snapshot(*, days: int = 90, future_partial: bool = False):
    settings = make_settings()
    gdb = GdbService(
        settings,
        FakeFetcher(lambda url, cond: status_result(FetchStatus.TIMEOUT)),
    )
    reference = date(2026, 10, 14)
    first = reference - timedelta(days=days - 1)
    seen_at_offsets = {19: "01", 20: "02", 21: "03", 26: "04", 40: "05"}
    outcomes: list[DayOutcome] = []
    for index in range(days):
        day = first + timedelta(days=index)
        offset = (reference - day).days
        prizes = {
            prize: tuple("99" for _ in range(PRIZE_COUNTS[prize]))
            for prize in PRIZE_KEYS
        }
        if offset in seen_at_offsets:
            prizes["db"] = (seen_at_offsets[offset],)
        outcomes.append(
            DayOutcome(
                day=day,
                source_url=f"https://example.test/{day.isoformat()}",
                gdb=prizes["db"][0],
                prizes=prizes,
                complete=True,
                ok=True,
            )
        )
    if future_partial:
        future = reference + timedelta(days=1)
        outcomes.append(
            DayOutcome(
                day=future,
                source_url=f"https://example.test/{future.isoformat()}",
                gdb="06",
                prizes={"db": ("06",)},
                complete=False,
                ok=True,
            )
        )
    state = RealtimeState(poll_interval_seconds=30.0, realtime_enabled=True)
    return gdb._assemble(90, outcomes, state), reference


def test_minimum_absence_evaluation_covers_boundaries_and_all_numbers():
    snapshot, reference = _minimum_snapshot(future_partial=True)

    evaluation = evaluate_snapshot_now(
        snapshot,
        now=datetime(2026, 10, 20, 14, 30, tzinfo=TZ),
        min_days=20,
    )

    by_number = {item.number: item for item in evaluation.candidates}
    assert evaluation.status == "ready"
    assert evaluation.reference_date == reference
    assert "01" not in by_number
    assert {
        number: (by_number[number].days_absent, by_number[number].is_lower_bound)
        for number in ("02", "03", "04", "05", "06")
    } == {
        "02": (20, False),
        "03": (21, False),
        "04": (26, False),
        "05": (40, False),
        "06": (90, True),
    }
    assert by_number["06"].last_seen is None
    assert "00" in by_number
    assert "99" not in by_number
    assert list(evaluation.candidates) == sorted(
        evaluation.candidates,
        key=lambda item: (-item.days_absent, item.number),
    )


def test_minimum_absence_does_not_claim_never_seen_with_short_coverage():
    snapshot, reference = _minimum_snapshot(days=19)

    evaluation = evaluate_snapshot_now(
        snapshot,
        now=datetime(2026, 10, 20, 14, 30, tzinfo=TZ),
        min_days=20,
    )

    assert evaluation.status == "no_match"
    assert evaluation.reference_date == reference
    assert evaluation.candidates == ()


def test_daily_report_formats_fresh_stale_zero_and_lower_bound_results():
    snapshot, reference = _minimum_snapshot()
    evaluation = evaluate_snapshot_now(
        snapshot,
        now=datetime(2026, 10, 20, 14, 30, tzinfo=TZ),
        min_days=20,
    )

    fresh = format_daily_report_message(
        evaluation,
        report_date=date(2026, 10, 15),
        min_days=20,
    )
    stale = format_daily_report_message(
        evaluation,
        report_date=date(2026, 10, 15),
        min_days=20,
        warning=DailyUpdateWarning(
            expected_date=date(2026, 10, 14),
            attempt_count=6,
            last_reason="invalid_upstream_data",
        ),
    )
    zero = format_daily_report_message(
        evaluation.__class__(
            status="no_match",
            reference_date=reference,
            candidates=(),
        ),
        report_date=date(2026, 10, 15),
        min_days=20,
    )

    assert "Báo cáo ngày: 15/10/2026" in fresh
    assert "Kỳ dữ liệu: 14/10/2026" in fresh
    assert "số chưa xuất hiện từ 20 ngày trở lên" in fresh
    assert "≥90 ngày – không thấy trong dữ liệu hiện có" in fresh
    assert "Tổng cộng:" in fresh
    assert stale.index("Đang sử dụng dữ liệu cũ") < stale.index("Kỳ dữ liệu")
    assert "Số lần thử: 6" in stale
    assert "Mã lỗi: invalid_upstream_data" in stale
    assert (
        "Không có số nào chưa xuất hiện từ 20 ngày trở lên trong kỳ dữ liệu này."
        in zero
    )


def test_failure_and_no_data_messages_never_invent_results():
    state = DailyDataUpdateState(
        business_date=date(2026, 10, 14),
        status="failed",
        attempt_count=1,
        first_attempt_at=datetime(2026, 10, 14, 18, 45, tzinfo=TZ),
        last_attempt_at=datetime(2026, 10, 14, 18, 46, tzinfo=TZ),
        initial_failure_at=datetime(2026, 10, 14, 18, 46, tzinfo=TZ),
        last_reason="invalid_upstream_data",
    )

    failure = format_data_failure_message(
        state,
        latest_reference_date=date(2026, 10, 13),
    )
    no_data = format_no_data_daily_message(
        report_date=date(2026, 10, 15),
        expected_date=date(2026, 10, 14),
        attempt_count=1,
        last_reason="invalid_upstream_data",
    )

    assert "14/10/2026" in failure
    assert "Kỳ dữ liệu gần nhất: 13/10/2026" in failure
    assert "23:45" in failure
    assert "Không có snapshot hợp lệ để lập báo cáo." in no_data
    assert not any(
        (line[:1].isdigit() and " ngày:" in line) or line.startswith("≥")
        for line in no_data.splitlines()
    )


def test_minimum_immediate_report_uses_same_unbounded_rule():
    snapshot, _ = _minimum_snapshot()
    checked_at = datetime(2026, 10, 20, 14, 30, tzinfo=TZ)
    evaluation = evaluate_snapshot_now(
        snapshot,
        now=checked_at,
        min_days=20,
    )

    message = format_immediate_report_message(
        evaluation,
        checked_at=checked_at,
        min_days=20,
    )

    assert "40 ngày: 05" in message
    assert "≥90 ngày – không thấy trong dữ liệu hiện có" in message
    assert "Kiểm tra lúc: 20/10/2026 14:30:00" in message


def test_evaluate_snapshot_uses_unbounded_minimum_and_due_time():
    snapshot, reference = _minimum_snapshot()
    evaluation = evaluate_snapshot(
        snapshot,
        now=datetime(2026, 10, 15, 9, 1, tzinfo=TZ),
        min_days=20,
        send_time=datetime.strptime("09:00", "%H:%M").time(),
    )

    assert evaluation.status == "ready"
    assert evaluation.reference_date == reference
    by_number = {item.number: item.days_absent for item in evaluation.candidates}
    assert by_number["02"] == 20
    assert by_number["05"] == 40
    message = format_alert_message(evaluation, min_days=20)
    assert "40 ngày: 05" in message
    assert "14/10/2026" in message


def test_evaluate_snapshot_ignores_incomplete_draws():
    snapshot, _ = _snapshot(incomplete_offset=10)
    evaluation = evaluate_snapshot(
        snapshot,
        now=datetime(2026, 10, 15, 9, 1, tzinfo=TZ),
        min_days=20,
        send_time=datetime.strptime("09:00", "%H:%M").time(),
    )

    assert evaluation.status == "ready"


def test_evaluate_snapshot_now_ignores_schedule_and_formats_report():
    snapshot, reference = _minimum_snapshot()
    checked_at = datetime(2026, 10, 20, 14, 30, tzinfo=TZ)
    evaluation = evaluate_snapshot_now(
        snapshot,
        now=checked_at,
        min_days=20,
    )

    assert evaluation.status == "ready"
    assert evaluation.reference_date == reference
    assert any(
        item.number == "05" and item.days_absent == 40
        for item in evaluation.candidates
    )
    message = format_immediate_report_message(
        evaluation,
        checked_at=checked_at,
        min_days=20,
    )
    assert "40 ngày: 05" in message
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
    snapshot, _ = _minimum_snapshot()
    settings = make_settings(
        notifications_enabled=True,
        notification_dry_run=False,
        notification_state_path=str(tmp_path / "state.json"),
        notification_min_days=20,
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
    persisted = NotificationStateStore(str(tmp_path / "state.json"))
    assert await persisted.sent_targets("2026-10-14:20-plus") == {
        "telegram:chat:test"
    }


async def test_notification_service_delivers_valid_zero_candidate_confirmation(
    tmp_path,
):
    snapshot, _ = _minimum_snapshot(days=19)
    settings = make_settings(
        notifications_enabled=True,
        notification_dry_run=False,
        notification_state_path=str(tmp_path / "state.json"),
        notification_min_days=20,
    )
    dispatcher = _FakeDispatcher()
    service = NotificationService(
        settings,
        _FakeRealtime(snapshot),
        dispatcher=dispatcher,
        clock=lambda: datetime(2026, 10, 15, 9, 1, tzinfo=TZ),
    )

    first = await service.run_once()
    second = await service.run_once()

    assert len(first) == 1
    assert second == []
    assert "Không có số nào chưa xuất hiện từ 20 ngày trở lên" in dispatcher.sent[0][1]


async def test_immediate_notification_sends_on_every_explicit_click(tmp_path):
    snapshot, _ = _minimum_snapshot()
    settings = make_settings(
        notifications_enabled=True,
        notification_dry_run=False,
        notification_state_path=str(tmp_path / "state.json"),
        notification_min_days=20,
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
    assert any(
        item.number == "05" and item.days_absent == 40
        for item in first.candidates
    )
    assert second.status == "delivered"
    assert len(dispatcher.sent) == 2
    assert all("Kiểm tra lúc: 20/10/2026 14:30:00" in item[1] for item in dispatcher.sent)


def test_notification_operational_endpoints_are_protected(tmp_path):
    snapshot, _ = _minimum_snapshot()
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
    body = send_now.json()
    assert body["candidateCount"] > 1
    assert body["minDays"] == 20
    assert body["maxDays"] is None
    assert body["threshold"] == "20-plus"
    candidate = next(item for item in body["candidates"] if item["number"] == "05")
    assert candidate == {
        "number": "05",
        "daysAbsent": 40,
        "lastSeen": "2026-09-04",
        "isLowerBound": False,
    }
