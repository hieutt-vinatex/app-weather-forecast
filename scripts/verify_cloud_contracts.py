#!/usr/bin/env python3
"""Offline verification for versioned cloud publication fixtures."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cloud.contracts import DailyDataUpdateState  # noqa: E402


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
    "NOTIFICATION_LEDGER_HMAC_KEY",
}
BOT_TOKEN_PATTERN = re.compile(rb"\b[0-9]{6,}:[A-Za-z0-9_-]{20,}\b")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
PATH_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
LEDGER_TARGET_PATTERN = re.compile(r"^telegram:[a-z_]+:[0-9a-f]{64}$")


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


def verify_publication_root(
    publication_root: str | Path,
    *,
    max_value_bytes: int = MAX_VALUE_BYTES,
    secret_values: Iterable[str] | None = None,
) -> VerificationReport:
    """Validate the complete filesystem publication used by GitHub Actions."""
    if max_value_bytes <= 0:
        raise ValueError("max_value_bytes must be positive")

    root = Path(publication_root)
    data_root = root / "site/data"
    report = VerificationReport()
    secrets = _secret_values(secret_values)
    report.errors.extend(_scan_publication_files(root, secrets))

    manifest, load_errors = _load_json_value(
        data_root / "manifest.json",
        max_value_bytes=max_value_bytes,
        secret_values=(),
    )
    report.errors.extend(load_errors)
    manifest_errors = _validate_manifest(manifest)
    report.errors.extend(manifest_errors)

    status, status_load_errors = _load_json_value(
        data_root / "status.json",
        max_value_bytes=max_value_bytes,
        secret_values=(),
    )
    report.errors.extend(status_load_errors)
    report.errors.extend(_validate_job_status(status))

    versions_root = data_root / "versions"
    version_dirs = (
        sorted(
            path.name
            for path in versions_root.iterdir()
            if path.is_dir() and not path.is_symlink()
        )
        if versions_root.is_dir()
        else []
    )
    if len(version_dirs) > 3:
        report.errors.append("versions: retained versions cannot exceed three")
    if any(not PATH_VERSION_PATTERN.fullmatch(version) for version in version_dirs):
        report.errors.append("versions: retained version name is invalid")

    if isinstance(manifest, dict):
        report.errors.extend(
            _verify_manifest_paths(
                data_root,
                manifest,
                max_value_bytes=max_value_bytes,
                report=report,
            )
        )

    ledger_path = root / "state/telegram-ledger.json"
    if ledger_path.exists():
        ledger, ledger_load_errors = _load_json_value(
            ledger_path,
            max_value_bytes=max_value_bytes,
            secret_values=(),
        )
        report.errors.extend(ledger_load_errors)
        report.errors.extend(_validate_telegram_ledger(ledger))

    daily_state_path = root / "state/daily-data-update.json"
    if daily_state_path.exists():
        daily_state, daily_state_load_errors = _load_json_value(
            daily_state_path,
            max_value_bytes=max_value_bytes,
            secret_values=(),
        )
        report.errors.extend(daily_state_load_errors)
        if not daily_state_load_errors:
            try:
                DailyDataUpdateState.model_validate(daily_state)
            except (ValidationError, TypeError, ValueError):
                report.errors.append(
                    "daily-data-update.json: state contract is invalid"
                )

    if report.errors:
        report.valid_ranges.clear()
    return report


def _verify_manifest_paths(
    data_root: Path,
    manifest: Mapping[str, Any],
    *,
    max_value_bytes: int,
    report: VerificationReport,
) -> list[str]:
    errors: list[str] = []
    version = manifest.get("version")
    if not isinstance(version, str) or not PATH_VERSION_PATTERN.fullmatch(version):
        return ["manifest.json: active version cannot resolve to a safe path"]
    version_root = data_root / "versions" / version
    expected_history_key = f"history:v1:{version}"
    if manifest.get("historyKey") != expected_history_key:
        errors.append("manifest.json: active history path does not match version")

    history, history_load_errors = _load_json_value(
        version_root / "history.json",
        max_value_bytes=max_value_bytes,
        secret_values=(),
    )
    errors.extend(history_load_errors)
    errors.extend(_validate_history(history))

    snapshot_keys = manifest.get("snapshotKeys")
    for days in VALID_RANGES:
        expected_key = f"snapshot:v1:{version}:{days}"
        if (
            not isinstance(snapshot_keys, dict)
            or snapshot_keys.get(str(days)) != expected_key
        ):
            errors.append(
                f"manifest.json: active snapshot path for {days} days does not match version"
            )
        snapshot, snapshot_load_errors = _load_json_value(
            version_root / f"snapshot-{days}.json",
            max_value_bytes=max_value_bytes,
            secret_values=(),
        )
        errors.extend(snapshot_load_errors)
        range_errors = _validate_public_snapshot(
            shape_worker_snapshot(snapshot, manifest), days
        )
        errors.extend(range_errors)
        if not history_load_errors and not snapshot_load_errors and not range_errors:
            report.valid_ranges.add(days)

    previous = manifest.get("previousPublication")
    if previous is not None:
        errors.extend(_verify_previous_paths(data_root, previous))
    return errors


def _verify_previous_paths(data_root: Path, previous: Any) -> list[str]:
    if not isinstance(previous, dict):
        return ["manifest.json: previous publication must be an object or null"]
    version = previous.get("version")
    if not isinstance(version, str) or not PATH_VERSION_PATTERN.fullmatch(version):
        return ["manifest.json: previous publication version is invalid"]
    errors: list[str] = []
    if not _is_timestamp(previous.get("generatedAt")):
        errors.append("manifest.json: previous generatedAt is invalid")
    reference_date = previous.get("sourceReferenceDate")
    if reference_date is not None and not _is_date(reference_date):
        errors.append("manifest.json: previous sourceReferenceDate is invalid")
    if not isinstance(previous.get("complete"), bool):
        errors.append("manifest.json: previous complete must be boolean")
    last_job = previous.get("lastJob")
    if not isinstance(last_job, dict) or not _nonempty_string(last_job.get("status")):
        errors.append("manifest.json: previous lastJob.status is invalid")
    keys = previous.get("snapshotKeys")
    for days in VALID_RANGES:
        expected = f"snapshot:v1:{version}:{days}"
        if not isinstance(keys, dict) or keys.get(str(days)) != expected:
            errors.append(
                f"manifest.json: previous snapshot path for {days} days does not match version"
            )
        path = data_root / "versions" / version / f"snapshot-{days}.json"
        if not path.is_file():
            errors.append(f"snapshot-{days}.json: previous snapshot is missing")
    return errors


def _validate_job_status(value: Any) -> list[str]:
    label = "status.json"
    if not isinstance(value, dict):
        return [f"{label}: job status must be an object"]
    errors: list[str] = []
    if value.get("kind") != "data":
        errors.append(f"{label}: kind must equal data")
    if not _nonempty_string(value.get("mode")):
        errors.append(f"{label}: mode is invalid")
    if value.get("status") not in {"running", "succeeded", "failed"}:
        errors.append(f"{label}: status is invalid")
    if not _is_timestamp(value.get("startedAt")):
        errors.append(f"{label}: startedAt is invalid")
    finished_at = value.get("finishedAt")
    if finished_at is not None and not _is_timestamp(finished_at):
        errors.append(f"{label}: finishedAt is invalid")
    record_count = value.get("recordCount")
    if (
        isinstance(record_count, bool)
        or not isinstance(record_count, int)
        or record_count < 0
    ):
        errors.append(f"{label}: recordCount is invalid")
    return errors


def _validate_telegram_ledger(value: Any) -> list[str]:
    label = "telegram-ledger.json"
    if not isinstance(value, dict):
        return [f"{label}: ledger must be an object"]
    errors: list[str] = []
    if value.get("version") != 1:
        errors.append(f"{label}: version must equal 1")
    events = value.get("events")
    if not isinstance(events, dict):
        return [*errors, f"{label}: events must be an object"]
    providers = value.get("providers")
    if providers != {}:
        errors.append(f"{label}: providers must be empty")
    for event_key, event in events.items():
        if not _nonempty_string(event_key) or not isinstance(event, dict):
            errors.append(f"{label}: event entry is invalid")
            continue
        targets = event.get("targets", {})
        if not isinstance(targets, dict):
            errors.append(f"{label}: event targets must be an object")
        else:
            for target_key, sent_at in targets.items():
                if (
                    not isinstance(target_key, str)
                    or not LEDGER_TARGET_PATTERN.fullmatch(target_key)
                ):
                    errors.append(f"{label}: target identifier is not an HMAC key")
                if not _is_timestamp(sent_at):
                    errors.append(f"{label}: target timestamp is invalid")
        updated_at = event.get("updatedAt")
        if updated_at is not None and not _is_timestamp(updated_at):
            errors.append(f"{label}: updatedAt is invalid")
        no_match = event.get("noMatch")
        if no_match is not None and not isinstance(no_match, bool):
            errors.append(f"{label}: noMatch must be boolean")
    return errors


def _scan_publication_files(root: Path, secrets: tuple[bytes, ...]) -> list[str]:
    errors: list[str] = []
    for area in (root / "site", root / "state"):
        if not area.exists():
            continue
        for path in sorted(area.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                errors.append(f"{path.relative_to(root).as_posix()}: file could not be read")
                continue
            if _contains_secret_material(raw, secrets):
                errors.append(
                    f"{path.relative_to(root).as_posix()}: secret material is not allowed"
                )
    return errors


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
    expanded: list[str] = []
    for value in candidates:
        if not isinstance(value, str):
            continue
        expanded.append(value)
        expanded.extend(part.strip() for part in value.split(","))
    return tuple(
        value.encode("utf-8")
        for value in expanded
        if len(value) >= 8
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
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--publication-root", type=Path)
    parser.add_argument("--max-value-bytes", type=int, default=MAX_VALUE_BYTES)
    args = parser.parse_args(argv)
    if args.publication_root is not None and args.directory is not None:
        parser.error("choose either directory or --publication-root")
    if args.publication_root is not None:
        report = verify_publication_root(
            args.publication_root,
            max_value_bytes=args.max_value_bytes,
        )
    elif args.directory is not None:
        report = verify_fixture_directory(
            args.directory,
            max_value_bytes=args.max_value_bytes,
        )
    else:
        parser.error("directory or --publication-root is required")
    if report.errors:
        for error in report.errors:
            print(f"ERROR: {error}")
        return 1
    ranges = ",".join(str(days) for days in sorted(report.valid_ranges))
    print(f"Cloud publication contracts valid for ranges: {ranges}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
