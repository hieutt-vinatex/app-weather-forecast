from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncio
import pytest

from app.cloud.contracts import JobRecord, PublicationManifest
from app.cloud.data_jobs import full_sync, incremental_sync, run_data_job
from app.cloud.filesystem_store import FilesystemJsonStore
from app.cloud.publisher import SnapshotPublisher
from app.services.gdb_service import DayOutcome
from app.services.snapshot_builder import SnapshotBuildContext
from tests.conftest import make_settings


class MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.ttls: dict[str, int | None] = {}

    async def get_json(self, key: str) -> Any | None:
        return deepcopy(self.values.get(key))

    async def put_json(
        self, key: str, value: Any, *, expiration_ttl: int | None = None
    ) -> None:
        self.values[key] = deepcopy(value)
        self.ttls[key] = expiration_ttl

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def list_keys(self, prefix: str = "") -> list[str]:
        return sorted(key for key in self.values if key.startswith(prefix))


def fixed_clock() -> datetime:
    return datetime(2026, 10, 29, 11, 0, tzinfo=timezone.utc)


def outcome_for(
    day: date, value: int, *, ok: bool = True, complete: bool | None = None
) -> DayOutcome:
    return DayOutcome(
        day=day,
        source_url=f"https://example.test/{day.isoformat()}",
        gdb=f"{value % 100:02d}" if ok else None,
        complete=ok if complete is None else complete,
        ok=ok,
        reason=None if ok else "parse_failure",
    )


def outcomes_ending(end: date, count: int = 90) -> list[DayOutcome]:
    start = end - timedelta(days=count - 1)
    return [outcome_for(start + timedelta(days=index), index) for index in range(count)]


async def publish_initial(store: MemoryStore, end: date) -> PublicationManifest:
    generated = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc)
    context = SnapshotBuildContext(
        fetched_at=generated,
        last_source_check_at=generated,
        last_successful_check_at=generated,
        last_changed_at=generated,
        snapshot_version=1,
        source="example.test",
        cached=False,
    )
    job = JobRecord(
        kind="data",
        mode="full",
        status="succeeded",
        started_at=generated,
        finished_at=generated,
        record_count=90,
    )
    return await SnapshotPublisher(store).publish(outcomes_ending(end), context, job)


async def test_full_sync_fetches_90_days_and_publishes_three_ranges(monkeypatch):
    store = MemoryStore()
    settings = make_settings()
    requested: list[date] = []

    async def fake_fetch(settings_arg, days):
        assert settings_arg is settings
        requested.extend(days)
        return [outcome_for(day, index) for index, day in enumerate(days)]

    monkeypatch.setattr("app.cloud.data_jobs._fetch_outcomes", fake_fetch)

    result = await full_sync(settings, store, clock=fixed_clock)
    manifest = PublicationManifest.model_validate(await store.get_json("manifest:v1"))
    history = await SnapshotPublisher(store).load_active_history()

    assert result.status == "succeeded"
    assert len(requested) == 90
    assert set(manifest.snapshot_keys) == {30, 60, 90}
    assert len(history) == 90
    assert (await store.get_json("job-status:v1:data"))["status"] == "succeeded"


async def test_incremental_sync_replaces_dates_without_duplicates(monkeypatch):
    store = MemoryStore()
    settings = make_settings()
    await publish_initial(store, date(2026, 10, 28))

    async def fake_fetch(settings_arg, days):
        del settings_arg
        return [outcome_for(day, 88 + index) for index, day in enumerate(days)]

    monkeypatch.setattr("app.cloud.data_jobs._fetch_outcomes", fake_fetch)

    result = await incremental_sync(settings, store, clock=fixed_clock)
    history = await SnapshotPublisher(store).load_active_history()
    dates = [item.day.isoformat() for item in history]

    assert result.status == "succeeded"
    assert len(dates) == len(set(dates)) == 90
    assert dates[-1] == "2026-10-29"


async def test_full_sync_preserves_known_good_days_when_upstream_degrades(monkeypatch):
    store = MemoryStore()
    settings = make_settings()
    await publish_initial(store, date(2026, 10, 28))

    async def degraded_fetch(settings_arg, days):
        del settings_arg
        return [
            outcome_for(day, 77, ok=day == days[-1])
            for day in days
        ]

    monkeypatch.setattr("app.cloud.data_jobs._fetch_outcomes", degraded_fetch)

    result = await full_sync(settings, store, clock=fixed_clock)
    history = await SnapshotPublisher(store).load_active_history()

    assert result.status == "succeeded"
    assert len(history) == 90
    assert all(item.ok for item in history)
    preserved = next(item for item in history if item.day == date(2026, 10, 28))
    assert preserved.gdb == "89"


