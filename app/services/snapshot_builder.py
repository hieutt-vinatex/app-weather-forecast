"""Pure assembly of resolved draw outcomes into public snapshot responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Sequence

from app.schemas.gdb import (
    GdbRecord,
    Meta,
    PrizeResults,
    RecordError,
    SnapshotResponse,
)
from app.services.statistics_service import ValidRecord, compute_statistics
from app.utils.date_helper import to_label, weekday_name_vi
from app.utils.parser import PRIZE_COUNTS, PRIZE_KEYS

if TYPE_CHECKING:
    from app.services.gdb_service import DayOutcome


@dataclass(frozen=True)
class SnapshotBuildContext:
    fetched_at: datetime
    last_source_check_at: datetime | None
    last_successful_check_at: datetime | None
    last_changed_at: datetime | None
    snapshot_version: int
    source: str
    poll_interval_seconds: float = 0.0
    realtime_enabled: bool = False
    cached: bool = True
    stale: bool = False


def assemble_snapshot(
    days: int,
    outcomes: Sequence[DayOutcome],
    context: SnapshotBuildContext,
) -> SnapshotResponse:
    """Build a deterministic public snapshot from already-resolved outcomes."""
    if days not in (30, 60, 90):
        raise ValueError("days must be 30, 60, or 90")

    records: list[GdbRecord] = []
    valid_all: list[ValidRecord] = []
    valid_by_prize: dict[str, list[ValidRecord]] = {
        prize: [] for prize in PRIZE_KEYS
    }
    errors: list[RecordError] = []
    missing: list[str] = []
    incomplete: list[str] = []

    for outcome in sorted(outcomes, key=lambda item: item.day):
        if outcome.ok and outcome.result_count > 0:
            prize_values = {
                prize: list(outcome.prizes.get(prize, ())) for prize in PRIZE_KEYS
            }
            records.append(
                GdbRecord(
                    gdb=outcome.gdb,
                    prizes=PrizeResults(**prize_values),
                    draw_complete=outcome.complete,
                    date=outcome.date_iso,
                    date_label=to_label(outcome.day),
                    day_name=weekday_name_vi(outcome.day),
                    source_url=outcome.source_url,
                )
            )
            if not outcome.complete:
                incomplete.append(outcome.date_iso)
            for prize, values in prize_values.items():
                for value in values:
                    record = ValidRecord(gdb=value[-2:], date_iso=outcome.date_iso)
                    valid_all.append(record)
                    valid_by_prize[prize].append(record)
        else:
            missing.append(outcome.date_iso)
            errors.append(
                RecordError(date=outcome.date_iso, reason=outcome.reason or "unknown")
            )

    statistics = compute_statistics(
        valid_all,
        attempted_days=days,
        expected_results_per_day=sum(PRIZE_COUNTS.values()),
    )
    statistics_by_prize = {
        prize: compute_statistics(
            valid_by_prize[prize],
            attempted_days=days,
            expected_results_per_day=PRIZE_COUNTS[prize],
        )
        for prize in PRIZE_KEYS
    }

    return SnapshotResponse(
        data=records,
        statistics=statistics,
        statistics_by_prize=statistics_by_prize,
        meta=Meta(
            requested_days=days,
            available_records=len(records),
            failed_count=len(errors),
            missing_dates=missing,
            incomplete_dates=incomplete,
            available_numbers=len(valid_all),
            errors=errors,
            partial=bool(errors or incomplete),
            cached=context.cached,
            stale=context.stale,
            fetched_at=context.fetched_at,
            last_source_check_at=context.last_source_check_at,
            last_successful_check_at=context.last_successful_check_at,
            last_changed_at=context.last_changed_at,
            snapshot_version=context.snapshot_version,
            poll_interval_seconds=context.poll_interval_seconds,
            realtime_enabled=context.realtime_enabled,
            source=context.source,
        ),
    )
