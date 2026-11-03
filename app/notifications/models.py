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


def evaluate_snapshot(
    snapshot: SnapshotResponse,
    *,
    now: datetime,
    min_days: int,
    send_time: time,
    reference_not_after: date | None = None,
) -> AlertEvaluation:
    reference_limit = reference_not_after or now.date()
    complete_records = [record for record in snapshot.data if record.draw_complete]
    dated_records = []
    for record in complete_records:
        try:
            record_date = date.fromisoformat(record.date)
        except ValueError:
            continue
        if record_date <= reference_limit:
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


def evaluate_snapshot_now(
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
            record_date = date.fromisoformat(record.date)
        except ValueError:
            continue
        if record_date <= now.date():
            complete_dates.append(record_date)
    if not complete_dates:
        return AlertEvaluation(status="waiting", reason="no_complete_draw")
    reference_date = max(complete_dates)
    evaluation_time = datetime.combine(
        reference_date + timedelta(days=1),
        time.min,
        tzinfo=now.tzinfo,
    )
    return evaluate_snapshot(
        snapshot,
        now=evaluation_time,
        min_days=min_days,
        send_time=time.min,
        reference_not_after=now.date(),
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


def format_immediate_report_message(
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


def format_alert_message(
    evaluation: AlertEvaluation,
    *,
    min_days: int,
) -> str:
    if evaluation.reference_date is None or evaluation.status not in {
        "ready",
        "no_match",
    }:
        raise ValueError("A complete alert evaluation is required")
    return "\n".join(_format_minimum_report_body(evaluation, min_days=min_days))


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