async def test_incremental_sync_does_not_replace_complete_draw_with_partial(monkeypatch):
    store = MemoryStore()
    settings = make_settings()
    await publish_initial(store, date(2026, 10, 28))

    async def partial_fetch(settings_arg, days):
        del settings_arg
        return [
            outcome_for(days[0], 11, complete=False),
            outcome_for(days[1], 12, complete=False),
        ]

    monkeypatch.setattr("app.cloud.data_jobs._fetch_outcomes", partial_fetch)

    result = await incremental_sync(settings, store, clock=fixed_clock)
    history = await SnapshotPublisher(store).load_active_history()
    yesterday = next(item for item in history if item.day == date(2026, 10, 28))

    assert result.status == "succeeded"
    assert yesterday.complete is True
    assert yesterday.gdb == "89"


async def test_malformed_current_draw_keeps_previous_manifest(monkeypatch):
    store = MemoryStore()
    settings = make_settings()
    old_manifest = await publish_initial(store, date(2026, 10, 28))

    async def fake_fetch(settings_arg, days):
        del settings_arg
        return [outcome_for(days[0], 10), outcome_for(days[1], 0, ok=False)]

    monkeypatch.setattr("app.cloud.data_jobs._fetch_outcomes", fake_fetch)

    result = await incremental_sync(settings, store, clock=fixed_clock)

    assert result.status == "failed"
    assert (await store.get_json("manifest:v1"))["version"] == old_manifest.version
    assert (await store.get_json("job-status:v1:data"))["status"] == "failed"


async def test_failed_filesystem_sync_keeps_manifest_and_publishes_status(
    monkeypatch, tmp_path
):
    store = FilesystemJsonStore(tmp_path)
    settings = make_settings()
    old_manifest = await publish_initial(store, date(2026, 10, 28))

    async def fake_fetch(settings_arg, days):
        del settings_arg
        return [outcome_for(days[0], 10), outcome_for(days[1], 0, ok=False)]

    monkeypatch.setattr("app.cloud.data_jobs._fetch_outcomes", fake_fetch)

    result = await incremental_sync(settings, store, clock=fixed_clock)

    assert result.status == "failed"
    assert (await store.get_json("manifest:v1"))["version"] == old_manifest.version
    assert (await store.get_json("job-status:v1:data"))["status"] == "failed"
    assert (tmp_path / "site/data/status.json").is_file()


async def test_requested_operation_reaches_succeeded_with_ttl(monkeypatch):
    store = MemoryStore()
    settings = make_settings()

    async def fake_fetch(settings_arg, days):
        del settings_arg
        return [outcome_for(day, index) for index, day in enumerate(days)]

    monkeypatch.setattr("app.cloud.data_jobs._fetch_outcomes", fake_fetch)

    result = await run_data_job(
        settings,
        store,
        mode="full",
        request_id="123e4567-e89b-12d3-a456-426614174000",
        clock=fixed_clock,
    )
    operation_key = "operation:v1:123e4567-e89b-12d3-a456-426614174000"
    operation = await store.get_json(operation_key)

    assert result.status == "succeeded"
    assert operation["status"] == "succeeded"
    assert store.ttls[operation_key] == 86400


async def test_cancelled_data_job_persists_timeout_failure(monkeypatch):
    store = MemoryStore()
    settings = make_settings()
    entered = asyncio.Event()

    async def never_finishes(settings_arg, days):
        del settings_arg, days
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("app.cloud.data_jobs._fetch_outcomes", never_finishes)
    request_id = "123e4567-e89b-12d3-a456-426614174009"
    task = asyncio.create_task(
        run_data_job(
            settings,
            store,
            mode="full",
            request_id=request_id,
            clock=fixed_clock,
        )
    )
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert (await store.get_json("job-status:v1:data"))["status"] == "failed"
    assert (await store.get_json("job-status:v1:data"))["reason"] == "job_timeout"
    operation = await store.get_json(f"operation:v1:{request_id}")
    assert operation["status"] == "failed"
