from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.cloud.contracts import DailyDataUpdateState, JobRecord
from app.cloud.publisher import SnapshotPublisher
from app.services.gdb_service import DayOutcome
from app.services.snapshot_builder import SnapshotBuildContext
from app.utils.parser import PRIZE_COUNTS
from scripts.verify_cloud_contracts import (
    verify_fixture_directory,
    verify_publication_root,
)


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
    path.parent.mkdir(parents=True, exist_ok=True)
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


async def published_tree(root: Path) -> tuple[Path, str, str]:
    flat_root = root / "flat"
    flat_root.mkdir()
    flat = await published_fixture(flat_root)
    manifest = json.loads((flat / "manifest.json").read_text(encoding="utf-8"))
    active = manifest["version"]
    previous = "20261028T110500000000Z"
    manifest["previousPublication"] = {
        "version": previous,
        "generatedAt": "2026-10-28T11:05:00Z",
        "snapshotKeys": {
            str(days): f"snapshot:v1:{previous}:{days}" for days in (30, 60, 90)
        },
        "sourceReferenceDate": "2026-10-28",
        "complete": True,
        "lastJob": manifest["lastJob"],
    }
    data_root = root / "publication/site/data"
    active_root = data_root / "versions" / active
    previous_root = data_root / "versions" / previous
    active_root.mkdir(parents=True)
    previous_root.mkdir(parents=True)
    write_json(data_root / "manifest.json", manifest)
    write_json(data_root / "status.json", manifest["lastJob"])
    for filename in ("history.json", "snapshot-30.json", "snapshot-60.json", "snapshot-90.json"):
        value = json.loads((flat / filename).read_text(encoding="utf-8"))
        write_json(active_root / filename, value)
        write_json(previous_root / filename, value)
    (root / "publication/site/index.html").write_text("dashboard", encoding="utf-8")
    write_json(
        root / "publication/state/telegram-ledger.json",
        {
            "version": 1,
            "events": {
                "2026-10-29:absence": {
                    "targets": {
                        f"telegram:chat:{'a' * 64}": "2026-10-29T11:05:00+00:00"
                    },
                    "updatedAt": "2026-10-29T11:05:00+00:00",
                }
            },
            "providers": {},
        },
    )
    return root / "publication", active, previous


async def test_publication_root_verifier_checks_active_previous_status_and_ledger(
    tmp_path: Path,
):
    publication, _, _ = await published_tree(tmp_path)

    report = verify_publication_root(publication)

    assert report.valid_ranges == {30, 60, 90}
    assert report.errors == []


@pytest.mark.parametrize(
    ("status", "extra"),
    [
        ("pending", {}),
        (
            "failed",
            {
                "initialFailureAt": "2026-11-03T18:45:30+07:00",
                "lastReason": "invalid_upstream_data",
            },
        ),
        (
            "succeeded",
            {
                "publishedVersion": "20261103T114500000000Z",
                "sourceReferenceDate": "2026-11-03",
            },
        ),
    ],
)
def test_daily_update_state_accepts_each_valid_status(status: str, extra: dict):
    raw = {
        "schemaVersion": 1,
        "businessDate": "2026-11-03",
        "status": status,
        "attemptCount": 1,
        "firstAttemptAt": "2026-11-03T18:45:00+07:00",
        "lastAttemptAt": "2026-11-03T18:45:30+07:00",
        **extra,
    }

    state = DailyDataUpdateState.model_validate(raw)

    assert state.model_dump(mode="json", by_alias=True)["status"] == status


