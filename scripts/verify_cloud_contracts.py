#!/usr/bin/env python3
"""Offline verification for versioned cloud publication fixtures."""

from __future__ import annotations

import argparse
import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


VALID_RANGES = (30, 60, 90)
MAX_VALUE_BYTES = 20 * 1024 * 1024
PRIZE_KEYS = {"db", "g1", "g2", "g3", "g4", "g5", "g6", "g7"}
FRESHNESS_STATES = {"current", "updating", "delayed", "stale"}
STATISTICS_KEYS = {
    "totalResults",
    "availableDraws",
    "expectedResults",
    "expectedResultsPerDraw",
    "averageResultsPerDraw",
    "uniqueNumbers",
    "collectionSuccessRate",
    "frequencies",
    "topNumbers",
    "coldNumbers",
    "tensDigitFrequency",
    "unitsDigitFrequency",
    "evenOdd",
}
SECRET_NAMES = {
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_KV_NAMESPACE_ID",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_IDS",
    "NOTIFICATION_ADMIN_TOKEN",
    "GITHUB_DISPATCH_TOKEN",
}
BOT_TOKEN_PATTERN = re.compile(rb"\b[0-9]{6,}:[A-Za-z0-9_-]{20,}\b")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass
class VerificationReport:
    valid_ranges: set[int] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


def verify_fixture_directory(
    directory: str | Path,
    *,
    max_value_bytes: int = MAX_VALUE_BYTES,
    secret_values: Iterable[str] | None = None,
) -> VerificationReport:
    """Validate an exported KV publication without contacting cloud services."""
    if max_value_bytes <= 0:
        raise ValueError("max_value_bytes must be positive")

    root = Path(directory)
    report = VerificationReport()
    values = _secret_values(secret_values)
    loaded: dict[str, Any] = {}
    file_errors: dict[str, list[str]] = {}
    filenames = [
        "manifest.json",
        "history.json",
        *(f"snapshot-{days}.json" for days in VALID_RANGES),
    ]
    for filename in filenames:
        value, errors = _load_json_value(
            root / filename,
            max_value_bytes=max_value_bytes,
            secret_values=values,
        )
        loaded[filename] = value
        file_errors[filename] = errors
        report.errors.extend(errors)

    manifest_errors = _validate_manifest(loaded["manifest.json"])
    history_errors = _validate_history(loaded["history.json"])
    report.errors.extend(manifest_errors)
    report.errors.extend(history_errors)

    manifest = loaded["manifest.json"]
    for days in VALID_RANGES:
        filename = f"snapshot-{days}.json"
        range_errors: list[str] = []
        snapshot = loaded[filename]
        if isinstance(manifest, dict):
            shaped = shape_worker_snapshot(snapshot, manifest)
            range_errors.extend(_validate_public_snapshot(shaped, days))
        else:
            range_errors.append(f"{filename}: cannot shape without a valid manifest")
        report.errors.extend(range_errors)
        if not (
            file_errors["manifest.json"]
            or file_errors["history.json"]
            or file_errors[filename]
            or manifest_errors
            or history_errors
            or range_errors
        ):
            report.valid_ranges.add(days)

    return report


def shape_worker_snapshot(snapshot: Any, manifest: Mapping[str, Any]) -> Any:
    """Mirror the Worker's public response enrichment for offline fixtures."""
    if not isinstance(snapshot, dict):
        return snapshot
    shaped = deepcopy(snapshot)
    meta = shaped.get("meta")
    last_job = manifest.get("lastJob")
    if not isinstance(meta, dict) or not isinstance(last_job, dict):
        return shaped
    status = last_job.get("status")
    if status == "running":
        freshness = "updating"
    elif status == "failed":
        freshness = "delayed"
    else:
        freshness = "current"
    meta.update(
        {
            "generatedAt": manifest.get("generatedAt"),
            "freshnessStatus": freshness,
            "lastJobStatus": status,
        }
    )
    return shaped


def _load_json_value(
    path: Path,
    *,
    max_value_bytes: int,
    secret_values: tuple[bytes, ...],
) -> tuple[Any, list[str]]:
    errors: list[str] = []
    label = path.name
    try:
        size = path.stat().st_size
    except OSError:
        return None, [f"{label}: required fixture is missing"]
    if size > max_value_bytes:
        return None, [f"{label}: value exceeds the safe byte limit"]
    try:
        raw = path.read_bytes()
    except OSError:
        return None, [f"{label}: fixture could not be read"]
    if _contains_secret_material(raw, secret_values):
        errors.append(f"{label}: secret material is not allowed in cloud values")
    try:
        return json.loads(raw), errors
    except (json.JSONDecodeError, UnicodeDecodeError):
        errors.append(f"{label}: value is not valid UTF-8 JSON")
        return None, errors


