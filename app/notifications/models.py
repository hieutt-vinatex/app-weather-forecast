"""Pure domain helpers for evaluating and formatting absence alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.schemas.gdb import SnapshotResponse


@dataclass(frozen=True)
class AbsenceCandidate:
    number: str
    days_absent: int
    last_seen: date


@dataclass(frozen=True)
class AlertEvaluation:
    status: str
    reference_date: date | None = None
    due_at: datetime | None = None
    candidates: tuple[AbsenceCandidate, ...] = ()
    reason: str | None = None

    @property
    def event_key(self) -> str | None:
        if self.reference_date is None:
            return None
        return self.reference_date.isoformat()


def evaluate_snapshot(
    snapshot: SnapshotResponse,
    *,
    now: datetime,
    min_days: int,
    max_days: int,
    send_time,
) -> AlertEvaluation:
    """Evaluate a snapshot without making any network or persistence changes.

    Exact 19–25 day claims require every draw in that lookback window to be
    complete. This prevents a missing result page from becoming a false alert.
    """
    complete_records = [record for record in snapshot.data if record.draw_complete]
    if not complete_records:
        return AlertEvaluation(status="waiting", reason="no_complete_draw")

    latest = max(complete_records, key=lambda record: record.date)
    try:
        reference_date = date.fromisoformat(latest.date)
    except ValueError:
        return AlertEvaluation(status="waiting", reason="invalid_reference_date")

    due_at = datetime.combine(
        reference_date + timedelta(days=1),
        send_time,
        tzinfo=now.tzinfo,
    )
    if now < due_at:
        return AlertEvaluation(
            status="not_due",
            reference_date=reference_date,
            due_at=due_at,
        )
    if now.date() > due_at.date():
        return AlertEvaluation(
            status="expired",
            reference_date=reference_date,
            due_at=due_at,
            reason="latest_complete_draw_is_too_old",
        )

    complete_dates = {record.date for record in complete_records}
    required_dates = {
        (reference_date - timedelta(days=offset)).isoformat()
        for offset in range(max_days + 1)
    }
    missing = sorted(required_dates - complete_dates)
    if missing:
        return AlertEvaluation(
            status="waiting",
            reference_date=reference_date,
            due_at=due_at,
            reason=f"incomplete_coverage:{','.join(missing[:3])}",
        )

    # Recompute from complete records through the reference date. Snapshot
    # statistics may already include a partially published newer draw while a
    # previous day's alert is being caught up.
    last_seen_by_number: dict[str, date] = {}
    for record in complete_records:
        try:
            record_date = date.fromisoformat(record.date)
        except ValueError:
            continue
        if record_date > reference_date:
            continue
        for values in record.prizes.model_dump().values():
            for value in values:
                if len(value) >= 2 and value[-2:].isdigit():
                    last_seen_by_number[value[-2:]] = max(
                        record_date,
                        last_seen_by_number.get(value[-2:], record_date),
                    )

    candidates: list[AbsenceCandidate] = []
    for number, last_seen in last_seen_by_number.items():
        days_absent = (reference_date - last_seen).days
        if min_days <= days_absent <= max_days:
            candidates.append(
                AbsenceCandidate(
                    number=number,
                    days_absent=days_absent,
                    last_seen=last_seen,
                )
            )

    candidates.sort(key=lambda item: (-item.days_absent, item.number))
    return AlertEvaluation(
        status="ready" if candidates else "no_match",
        reference_date=reference_date,
        due_at=due_at,
        candidates=tuple(candidates),
    )


def evaluate_snapshot_now(
    snapshot: SnapshotResponse,
    *,
    now: datetime,
    min_days: int,
    max_days: int,
) -> AlertEvaluation:
    """Evaluate the latest complete draw immediately, ignoring the 09:00 schedule.

    The regular scheduler is intentionally restricted to the morning after a
    draw. A user-triggered report instead evaluates whatever the latest
    complete draw is at click time while preserving the same completeness and
    19–25 day calculation rules.
    """
    complete_records = [record for record in snapshot.data if record.draw_complete]
    if not complete_records:
        return AlertEvaluation(status="waiting", reason="no_complete_draw")

    latest = max(complete_records, key=lambda record: record.date)
    try:
        reference_date = date.fromisoformat(latest.date)
    except ValueError:
        return AlertEvaluation(status="waiting", reason="invalid_reference_date")

    # Evaluate at the exact due instant for this reference draw. This bypasses
    # only the scheduler's not-due/expired gates; all data coverage and absence
    # calculations continue to use the shared implementation above.
    evaluation_time = datetime.combine(
        reference_date + timedelta(days=1),
        time.min,
        tzinfo=now.tzinfo,
    )
    return evaluate_snapshot(
        snapshot,
        now=evaluation_time,
        min_days=min_days,
        max_days=max_days,
        send_time=time.min,
    )


def format_alert_message(
    evaluation: AlertEvaluation,
    *,
    min_days: int,
    max_days: int,
) -> str:
    if evaluation.reference_date is None or not evaluation.candidates:
        raise ValueError("A ready evaluation with candidates is required")

    grouped: dict[int, list[str]] = {}
    for item in evaluation.candidates:
        grouped.setdefault(item.days_absent, []).append(item.number)

    lines = [
        f"🔔 XSMB · số chưa xuất hiện {min_days}–{max_days} ngày",
        f"Kỳ dữ liệu: {evaluation.reference_date.strftime('%d/%m/%Y')}",
        f"Tổng cộng: {len(evaluation.candidates)} số",
        "",
    ]
    for days in sorted(grouped, reverse=True):
        lines.append(f"{days} ngày: {', '.join(grouped[days])}")
    lines.extend(
        [
            "",
            "Dữ liệu gồm hai số cuối của ĐB và G1–G7.",
            "Chỉ dùng để thống kê, không phải dự đoán kết quả.",
        ]
    )
    return "\n".join(lines)


def format_immediate_report_message(
    evaluation: AlertEvaluation,
    *,
    checked_at: datetime,
    min_days: int,
    max_days: int,
) -> str:
    """Format a user-triggered report, including a valid zero-match result."""
    if evaluation.reference_date is None or evaluation.status not in {
        "ready",
        "no_match",
    }:
        raise ValueError("A complete immediate evaluation is required")

    checked_line = f"Kiểm tra lúc: {checked_at.strftime('%d/%m/%Y %H:%M:%S')}"
    if evaluation.candidates:
        return "\n".join(
            [
                format_alert_message(
                    evaluation,
                    min_days=min_days,
                    max_days=max_days,
                ),
                checked_line,
            ]
        )

    return "\n".join(
        [
            f"🔔 XSMB · số chưa xuất hiện {min_days}–{max_days} ngày",
            f"Kỳ dữ liệu: {evaluation.reference_date.strftime('%d/%m/%Y')}",
            "Kết quả: không có số nào nằm trong khoảng này.",
            checked_line,
            "",
            "Dữ liệu gồm hai số cuối của ĐB và G1–G7.",
            "Chỉ dùng để thống kê, không phải dự đoán kết quả.",
        ]
    )
