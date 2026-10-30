from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.cloud.contracts import JobRecord
from app.cloud.publisher import SnapshotPublisher
from app.services.gdb_service import DayOutcome
from app.services.snapshot_builder import SnapshotBuildContext
from app.utils.parser import PRIZE_COUNTS
from scripts.verify_cloud_contracts import verify_fixture_directory


class FixtureStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def get_json(self, key: str) -> Any | None:
        return deepcopy(self.values.get(key))

    async def put_json(
        self,
        key: str,
        value: Any,
        *,
        expiration_ttl: int | None = None,
    ) -> None:
        del expiration_ttl
        self.values[key] = deepcopy(value)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def list_keys(self, prefix: str = "") -> list[str]:
        return sorted(key for key in self.values if key.startswith(prefix))


def complete_prizes(seed: int) -> dict[str, tuple[str, ...]]:
    return {
        prize: tuple(
            f"{(seed + offset) % 100:02d}" for offset in range(expected_count)
        )
        for prize, expected_count in PRIZE_COUNTS.items()
    }


async def published_fixture(directory: Path) -> Path:
    generated_at = datetime(2026, 10, 29, 11, 5, tzinfo=timezone.utc)
    context = SnapshotBuildContext(
        fetched_at=generated_at,
        last_source_check_at=generated_at,
        last_successful_check_at=generated_at,
        last_changed_at=generated_at,
        snapshot_version=8,
        source="example.test",
    )
    first_day = date(2026, 8, 1)
    outcomes = [
        DayOutcome(
            day=first_day + timedelta(days=index),
            source_url=f"https://example.test/{first_day + timedelta(days=index)}",
            gdb=f"{index % 100:02d}",
            prizes=complete_prizes(index),
            complete=True,
            ok=True,
        )
        for index in range(90)
    ]
    job = JobRecord(
        kind="data",
        mode="full",
        status="succeeded",
        started_at=generated_at,
        finished_at=generated_at,
    )
    store = FixtureStore()
    manifest = await SnapshotPublisher(store).publish(outcomes, context, job)

    write_json(directory / "manifest.json", store.values["manifest:v1"])
    write_json(directory / "history.json", store.values[manifest.history_key])
    for days, key in manifest.snapshot_keys.items():
        write_json(directory / f"snapshot-{days}.json", store.values[key])
    return directory


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


async def test_all_published_ranges_match_public_contract(tmp_path):
    fixtures = await published_fixture(tmp_path)

    report = verify_fixture_directory(fixtures)

    assert report.valid_ranges == {30, 60, 90}
    assert report.errors == []


async def test_verifier_rejects_unsorted_duplicate_dates_and_secret_material(
    tmp_path,
):
    fixtures = await published_fixture(tmp_path)
    snapshot_path = fixtures / "snapshot-30.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["data"] = [snapshot["data"][1], snapshot["data"][1]]
    snapshot["meta"]["debug"] = "TELEGRAM_BOT_TOKEN"
    write_json(snapshot_path, snapshot)

    report = verify_fixture_directory(fixtures)

    assert 30 not in report.valid_ranges
    assert any("sorted and unique" in error for error in report.errors)
    assert any("secret material" in error for error in report.errors)


async def test_verifier_enforces_the_configured_value_size_limit(tmp_path):
    fixtures = await published_fixture(tmp_path)

    report = verify_fixture_directory(fixtures, max_value_bytes=100)

    assert report.valid_ranges == set()
    assert any("safe byte limit" in error for error in report.errors)


async def test_verifier_checks_manifest_statistics_and_frontend_record_shape(
    tmp_path,
):
    fixtures = await published_fixture(tmp_path)
    manifest_path = fixtures / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schemaVersion"] = 2
    manifest["generatedAt"] = "not-a-timestamp"
    del manifest["snapshotKeys"]["90"]
    write_json(manifest_path, manifest)

    snapshot_path = fixtures / "snapshot-60.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    del snapshot["statistics"]["totalResults"]
    snapshot["data"][0]["prizes"] = None
    write_json(snapshot_path, snapshot)

    report = verify_fixture_directory(fixtures)

    assert report.valid_ranges == set()
    assert any("schemaVersion" in error for error in report.errors)
    assert any("generatedAt" in error for error in report.errors)
    assert any("snapshot key for 90" in error for error in report.errors)
    assert any("statistics is missing keys" in error for error in report.errors)
    assert any("prizes must be an object" in error for error in report.errors)
