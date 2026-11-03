from __future__ import annotations

from copy import deepcopy
import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.cloud.contracts import (
    DAILY_DATA_UPDATE_KEY,
    DailyDataUpdateState,
    JobRecord,
    PublicationManifest,
)
from app.cloud.notification_jobs import (
    _build_dispatcher,
    run_daily_report,
    run_data_failure_notification,
    run_manual_notification,
)
from app.cloud.notification_store import KVNotificationStateStore
from app.cloud.publisher import StorageWriteError
from app.notifications.channels import (
    DeliveryResult,
    NotificationTarget,
)
from app.services.gdb_service import DayOutcome
from app.services.snapshot_builder import SnapshotBuildContext, assemble_snapshot
from app.utils.parser import PRIZE_COUNTS, PRIZE_KEYS
from tests.conftest import make_settings

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DAILY_EVENT_KEY = "daily-report:2026-10-15:20-plus"
FAILURE_EVENT_KEY = "data-update-failure:2026-10-14"


class MemoryStore:
    def __init__(self, *, fail_notification_writes: int = 0) -> None:
        self.values: dict[str, Any] = {}
        self.fail_notification_writes = fail_notification_writes

    async def get_json(self, key: str) -> Any | None:
        return deepcopy(self.values.get(key))

    async def put_json(
        self, key: str, value: Any, *, expiration_ttl: int | None = None
    ) -> None:
        del expiration_ttl
        if key == "notification-state:v1" and self.fail_notification_writes:
            self.fail_notification_writes -= 1
            raise StorageWriteError("injected state failure")
        self.values[key] = deepcopy(value)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def list_keys(self, prefix: str = "") -> list[str]:
        return sorted(key for key in self.values if key.startswith(prefix))


class StaleNotificationReadStore(MemoryStore):
    async def get_json(self, key: str) -> Any | None:
        if key == "notification-state:v1":
            return {"version": 1, "events": {}, "providers": {}}
        return await super().get_json(key)


class FakeDispatcher:
    def __init__(self, targets: list[NotificationTarget], fail_once: set[str] | None = None):
        self._targets = targets
        self._fail_once = set(fail_once or ())
        self.sent: list[tuple[NotificationTarget, str]] = []

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def targets(self) -> list[NotificationTarget]:
        return list(self._targets)

    async def send(self, target: NotificationTarget, message: str) -> DeliveryResult:
        self.sent.append((target, message))
        if target.key in self._fail_once:
            self._fail_once.remove(target.key)
            return DeliveryResult(target=target, success=False, error="temporary")
        return DeliveryResult(target=target, success=True, provider_id="1")


def target(name: str) -> NotificationTarget:
    return NotificationTarget(
        key=f"telegram:{name}",
        channel="telegram",
        kind="chat",
        recipient=name,
        display=f"chat:…{name[-1:]}",
    )


def fixed_clock() -> datetime:
    return datetime(2026, 10, 15, 9, 7, tzinfo=TZ)


def stale_clock() -> datetime:
    return datetime(2026, 11, 2, 9, 7, tzinfo=TZ)


def ready_snapshot(reference: date = date(2026, 10, 14)):
    outcomes: list[DayOutcome] = []
    for offset in range(89, -1, -1):
        day = reference - timedelta(days=offset)
        prizes = {
            prize: tuple("00" for _ in range(PRIZE_COUNTS[prize]))
            for prize in PRIZE_KEYS
        }
        if offset == 20:
            prizes["db"] = ("20",)
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
    context = SnapshotBuildContext(
        fetched_at=datetime.combine(reference, datetime.min.time(), tzinfo=TZ),
        last_source_check_at=None,
        last_successful_check_at=None,
        last_changed_at=None,
        snapshot_version=1,
        source="example.test",
    )
    return assemble_snapshot(90, outcomes, context)


