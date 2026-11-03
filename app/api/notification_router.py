"""Operational endpoints for server-side notifications."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from app.notifications.service import NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _service(request: Request) -> NotificationService:
    return request.app.state.notifications


def _require_admin(request: Request, supplied: str | None) -> None:
    settings = request.app.state.settings
    configured = settings.notification_admin_token
    if configured is None or not configured.get_secret_value():
        raise HTTPException(status_code=404, detail="Endpoint chưa được bật.")
    if supplied is None or not secrets.compare_digest(
        supplied, configured.get_secret_value()
    ):
        raise HTTPException(status_code=401, detail="Token quản trị không hợp lệ.")


@router.get("/status")
async def notification_status(request: Request) -> dict:
    """Return operational state without exposing credentials or recipient IDs."""
    return _service(request).status()


@router.post("/test")
async def test_notifications(
    request: Request,
    x_notification_token: str | None = Header(default=None),
) -> dict:
    """Send a protected test message to every configured destination."""
    settings = request.app.state.settings
    _require_admin(request, x_notification_token)

    service = _service(request)
    results = await service.send_test()
    return {
        "dryRun": settings.notification_dry_run,
        "success": bool(results) and all(result.success for result in results),
        "results": [
            {
                "channel": result.target.channel,
                "target": result.target.display,
                "success": result.success,
                "providerId": result.provider_id,
                "error": result.error,
            }
            for result in results
        ],
    }


@router.post("/send-now")
async def send_notifications_now(
    request: Request,
    x_notification_token: str | None = Header(default=None),
) -> dict:
    """Evaluate the latest complete data and send an immediate report."""
    _require_admin(request, x_notification_token)
    settings = request.app.state.settings
    outcome = await _service(request).send_now()
    success = bool(outcome.deliveries) and all(
        result.success for result in outcome.deliveries
    )

    if outcome.status == "not_configured":
        message = "Chưa có kênh nhận thông báo nào được cấu hình."
    elif outcome.status == "waiting":
        message = "Chưa đủ dữ liệu hoàn chỉnh để tính khoảng ngày chưa xuất hiện."
    elif outcome.status == "dry_run":
        message = "Đã tính báo cáo nhưng chưa gửi vì hệ thống đang ở chế độ dry-run."
    elif outcome.status == "partial_failure":
        message = "Đã gửi báo cáo nhưng có ít nhất một kênh thất bại."
    elif outcome.candidates:
        message = (
            f"Đã gửi {len(outcome.candidates)} số đang vắng "
            f"từ {settings.notification_min_days} ngày trở lên."
        )
    else:
        message = (
            "Đã gửi báo cáo: không có số nào đang vắng "
            f"từ {settings.notification_min_days} ngày trở lên."
        )

    return {
        "status": outcome.status,
        "success": success,
        "dryRun": settings.notification_dry_run,
        "message": message,
        "checkedAt": outcome.checked_at.isoformat(),
        "referenceDate": outcome.reference_date,
        "minDays": settings.notification_min_days,
        "maxDays": None,
        "threshold": f"{settings.notification_min_days}-plus",
        "candidateCount": len(outcome.candidates),
        "candidates": [
            {
                "number": candidate.number,
                "daysAbsent": candidate.days_absent,
                "lastSeen": (
                    candidate.last_seen.isoformat()
                    if candidate.last_seen is not None
                    else None
                ),
                "isLowerBound": candidate.is_lower_bound,
            }
            for candidate in outcome.candidates
        ],
        "reason": outcome.reason,
        "results": [
            {
                "channel": result.target.channel,
                "target": result.target.display,
                "success": result.success,
                "providerId": result.provider_id,
                "error": result.error,
            }
            for result in outcome.deliveries
        ],
    }
