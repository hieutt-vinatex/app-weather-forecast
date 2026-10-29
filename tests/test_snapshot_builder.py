from datetime import date, datetime, timezone

import pytest

from app.services.gdb_service import DayOutcome
from app.services.snapshot_builder import SnapshotBuildContext, assemble_snapshot
from app.utils.parser import PRIZE_COUNTS


def _complete_prizes(seed: int) -> dict[str, tuple[str, ...]]:
    return {
        prize: tuple(
            f"{(seed + offset) % 100:02d}" for offset in range(expected_count)
        )
        for prize, expected_count in PRIZE_COUNTS.items()
    }


@pytest.fixture
def context() -> SnapshotBuildContext:
    fetched_at = datetime(2026, 10, 29, 18, 5, tzinfo=timezone.utc)
    return SnapshotBuildContext(
        fetched_at=fetched_at,
        last_source_check_at=fetched_at,
        last_successful_check_at=fetched_at,
        last_changed_at=fetched_at,
        snapshot_version=7,
        source="example.test",
        poll_interval_seconds=30,
        realtime_enabled=True,
        cached=True,
    )


def test_assemble_snapshot_preserves_current_contract_and_sorts_dates(context):
    outcomes = [
        DayOutcome(
            day=date(2026, 10, 29),
            source_url="https://example.test/2026-10-29",
            prizes={"db": ("34",)},
            gdb="34",
            complete=False,
            ok=True,
        ),
        DayOutcome(
            day=date(2026, 10, 28),
            source_url="https://example.test/2026-10-28",
            prizes=_complete_prizes(10),
            gdb="10",
            complete=True,
            ok=True,
        ),
    ]

    snapshot = assemble_snapshot(30, outcomes, context)

    assert [record.date for record in snapshot.data] == ["2026-10-28", "2026-10-29"]
    assert snapshot.meta.requested_days == 30
    assert snapshot.meta.incomplete_dates == ["2026-10-29"]
    assert snapshot.meta.cached is True
    assert snapshot.meta.snapshot_version == 7
    assert set(snapshot.statistics_by_prize) == {
        "db",
        "g1",
        "g2",
        "g3",
        "g4",
        "g5",
        "g6",
        "g7",
    }


def test_assemble_snapshot_rejects_unsupported_days(context):
    with pytest.raises(ValueError, match="30, 60, or 90"):
        assemble_snapshot(31, [], context)