def seed_snapshot(
    store: MemoryStore,
    reference: date = date(2026, 10, 14),
    *,
    snapshot=None,
) -> None:
    generated = datetime.combine(reference, datetime.min.time(), tzinfo=TZ)
    job = JobRecord(
        kind="data",
        mode="full",
        status="succeeded",
        started_at=generated,
        finished_at=generated,
    )
    version = f"ready-{reference.isoformat()}"
    snapshot_key = f"snapshot:v1:{version}:90"
    manifest = PublicationManifest(
        version=version,
        generated_at=generated,
        history_key=f"history:v1:{version}",
        snapshot_keys={30: "unused:30", 60: "unused:60", 90: snapshot_key},
        source_reference_date=reference,
        complete=True,
        last_job=job,
    )
    store.values["manifest:v1"] = manifest.model_dump(mode="json", by_alias=True)
    value = snapshot or ready_snapshot(reference)
    store.values[snapshot_key] = value.model_dump(mode="json", by_alias=True)


def seed_daily_state(
    store: MemoryStore,
    *,
    status: str,
    business_date: date = date(2026, 10, 14),
    attempt_count: int = 1,
    initial_failure: bool = True,
) -> None:
    first = datetime.combine(
        business_date,
        datetime.strptime("18:45", "%H:%M").time(),
        tzinfo=TZ,
    )
    kwargs: dict[str, Any] = {}
    if status == "failed":
        kwargs.update(
            initial_failure_at=first if initial_failure else None,
            last_reason="invalid_upstream_data",
        )
    elif status == "succeeded":
        kwargs.update(
            published_version=f"ready-{business_date.isoformat()}",
            source_reference_date=business_date,
        )
    state = DailyDataUpdateState(
        business_date=business_date,
        status=status,
        attempt_count=attempt_count,
        first_attempt_at=first,
        last_attempt_at=first,
        **kwargs,
    )
    store.values[DAILY_DATA_UPDATE_KEY] = state.model_dump(
        mode="json", by_alias=True
    )


def no_candidate_snapshot(reference: date = date(2026, 10, 14)):
    outcomes: list[DayOutcome] = []
    for offset in range(89, -1, -1):
        day = reference - timedelta(days=offset)
        values = [f"{(offset * 27 + index) % 100:02d}" for index in range(27)]
        cursor = 0
        prizes: dict[str, tuple[str, ...]] = {}
        for prize in PRIZE_KEYS:
            count = PRIZE_COUNTS[prize]
            prizes[prize] = tuple(values[cursor : cursor + count])
            cursor += count
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
    context = SnapshotBuildContext(
        fetched_at=datetime.combine(reference, datetime.min.time(), tzinfo=TZ),
        last_source_check_at=None,
        last_successful_check_at=None,
        last_changed_at=None,
        snapshot_version=1,
        source="example.test",
    )
    return assemble_snapshot(90, outcomes, context)


