from __future__ import annotations

from app.cloud.data_jobs import DataJobResult
from app.cloud.notification_jobs import CloudNotificationResult
from scripts import cloud_job
from tests.conftest import make_settings

REQUEST_ID = "123e4567-e89b-12d3-a456-426614174000"


def cloud_settings():
    return make_settings(
        cloudflare_account_id="account",
        cloudflare_kv_namespace_id="namespace",
        cloudflare_api_token="secret",
    )


def test_sync_cli_returns_nonzero_and_preserves_requested_operation(monkeypatch):
    operation: dict[str, str] = {}

    async def fake_run_sync(args, settings):
        assert settings.cloudflare_account_id == "account"
        operation["request_id"] = args.request_id
        operation["status"] = "failed"
        return DataJobResult(
            status="failed",
            mode=args.mode,
            version=None,
            record_count=0,
            reason="invalid_upstream_data",
        )

    monkeypatch.setattr(cloud_job, "_run_sync", fake_run_sync)

    code = cloud_job.main(
        ["sync", "--mode", "incremental", "--request-id", REQUEST_ID],
        settings_factory=cloud_settings,
    )

    assert code == 1
    assert operation == {"request_id": REQUEST_ID, "status": "failed"}


def test_telegram_cli_noop_after_recorded_success_returns_zero(monkeypatch):
    async def fake_run_telegram(args, settings):
        del args, settings
        return CloudNotificationResult(
            status="already_delivered",
            mode="scheduled",
        )

    monkeypatch.setattr(cloud_job, "_run_telegram", fake_run_telegram)

    assert cloud_job.main(
        ["telegram", "--mode", "scheduled"],
        settings_factory=cloud_settings,
    ) == 0


def test_cli_settings_factory_failure_is_safe(capsys):
    def invalid_settings():
        return make_settings()

    code = cloud_job.main(
        ["sync", "--mode", "full"],
        settings_factory=invalid_settings,
    )

    assert code == 2
    assert "CLOUDFLARE_API_TOKEN" in capsys.readouterr().err