@pytest.mark.parametrize(
    "update",
    [
        {"attemptCount": -1},
        {"firstAttemptAt": "2026-11-03T18:45:00"},
        {"status": "succeeded"},
        {"lastReason": "https://source.example/private?token=raw"},
        {"exception": "upstream response body"},
        {"botToken": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"},
        {"chatId": "-1001234567890"},
    ],
)
def test_daily_update_state_rejects_unsafe_or_incomplete_values(update: dict):
    raw = {
        "schemaVersion": 1,
        "businessDate": "2026-11-03",
        "status": "pending",
        "attemptCount": 1,
        "firstAttemptAt": "2026-11-03T18:45:00+07:00",
        "lastAttemptAt": "2026-11-03T18:45:30+07:00",
        **update,
    }

    with pytest.raises(ValidationError):
        DailyDataUpdateState.model_validate(raw)


async def test_publication_verifier_validates_daily_update_state(tmp_path: Path):
    publication, _, _ = await published_tree(tmp_path)
    write_json(
        publication / "state/daily-data-update.json",
        {
            "schemaVersion": 1,
            "businessDate": "2026-11-03",
            "status": "succeeded",
            "attemptCount": 2,
            "firstAttemptAt": "2026-11-03T18:45:00+07:00",
            "lastAttemptAt": "2026-11-03T19:45:00+07:00",
            "initialFailureAt": "2026-11-03T18:45:30+07:00",
            "publishedVersion": "20261103T124500000000Z",
            "sourceReferenceDate": "2026-11-03",
        },
    )

    report = verify_publication_root(publication)

    assert report.errors == []


async def test_publication_verifier_reports_daily_state_without_echoing_payload(
    tmp_path: Path,
):
    publication, _, _ = await published_tree(tmp_path)
    secret = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    write_json(
        publication / "state/daily-data-update.json",
        {
            "schemaVersion": 1,
            "businessDate": "2026-11-03",
            "status": "failed",
            "attemptCount": 1,
            "firstAttemptAt": "2026-11-03T18:45:00+07:00",
            "lastAttemptAt": "2026-11-03T18:45:30+07:00",
            "initialFailureAt": "2026-11-03T18:45:30+07:00",
            "lastReason": secret,
        },
    )

    report = verify_publication_root(publication, secret_values=(secret,))

    assert any("daily-data-update.json" in error for error in report.errors)
    assert all(secret not in error for error in report.errors)


async def test_publication_root_verifier_rejects_broken_paths_and_retention(
    tmp_path: Path,
):
    publication, active, previous = await published_tree(tmp_path)
    data_root = publication / "site/data"
    manifest_path = data_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["snapshotKeys"]["30"] = f"snapshot:v1:{previous}:30"
    write_json(manifest_path, manifest)
    (data_root / "versions" / previous / "snapshot-90.json").unlink()
    for version in ("20261027T110500000000Z", "20261026T110500000000Z"):
        version_root = data_root / "versions" / version
        version_root.mkdir(parents=True)
        for filename in ("history.json", "snapshot-30.json", "snapshot-60.json", "snapshot-90.json"):
            (version_root / filename).write_text(
                (data_root / "versions" / active / filename).read_text(encoding="utf-8"),
                encoding="utf-8",
            )

    report = verify_publication_root(publication)

    assert report.valid_ranges != {30, 60, 90}
    assert any("active snapshot path" in error for error in report.errors)
    assert any("previous snapshot" in error for error in report.errors)
    assert any("retained versions" in error for error in report.errors)


async def test_publication_root_verifier_rejects_invalid_status_ledger_and_secrets(
    tmp_path: Path,
):
    publication, active, _ = await published_tree(tmp_path)
    data_root = publication / "site/data"
    history_path = data_root / "versions" / active / "history.json"
    history = json.loads(history_path.read_text(encoding="utf-8"))
    history.append(deepcopy(history[-1]))
    write_json(history_path, history)
    write_json(data_root / "status.json", {"kind": "data", "status": "unknown"})
    write_json(
        publication / "state/telegram-ledger.json",
        {
            "version": 1,
            "events": {
                "2026-10-29:absence": {
                    "targets": {"telegram:chat:123456789": "not-a-time"}
                }
            },
            "providers": {"telegram": {"chatId": "123456789"}},
        },
    )
    secrets = (
        "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef",
        "-1001234567890",
        "ledger-hmac-secret-value",
    )
    (publication / "site/assets").mkdir()
    (publication / "site/assets/app.js").write_text(
        " ".join(secrets), encoding="utf-8"
    )

    report = verify_publication_root(publication, secret_values=secrets)

    assert any("history cannot exceed 90" in error for error in report.errors)
    assert any("status.json" in error for error in report.errors)
    assert any("telegram-ledger.json" in error for error in report.errors)
    assert any("secret material" in error for error in report.errors)
    assert all(secret not in error for error in report.errors for secret in secrets)


async def test_publication_secret_scan_splits_comma_separated_chat_ids(tmp_path: Path):
    publication, _, _ = await published_tree(tmp_path)
    chat_ids = "-1001234567890,987654321"
    (publication / "site/index.html").write_text(
        "recipient=987654321", encoding="utf-8"
    )

    report = verify_publication_root(publication, secret_values=(chat_ids,))

    assert any("secret material" in error for error in report.errors)
    assert all("987654321" not in error for error in report.errors)