async def test_daily_report_skips_target_recorded_for_report_date(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    seed_daily_state(store, status="succeeded")
    dispatcher = FakeDispatcher([target("a")])
    state = KVNotificationStateStore(store)
    await state.mark_sent(DAILY_EVENT_KEY, "telegram:a", fixed_clock())
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_daily_report(
        make_settings(notification_dry_run=False), store, clock=fixed_clock
    )

    assert result.status == "already_delivered"
    assert dispatcher.sent == []


async def test_notification_state_keeps_prior_ack_despite_stale_kv_read():
    store = StaleNotificationReadStore()
    state = KVNotificationStateStore(store)

    await state.mark_sent(DAILY_EVENT_KEY, "telegram:a", fixed_clock())
    await state.mark_sent(DAILY_EVENT_KEY, "telegram:b", fixed_clock())

    persisted = store.values["notification-state:v1"]
    assert set(persisted["events"][DAILY_EVENT_KEY]["targets"]) == {
        "telegram:a",
        "telegram:b",
    }


async def test_notification_state_prunes_known_namespaces_and_keeps_unknown_keys():
    store = MemoryStore()
    store.values["notification-state:v1"] = {
        "version": 1,
        "events": {
            "daily-report:2026-01-01:20-plus": {"targets": {}},
            "data-update-failure:2026-01-02": {"targets": {}},
            "2026-01-03:19-25": {"targets": {}},
            "daily-report:2026-10-15:20-plus": {"targets": {}},
            "future-format:keep-me": {"targets": {}},
        },
        "providers": {},
    }
    state = KVNotificationStateStore(store)

    await state.mark_sent(
        "daily-report:2026-10-15:20-plus",
        "telegram:a",
        fixed_clock(),
    )

    events = store.values["notification-state:v1"]["events"]
    assert "daily-report:2026-01-01:20-plus" not in events
    assert "data-update-failure:2026-01-02" not in events
    assert "2026-01-03:19-25" not in events
    assert "daily-report:2026-10-15:20-plus" in events
    assert "future-format:keep-me" in events


async def test_daily_partial_failure_retries_only_failed_target(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    seed_daily_state(store, status="succeeded")
    dispatcher = FakeDispatcher(
        [target("a"), target("b")], fail_once={"telegram:b"}
    )
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    settings = make_settings(notification_dry_run=False)

    first = await run_daily_report(settings, store, clock=fixed_clock)
    second = await run_daily_report(settings, store, clock=fixed_clock)

    assert first.status == "partial_failure"
    assert second.status == "delivered"
    assert [item.key for item, _ in dispatcher.sent] == [
        "telegram:a",
        "telegram:b",
        "telegram:b",
    ]


async def test_daily_failed_update_reports_with_explicit_old_snapshot(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store, date(2026, 10, 13))
    seed_daily_state(store, status="failed", attempt_count=6)
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_daily_report(
        make_settings(notification_dry_run=False), store, clock=fixed_clock
    )

    assert result.status == "delivered"
    assert result.reference_date == "2026-10-13"
    assert len(dispatcher.sent) == 1
    message = dispatcher.sent[0][1]
    assert "Đang sử dụng dữ liệu cũ" in message
    assert "Số lần thử: 6" in message
    assert "Mã lỗi: invalid_upstream_data" in message
    assert "Kỳ dữ liệu: 13/10/2026" in message


async def test_daily_partial_current_snapshot_is_never_reported_as_fresh(
    monkeypatch,
):
    store = MemoryStore()
    partial = ready_snapshot()
    partial.data[-1] = partial.data[-1].model_copy(
        update={"draw_complete": False}
    )
    seed_snapshot(store, snapshot=partial)
    seed_daily_state(store, status="succeeded")
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_daily_report(
        make_settings(notification_dry_run=False), store, clock=fixed_clock
    )

    assert result.status == "delivered"
    assert result.reference_date == "2026-10-13"
    message = dispatcher.sent[0][1]
    assert "Đang sử dụng dữ liệu cũ" in message
    assert "Mã lỗi: publication_mismatch" in message
    assert "Kỳ dữ liệu: 13/10/2026" in message


async def test_daily_state_write_failure_after_send_allows_at_least_once_retry(
    monkeypatch,
):
    store = MemoryStore(fail_notification_writes=1)
    seed_snapshot(store)
    seed_daily_state(store, status="succeeded")
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    with pytest.raises(StorageWriteError):
        await run_daily_report(
            make_settings(notification_dry_run=False), store, clock=fixed_clock
        )

    assert len(dispatcher.sent) == 1
    assert (await store.get_json("job-status:v1:telegram"))["status"] == "failed"


async def test_daily_dry_run_formats_without_sending_or_marking(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    seed_daily_state(store, status="succeeded")
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_daily_report(
        make_settings(notification_dry_run=True), store, clock=fixed_clock
    )

    assert result.status == "dry_run"
    assert dispatcher.sent == []
    assert await store.get_json("notification-state:v1") is None


async def test_first_failure_alert_is_deduplicated_and_retries_only_failed_target(
    monkeypatch,
):
    store = MemoryStore()
    seed_snapshot(store, date(2026, 10, 13))
    seed_daily_state(store, status="failed")
    dispatcher = FakeDispatcher(
        [target("a"), target("b")], fail_once={"telegram:b"}
    )
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    settings = make_settings(notification_dry_run=False)

    first = await run_data_failure_notification(settings, store, clock=fixed_clock)
    raw_state = store.values[DAILY_DATA_UPDATE_KEY]
    raw_state["attemptCount"] = 2
    store.values[DAILY_DATA_UPDATE_KEY] = raw_state
    second = await run_data_failure_notification(settings, store, clock=fixed_clock)
    third = await run_data_failure_notification(settings, store, clock=fixed_clock)

    assert first.status == "partial_failure"
    assert second.status == "delivered"
    assert third.status == "already_delivered"
    assert [item.key for item, _ in dispatcher.sent] == [
        "telegram:a",
        "telegram:b",
        "telegram:b",
    ]
    message = dispatcher.sent[0][1]
    assert "14/10/2026" in message
    assert "invalid_upstream_data" in message
    assert "Kỳ dữ liệu gần nhất: 13/10/2026" in message
    assert "23:45" in message
    assert FAILURE_EVENT_KEY in store.values["notification-state:v1"]["events"]


@pytest.mark.parametrize("status", ["pending", "succeeded"])
async def test_failure_alert_noops_for_non_failed_state(monkeypatch, status):
    store = MemoryStore()
    seed_snapshot(store)
    seed_daily_state(store, status=status)
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_data_failure_notification(
        make_settings(notification_dry_run=False), store, clock=fixed_clock
    )

    assert result.status == "not_due"
    assert dispatcher.sent == []


async def test_failure_alert_noops_for_invalid_or_old_state(monkeypatch):
    store = MemoryStore()
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    settings = make_settings(notification_dry_run=False)

    seed_daily_state(
        store,
        status="failed",
        business_date=date(2026, 10, 12),
    )
    old = await run_data_failure_notification(settings, store, clock=fixed_clock)
    store.values[DAILY_DATA_UPDATE_KEY] = {
        "schemaVersion": 1,
        "businessDate": "2026-10-14",
        "status": "failed",
        "attemptCount": 1,
        "firstAttemptAt": "2026-10-14T18:45:00+07:00",
        "lastAttemptAt": "2026-10-14T18:46:00+07:00",
        "lastReason": "invalid_upstream_data",
    }
    invalid = await run_data_failure_notification(settings, store, clock=fixed_clock)

    assert old.status == invalid.status == "not_due"
    assert dispatcher.sent == []


async def test_failure_alert_sends_without_valid_snapshot(monkeypatch):
    store = MemoryStore()
    seed_daily_state(store, status="failed")
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_data_failure_notification(
        make_settings(notification_dry_run=False), store, clock=fixed_clock
    )

    assert result.status == "delivered"
    assert "Kỳ dữ liệu gần nhất: không có" in dispatcher.sent[0][1]


async def test_daily_missing_state_warns_but_still_reports(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_daily_report(
        make_settings(notification_dry_run=False), store, clock=fixed_clock
    )

    assert result.status == "delivered"
    assert "update_state_missing" in dispatcher.sent[0][1]
    assert "Đang sử dụng dữ liệu cũ" in dispatcher.sent[0][1]


async def test_daily_no_snapshot_and_zero_candidates_are_still_delivered(monkeypatch):
    settings = make_settings(notification_dry_run=False)
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings_arg, state_store: dispatcher,
    )
    no_snapshot_store = MemoryStore()
    seed_daily_state(no_snapshot_store, status="failed")

    missing = await run_daily_report(
        settings, no_snapshot_store, clock=fixed_clock
    )

    zero_store = MemoryStore()
    seed_snapshot(zero_store, snapshot=no_candidate_snapshot())
    seed_daily_state(zero_store, status="succeeded")
    zero = await run_daily_report(settings, zero_store, clock=fixed_clock)

    assert missing.status == "delivered"
    assert "Không có snapshot hợp lệ" in dispatcher.sent[0][1]
    assert zero.status == "delivered"
    assert "Không có số nào chưa xuất hiện từ 20 ngày trở lên" in dispatcher.sent[1][1]


async def test_daily_event_repeats_next_day_with_same_snapshot(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    seed_daily_state(store, status="succeeded")
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    settings = make_settings(notification_dry_run=False)

    first = await run_daily_report(settings, store, clock=fixed_clock)
    repeated = await run_daily_report(settings, store, clock=fixed_clock)
    next_day = await run_daily_report(settings, store, clock=stale_clock)

    assert first.status == "delivered"
    assert repeated.status == "already_delivered"
    assert next_day.status == "delivered"
    assert len(dispatcher.sent) == 2


@pytest.mark.parametrize(
    "clock",
    [
        lambda: datetime(2026, 10, 15, 8, 59, tzinfo=TZ),
        lambda: datetime(2026, 10, 15, 13, 0, tzinfo=TZ),
    ],
)
async def test_daily_outside_morning_window_does_not_consume_event(
    monkeypatch, clock
):
    store = MemoryStore()
    seed_snapshot(store)
    seed_daily_state(store, status="succeeded")
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_daily_report(
        make_settings(notification_dry_run=False), store, clock=clock
    )

    assert result.status == "outside_window"
    assert dispatcher.sent == []
    assert await store.get_json("notification-state:v1") is None


async def test_manual_notification_allows_explicit_repeats(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    settings = make_settings(notification_dry_run=False)

    first = await run_manual_notification(
        settings,
        store,
        "123e4567-e89b-12d3-a456-426614174000",
        clock=fixed_clock,
    )
    second = await run_manual_notification(
        settings,
        store,
        "123e4567-e89b-12d3-a456-426614174001",
        clock=fixed_clock,
    )

    assert first.status == second.status == "delivered"
    assert len(dispatcher.sent) == 2


async def test_manual_notification_does_not_suppress_daily_delivery(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    seed_daily_state(store, status="succeeded")
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    settings = make_settings(notification_dry_run=False)

    manual = await run_manual_notification(
        settings,
        store,
        "123e4567-e89b-12d3-a456-426614174010",
        clock=fixed_clock,
    )
    daily = await run_daily_report(settings, store, clock=fixed_clock)

    assert manual.status == "delivered"
    assert daily.status == "delivered"
    assert len(dispatcher.sent) == 2
    ledger = store.values["notification-state:v1"]
    assert set(ledger["events"]) == {DAILY_EVENT_KEY}


def test_cloud_dispatcher_is_telegram_only_and_uses_hmac_target_keys():
    store = MemoryStore()
    settings = make_settings(
        notification_ledger_hmac_key="ledger-secret",
        telegram_bot_token="telegram-secret",
        telegram_chat_ids="123456789",
        zalo_access_token="zalo-secret",
        zalo_recipient_ids="zalo-user",
        facebook_page_access_token="facebook-secret",
        facebook_page_id="page-1",
        facebook_messenger_recipient_ids="psid-1",
    )

    dispatcher = _build_dispatcher(settings, KVNotificationStateStore(store))
    targets = dispatcher.targets()

    assert [(item.channel, item.kind) for item in targets] == [("telegram", "chat")]
    assert targets[0].key == (
        "telegram:chat:"
        "a22a051196d83c49225db05dc40fdad69b501b2c29301214805246eaebc7d78d"
    )
    assert "123456789" not in targets[0].key
    assert "6789" not in targets[0].key


async def test_cancelled_manual_notification_persists_timeout_failure(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    entered = asyncio.Event()
    dispatcher = FakeDispatcher([target("a")])

    async def never_finishes(target_arg, message):
        del target_arg, message
        entered.set()
        await asyncio.Event().wait()

    dispatcher.send = never_finishes
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    request_id = "123e4567-e89b-12d3-a456-426614174009"
    task = asyncio.create_task(
        run_manual_notification(
            make_settings(notification_dry_run=False),
            store,
            request_id,
            clock=fixed_clock,
        )
    )
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert (await store.get_json(f"operation:v1:{request_id}"))["status"] == "failed"
    job = await store.get_json("job-status:v1:telegram")
    assert job["status"] == "failed"
    assert job["reason"] == "job_timeout"


async def test_manual_exception_uses_injected_clock_for_failed_operation(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    dispatcher = FakeDispatcher([target("a")])

    async def fail_send(target_arg, message):
        del target_arg, message
        raise RuntimeError("provider failed")

    dispatcher.send = fail_send  # type: ignore[method-assign]
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    request_id = "123e4567-e89b-12d3-a456-426614174002"

    with pytest.raises(RuntimeError, match="provider failed"):
        await run_manual_notification(
            make_settings(notification_dry_run=False),
            store,
            request_id,
            clock=fixed_clock,
        )

    operation = await store.get_json(f"operation:v1:{request_id}")
    assert operation["status"] == "failed"
    assert operation["updatedAt"] == fixed_clock().isoformat()
