from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from app.cloud.contracts import (
    JobRecord,
    PublicationManifest,
    StoredDayOutcome,
)
from app.cloud.publisher import (
    PayloadTooLargeError,
    SnapshotPublisher,
    StorageWriteError,
)
from app.services.gdb_service import DayOutcome
from app.services.snapshot_builder import SnapshotBuildContext


class MemoryStore:
    def __init__(self, *, fail_on_put: int | None = None) -> None:
        self.values: dict[str, Any] = {}
        self.fail_on_put = fail_on_put
        self.put_count = 0

    async def get_json(self, key: str) -> Any | None:
        value = self.values.get(key)
        return deepcopy(value)

    async def put_json(
        self, key: str, value: Any, *, expiration_ttl: int | None = None
    ) -> None:
        del expiration_ttl
        self.put_count += 1
        if self.put_count == self.fail_on_put:
            raise StorageWriteError("injected write failure")
        self.values[key] = deepcopy(value)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def list_keys(self, prefix: str = "") -> list[str]:
        return sorted(key for key in self.values if key.startswith(prefix))


@pytest.fixture
def context() -> SnapshotBuildContext:
    generated = datetime(2026, 10, 29, 11, 5, tzinfo=timezone.utc)
    return SnapshotBuildContext(
        fetched_at=generated,
        last_source_check_at=generated,
        last_successful_check_at=generated,
        last_changed_at=generated,
        snapshot_version=8,
        source="example.test",
    )


@pytest.fixture
def outcomes() -> list[DayOutcome]:
    return [
        DayOutcome(
            day=date(2026, 10, 28),
            source_url="https://example.test/2026-10-28",
            gdb="12",
            complete=True,
            ok=True,
        ),
        DayOutcome(
            day=date(2026, 10, 29),
            source_url="https://example.test/2026-10-29",
            gdb="34",
            complete=False,
            ok=True,
        ),
    ]


@pytest.fixture
def job(context) -> JobRecord:
    return JobRecord(
        kind="data",
        mode="full",
        status="succeeded",
        started_at=context.fetched_at,
        finished_at=context.fetched_at,
    )


def test_stored_day_outcome_round_trips_domain_values(outcomes):
    restored = StoredDayOutcome.from_domain(outcomes[0]).to_domain()

    assert restored.signature == outcomes[0].signature
    assert restored.complete is outcomes[0].complete
    assert restored.source_url == outcomes[0].source_url


async def test_publish_advances_manifest_only_after_all_payloads_exist(
    outcomes, context, job
):
    store = MemoryStore(fail_on_put=4)
    old_manifest = PublicationManifest(
        version="20261028T110500000000Z",
        generated_at=datetime(2026, 10, 28, 11, 5, tzinfo=timezone.utc),
        history_key="history:v1:old",
        snapshot_keys={30: "snapshot:v1:old:30"},
        source_reference_date=date(2026, 10, 28),
        complete=True,
        last_job=job,
    )
    store.values["manifest:v1"] = old_manifest.model_dump(mode="json", by_alias=True)
    publisher = SnapshotPublisher(store)

    with pytest.raises(StorageWriteError):
        await publisher.publish(outcomes, context, job)

    assert await store.get_json("manifest:v1") == old_manifest.model_dump(
        mode="json", by_alias=True
    )


async def test_successful_publish_writes_all_ranges_before_manifest(
    outcomes, context, job
):
    store = MemoryStore()
    manifest = await SnapshotPublisher(store).publish(outcomes, context, job)

    assert set(manifest.snapshot_keys) == {30, 60, 90}
    assert await store.get_json("manifest:v1") == manifest.model_dump(
        mode="json", by_alias=True
    )
    for key in [manifest.history_key, *manifest.snapshot_keys.values()]:
        assert await store.get_json(key) is not None


async def test_oversized_payload_fails_before_any_versioned_write(
    outcomes, context, job
):
    store = MemoryStore()
    old = {"version": "old"}
    store.values["manifest:v1"] = old

    with pytest.raises(PayloadTooLargeError):
        await SnapshotPublisher(store, max_value_bytes=100).publish(
            outcomes, context, job
        )

    assert store.values == {"manifest:v1": old}
    assert store.put_count == 0


async def test_load_history_uses_only_manifest_version(outcomes, context, job):
    store = MemoryStore()
    publisher = SnapshotPublisher(store)
    manifest = await publisher.publish(outcomes, context, job)
    store.values["history:v1:unpublished"] = [
        StoredDayOutcome.from_domain(
            DayOutcome(
                day=date(2026, 10, 30),
                source_url="https://example.test/unpublished",
                gdb="99",
                complete=True,
                ok=True,
            )
        ).model_dump(mode="json", by_alias=True)
    ]

    restored = await publisher.load_active_history()

    assert [item.day for item in restored] == [item.day for item in outcomes]
    assert manifest.history_key != "history:v1:unpublished"


async def test_publish_prunes_versions_beyond_rollback_window(
    outcomes, context, job
):
    store = MemoryStore()
    publisher = SnapshotPublisher(store, retained_versions=2)

    for offset in range(3):
        await publisher.publish(
            outcomes,
            replace(context, fetched_at=context.fetched_at + timedelta(minutes=offset)),
            job,
        )

    assert len(await store.list_keys("history:v1:")) == 2
    assert len(await store.list_keys("snapshot:v1:")) == 6