def _validate_manifest(value: Any) -> list[str]:
    label = "manifest.json"
    if not isinstance(value, dict):
        return [f"{label}: manifest must be an object"]
    errors: list[str] = []
    required = {
        "schemaVersion",
        "version",
        "generatedAt",
        "historyKey",
        "snapshotKeys",
        "sourceReferenceDate",
        "complete",
        "lastJob",
    }
    if missing := sorted(required - value.keys()):
        errors.append(f"{label}: missing required keys: {', '.join(missing)}")
    if value.get("schemaVersion") != 1:
        errors.append(f"{label}: schemaVersion must equal 1")
    version = value.get("version")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        errors.append(f"{label}: version is invalid")
    if not _is_timestamp(value.get("generatedAt")):
        errors.append(f"{label}: generatedAt must be an offset-aware ISO timestamp")
    if not _nonempty_string(value.get("historyKey")):
        errors.append(f"{label}: historyKey is invalid")
    snapshot_keys = value.get("snapshotKeys")
    if not isinstance(snapshot_keys, dict):
        errors.append(f"{label}: snapshotKeys must be an object")
    else:
        for days in VALID_RANGES:
            if not _nonempty_string(snapshot_keys.get(str(days))):
                errors.append(f"{label}: snapshot key for {days} days is missing")
    reference_date = value.get("sourceReferenceDate")
    if reference_date is not None and not _is_date(reference_date):
        errors.append(f"{label}: sourceReferenceDate must be an ISO date or null")
    if not isinstance(value.get("complete"), bool):
        errors.append(f"{label}: complete must be boolean")
    last_job = value.get("lastJob")
    if not isinstance(last_job, dict) or not _nonempty_string(last_job.get("status")):
        errors.append(f"{label}: lastJob.status is invalid")
    return errors


def _validate_history(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["history.json: history must be an array"]
    errors: list[str] = []
    if len(value) > 90:
        errors.append("history.json: history cannot exceed 90 dates")
    dates = [item.get("day") if isinstance(item, dict) else None for item in value]
    if any(not _is_date(item) for item in dates):
        errors.append("history.json: every record must have a valid ISO day")
    elif dates != sorted(dates) or len(dates) != len(set(dates)):
        errors.append("history.json: dates must be sorted and unique")
    return errors


def _validate_public_snapshot(value: Any, days: int) -> list[str]:
    label = f"snapshot-{days}.json"
    if not isinstance(value, dict):
        return [f"{label}: snapshot must be an object"]
    errors: list[str] = []
    data = value.get("data")
    if not isinstance(data, list):
        errors.append(f"{label}: data must be an array")
    else:
        if len(data) > days or len(data) > 90:
            errors.append(f"{label}: data exceeds its requested date range")
        if any(
            not isinstance(item, dict) or not isinstance(item.get("prizes"), dict)
            for item in data
        ):
            errors.append(f"{label}: every record prizes must be an object")
        dates = [item.get("date") if isinstance(item, dict) else None for item in data]
        if any(not _is_date(item) for item in dates):
            errors.append(f"{label}: every record must have a valid ISO date")
        elif dates != sorted(dates) or len(dates) != len(set(dates)):
            errors.append(f"{label}: dates must be sorted and unique")

    statistics = value.get("statistics")
    errors.extend(_validate_statistics(statistics, f"{label}: statistics"))
    by_prize = value.get("statisticsByPrize")
    if not isinstance(by_prize, dict):
        errors.append(f"{label}: statisticsByPrize must be an object")
    else:
        missing_prizes = sorted(PRIZE_KEYS - by_prize.keys())
        if missing_prizes:
            errors.append(
                f"{label}: statisticsByPrize is missing: {', '.join(missing_prizes)}"
            )
        for prize in sorted(PRIZE_KEYS & by_prize.keys()):
            errors.extend(
                _validate_statistics(
                    by_prize[prize],
                    f"{label}: statisticsByPrize.{prize}",
                )
            )

    meta = value.get("meta")
    if not isinstance(meta, dict):
        errors.append(f"{label}: meta must be an object")
        return errors
    if meta.get("requestedDays") != days:
        errors.append(f"{label}: meta.requestedDays does not match the range")
    version = meta.get("snapshotVersion")
    if isinstance(version, bool) or not isinstance(version, int):
        errors.append(f"{label}: meta.snapshotVersion must be an integer")
    if not _is_timestamp(meta.get("generatedAt")):
        errors.append(f"{label}: meta.generatedAt is invalid")
    if meta.get("freshnessStatus") not in FRESHNESS_STATES:
        errors.append(f"{label}: meta.freshnessStatus is invalid")
    if not _nonempty_string(meta.get("lastJobStatus")):
        errors.append(f"{label}: meta.lastJobStatus is invalid")
    return errors


def _validate_statistics(value: Any, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    if missing := sorted(STATISTICS_KEYS - value.keys()):
        return [f"{label} is missing keys: {', '.join(missing)}"]
    return []


def _contains_secret_material(raw: bytes, secret_values: tuple[bytes, ...]) -> bool:
    if BOT_TOKEN_PATTERN.search(raw):
        return True
    if any(name.encode("utf-8") in raw for name in SECRET_NAMES):
        return True
    return any(value in raw for value in secret_values)


def _secret_values(values: Iterable[str] | None) -> tuple[bytes, ...]:
    candidates = list(values or ())
    candidates.extend(os.environ.get(name, "") for name in SECRET_NAMES)
    return tuple(
        value.encode("utf-8")
        for value in candidates
        if isinstance(value, str) and len(value) >= 8
    )


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _is_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify exported manifest/history/snapshot cloud fixtures."
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--max-value-bytes", type=int, default=MAX_VALUE_BYTES)
    args = parser.parse_args(argv)
    report = verify_fixture_directory(
        args.directory,
        max_value_bytes=args.max_value_bytes,
    )
    if report.errors:
        for error in report.errors:
            print(f"ERROR: {error}")
        return 1
    ranges = ",".join(str(days) for days in sorted(report.valid_ranges))
    print(f"Cloud publication contracts valid for ranges: {ranges}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
