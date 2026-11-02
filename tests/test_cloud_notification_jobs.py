from __future__ import annotations

from copy import deepcopy
import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.cloud.contracts import JobRecord, PublicationManifest
from app.cloud.notification_jobs import (
    _build_dispatcher,
    run_manual_notification,
    run_scheduled_notification,
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
EVENT_KEY = "2026-10-14:19-25"


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


def ready_snapshot():
    reference = date(2026, 10, 14)
    outcomes: list[DayOutcome] = []
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
                complete=True,
                ok=True,
            )
        )
    context = SnapshotBuildContext(
        fetched_at=datetime(2026, 10, 14, 18, 40, tzinfo=TZ),
        last_source_check_at=None,
        last_successful_check_at=None,
        last_changed_at=None,
        snapshot_version=1,
        source="example.test",
    )
    return assemble_snapshot(90, outcomes, context)


def seed_snapshot(store: MemoryStore) -> None:
    generated = datetime(2026, 10, 14, 18, 40, tzinfo=TZ)
    job = JobRecord(
        kind="data",
        mode="full",
        status="succeeded",
        started_at=generated,
        finished_at=generated,
    )
    snapshot_key = "snapshot:v1:ready:90"
    manifest = PublicationManifest(
        version="ready",
        generated_at=generated,
        history_key="history:v1:ready",
        snapshot_keys={30: "unused:30", 60: "unused:60", 90: snapshot_key},
        source_reference_date=date(2026, 10, 14),
        complete=True,
        last_job=job,
    )
    store.values["manifest:v1"] = manifest.model_dump(mode="json", by_alias=True)
    store.values[snapshot_key] = ready_snapshot().model_dump(mode="json", by_alias=True)


async def test_scheduled_notification_skips_recorded_target(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    dispatcher = FakeDispatcher([target("a")])
    state = KVNotificationStateStore(store)
    await state.mark_sent(EVENT_KEY, "telegram:a", fixed_clock())
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_scheduled_notification(
        make_settings(notification_dry_run=False), store, clock=fixed_clock
    )

    assert result.status == "already_delivered"
    assert dispatcher.sent == []


async def test_notification_state_keeps_prior_ack_despite_stale_kv_read():
    store = StaleNotificationReadStore()
    state = KVNotificationStateStore(store)

    await state.mark_sent(EVENT_KEY, "telegram:a", fixed_clock())
    await state.mark_sent(EVENT_KEY, "telegram:b", fixed_clock())

    persisted = store.values["notification-state:v1"]
    assert set(persisted["events"][EVENT_KEY]["targets"]) == {
        "telegram:a",
        "telegram:b",
    }


async def test_partial_failure_retries_only_failed_target(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    dispatcher = FakeDispatcher(
        [target("a"), target("b")], fail_once={"telegram:b"}
    )
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )
    settings = make_settings(notification_dry_run=False)

    first = await run_scheduled_notification(settings, store, clock=fixed_clock)
    second = await run_scheduled_notification(settings, store, clock=fixed_clock)

    assert first.status == "partial_failure"
    assert second.status == "delivered"
    assert [item.key for item, _ in dispatcher.sent] == [
        "telegram:a",
        "telegram:b",
        "telegram:b",
    ]


async def test_scheduled_notification_uses_latest_complete_snapshot_when_old(
    monkeypatch,
):
    store = MemoryStore()
    seed_snapshot(store)
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_scheduled_notification(
        make_settings(notification_dry_run=False), store, clock=stale_clock
    )

    assert result.status == "delivered"
    assert result.reference_date == "2026-10-14"
    assert len(dispatcher.sent) == 1
    assert "Kỳ dữ liệu: 14/10/2026" in dispatcher.sent[0][1]


async def test_state_write_failure_after_send_allows_at_least_once_retry(monkeypatch):
    store = MemoryStore(fail_notification_writes=1)
    seed_snapshot(store)
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    with pytest.raises(StorageWriteError):
        await run_scheduled_notification(
            make_settings(notification_dry_run=False), store, clock=fixed_clock
        )

    assert len(dispatcher.sent) == 1
    assert (await store.get_json("job-status:v1:telegram"))["status"] == "failed"


async def test_dry_run_formats_without_sending_or_marking(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
    dispatcher = FakeDispatcher([target("a")])
    monkeypatch.setattr(
        "app.cloud.notification_jobs._build_dispatcher",
        lambda settings, state_store: dispatcher,
    )

    result = await run_scheduled_notification(
        make_settings(notification_dry_run=True), store, clock=fixed_clock
    )

    assert result.status == "dry_run"
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


async def test_manual_notification_does_not_suppress_scheduled_delivery(monkeypatch):
    store = MemoryStore()
    seed_snapshot(store)
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
    scheduled = await run_scheduled_notification(settings, store, clock=fixed_clock)

    assert manual.status == "delivered"
    assert scheduled.status == "delivered"
    assert len(dispatcher.sent) == 2


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
