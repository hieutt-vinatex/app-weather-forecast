"""Pure domain helpers for evaluating and formatting absence alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.cloud.contracts import DailyDataUpdateState
from app.schemas.gdb import SnapshotResponse


@dataclass(frozen=True)
class AbsenceCandidate:
    number: str
    days_absent: int
    last_seen: date | None
    is_lower_bound: bool = False


@dataclass(frozen=True)
class DailyUpdateWarning:
    expected_date: date
    attempt_count: int
    last_reason: str | None = None


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


def evaluate_minimum_absence_snapshot(
    snapshot: SnapshotResponse,
    *,
    now: datetime,
    min_days: int,
    send_time: time,
) -> AlertEvaluation:
    complete_records = [record for record in snapshot.data if record.draw_complete]
    dated_records = []
    for record in complete_records:
        try:
            record_date = date.fromisoformat(record.date)
        except ValueError:
            continue
        dated_records.append((record_date, record))
    if not dated_records:
        return AlertEvaluation(status="waiting", reason="no_complete_draw")

    reference_date = max(record_date for record_date, _ in dated_records)
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

    usable = [
        (record_date, record)
        for record_date, record in dated_records
        if record_date <= reference_date
    ]
    earliest_date = min(record_date for record_date, _ in usable)
    coverage_days = (reference_date - earliest_date).days + 1
    last_seen_by_number: dict[str, date] = {}
    for record_date, record in usable:
        for values in record.prizes.model_dump().values():
            for value in values:
                if len(value) >= 2 and value[-2:].isdigit():
                    number = value[-2:]
                    previous = last_seen_by_number.get(number)
                    if previous is None or record_date > previous:
                        last_seen_by_number[number] = record_date

    candidates: list[AbsenceCandidate] = []
    for value in range(100):
        number = f"{value:02d}"
        last_seen = last_seen_by_number.get(number)
        if last_seen is None:
            if coverage_days >= min_days:
                candidates.append(
                    AbsenceCandidate(
                        number=number,
                        days_absent=coverage_days,
                        last_seen=None,
                        is_lower_bound=True,
                    )
                )
            continue
        days_absent = (reference_date - last_seen).days
        if days_absent >= min_days:
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


def evaluate_minimum_absence_snapshot_now(
    snapshot: SnapshotResponse,
    *,
    now: datetime,
    min_days: int,
) -> AlertEvaluation:
    complete_dates: list[date] = []
    for record in snapshot.data:
        if not record.draw_complete:
            continue
        try:
            complete_dates.append(date.fromisoformat(record.date))
        except ValueError:
            continue
    if not complete_dates:
        return AlertEvaluation(status="waiting", reason="no_complete_draw")
    reference_date = max(complete_dates)
    evaluation_time = datetime.combine(
        reference_date + timedelta(days=1),
        time.min,
        tzinfo=now.tzinfo,
    )
    return evaluate_minimum_absence_snapshot(
        snapshot,
        now=evaluation_time,
        min_days=min_days,
        send_time=time.min,
    )


def format_daily_report_message(
    evaluation: AlertEvaluation,
    *,
    report_date: date,
    min_days: int,
    warning: DailyUpdateWarning | None = None,
) -> str:
    if evaluation.reference_date is None or evaluation.status not in {
        "ready",
        "no_match",
    }:
        raise ValueError("A complete daily evaluation is required")

    prefix = []
    if warning is not None:
        prefix.extend(_format_update_warning(warning))
    body = _format_minimum_report_body(evaluation, min_days=min_days)
    report_line = f"Báo cáo ngày: {report_date.strftime('%d/%m/%Y')}"
    return "\n".join([*prefix, report_line, *body])


def format_no_data_daily_message(
    *,
    report_date: date,
    expected_date: date,
    attempt_count: int,
    last_reason: str | None,
) -> str:
    reason = last_reason or "update_state_missing"
    return "\n".join(
        [
            "⚠️ XSMB · không thể lập báo cáo dữ liệu hằng ngày",
            f"Báo cáo ngày: {report_date.strftime('%d/%m/%Y')}",
            (
                "Kỳ dữ liệu dự kiến: "
                f"{expected_date.strftime('%d/%m/%Y')} chưa cập nhật thành công."
            ),
            f"Số lần thử: {attempt_count}",
            f"Mã lỗi: {reason}",
            "Không có snapshot hợp lệ để lập báo cáo.",
            "Chỉ dùng để thống kê, không phải dự đoán kết quả.",
        ]
    )


def format_data_failure_message(
    state: DailyDataUpdateState,
    *,
    latest_reference_date: date | None,
) -> str:
    latest = (
        latest_reference_date.strftime("%d/%m/%Y")
        if latest_reference_date is not None
        else "không có"
    )
    return "\n".join(
        [
            "⚠️ XSMB · cập nhật dữ liệu buổi tối thất bại",
            f"Ngày dữ liệu cần cập nhật: {state.business_date.strftime('%d/%m/%Y')}",
            f"Số lần thử: {state.attempt_count}",
            f"Mã lỗi: {state.last_reason or 'job_failed'}",
            f"Kỳ dữ liệu gần nhất: {latest}",
            "Hệ thống sẽ tự thử lại mỗi giờ đến 23:45.",
        ]
    )


def format_minimum_immediate_report_message(
    evaluation: AlertEvaluation,
    *,
    checked_at: datetime,
    min_days: int,
) -> str:
    if evaluation.reference_date is None or evaluation.status not in {
        "ready",
        "no_match",
    }:
        raise ValueError("A complete immediate evaluation is required")
    body = _format_minimum_report_body(evaluation, min_days=min_days)
    body.append(f"Kiểm tra lúc: {checked_at.strftime('%d/%m/%Y %H:%M:%S')}")
    return "\n".join(body)


def _format_update_warning(warning: DailyUpdateWarning) -> list[str]:
    return [
        "⚠️ Dữ liệu kỳ dự kiến không cập nhật thành công.",
        f"Kỳ dự kiến: {warning.expected_date.strftime('%d/%m/%Y')}",
        f"Số lần thử: {warning.attempt_count}",
        f"Mã lỗi: {warning.last_reason or 'update_state_missing'}",
        "Đang sử dụng dữ liệu cũ.",
        "",
    ]


def _format_minimum_report_body(
    evaluation: AlertEvaluation,
    *,
    min_days: int,
) -> list[str]:
    assert evaluation.reference_date is not None
    lines = [
        f"🔔 XSMB · số chưa xuất hiện từ {min_days} ngày trở lên",
        f"Kỳ dữ liệu: {evaluation.reference_date.strftime('%d/%m/%Y')}",
    ]
    if not evaluation.candidates:
        lines.extend(
            [
                (
                    "Không có số nào chưa xuất hiện từ "
                    f"{min_days} ngày trở lên trong kỳ dữ liệu này."
                ),
                "",
                "Dữ liệu gồm hai số cuối của ĐB và G1–G7.",
                "Chỉ dùng để thống kê, không phải dự đoán kết quả.",
            ]
        )
        return lines

    exact_groups: dict[int, list[str]] = {}
    lower_groups: dict[int, list[str]] = {}
    for item in evaluation.candidates:
        groups = lower_groups if item.is_lower_bound else exact_groups
        groups.setdefault(item.days_absent, []).append(item.number)
    lines.extend([f"Tổng cộng: {len(evaluation.candidates)} số", ""])
    for days in sorted(lower_groups, reverse=True):
        lines.append(
            f"≥{days} ngày – không thấy trong dữ liệu hiện có: "
            f"{', '.join(lower_groups[days])}"
        )
    for days in sorted(exact_groups, reverse=True):
        lines.append(f"{days} ngày: {', '.join(exact_groups[days])}")
    lines.extend(
        [
            "",
            "Dữ liệu gồm hai số cuối của ĐB và G1–G7.",
            "Chỉ dùng để thống kê, không phải dự đoán kết quả.",
        ]
    )
    return lines


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
