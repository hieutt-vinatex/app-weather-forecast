from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pytest

from app.cloud.filesystem_store import FilesystemJsonStore
from app.cloud.data_jobs import DataJobResult
from app.cloud.notification_jobs import CloudNotificationResult
from scripts import cloud_job
from tests.conftest import make_settings

REQUEST_ID = "123e4567-e89b-12d3-a456-426614174000"


def github_settings():
    return make_settings(notification_ledger_hmac_key="ledger-secret")


def test_sync_cli_uses_publication_root_without_cloudflare_configuration(
    monkeypatch, tmp_path: Path
):
    operation: dict[str, str] = {}

    async def fake_run_sync(args, settings):
        assert settings.cloudflare_account_id == ""
        operation["store_root"] = str(args.store_root)
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
        [
            "sync",
            "--mode",
            "incremental",
            "--request-id",
            REQUEST_ID,
            "--store-root",
            str(tmp_path),
        ],
        settings_factory=github_settings,
    )

    assert code == 1
    assert operation == {
        "store_root": str(tmp_path),
        "request_id": REQUEST_ID,
        "status": "failed",
    }


async def test_run_sync_constructs_filesystem_store(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    async def fake_run_data_job(settings, store, **kwargs):
        captured["settings"] = settings
        captured["store"] = store
        captured.update(kwargs)
        await store.put_json("job-status:v1:data", {"status": "succeeded"})
        return DataJobResult(
            status="succeeded",
            mode=kwargs["mode"],
            version="v1",
            record_count=90,
        )

    monkeypatch.setattr(cloud_job, "run_data_job", fake_run_data_job)
    args = argparse.Namespace(
        mode="full",
        request_id=None,
        store_root=tmp_path,
    )

    result = await cloud_job._run_sync(args, github_settings())

    assert result.status == "succeeded"
    assert isinstance(captured["store"], FilesystemJsonStore)
    assert (tmp_path / "site/data/status.json").is_file()


async def test_run_sync_routes_scheduled_mode_to_guarded_job(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    async def fake_scheduled(settings, store, *, clock):
        captured["settings"] = settings
        captured["store"] = store
        captured["clock"] = clock()
        return DataJobResult(
            status="already_succeeded",
            mode="scheduled",
            version="v1",
            record_count=90,
        )

    async def unexpected_manual(*args, **kwargs):
        raise AssertionError(f"unexpected manual job: {args} {kwargs}")

    monkeypatch.setattr(cloud_job, "run_scheduled_data_job", fake_scheduled)
    monkeypatch.setattr(cloud_job, "run_data_job", unexpected_manual)
    args = argparse.Namespace(
        mode="scheduled",
        request_id=None,
        store_root=tmp_path,
    )

    result = await cloud_job._run_sync(args, github_settings())

    assert result.status == "already_succeeded"
    assert isinstance(captured["store"], FilesystemJsonStore)


@pytest.mark.parametrize("status", ["already_succeeded", "outside_window"])
def test_scheduled_data_noop_statuses_exit_zero(monkeypatch, tmp_path, status):
    async def fake_run_sync(args, settings):
        del args, settings
        return DataJobResult(
            status=status,
            mode="scheduled",
            version=None,
            record_count=0,
        )

    monkeypatch.setattr(cloud_job, "_run_sync", fake_run_sync)

    assert cloud_job.main(
        [
            "sync",
            "--mode",
            "scheduled",
            "--store-root",
            str(tmp_path),
        ],
        settings_factory=github_settings,
    ) == 0


def test_telegram_cli_noop_after_recorded_success_returns_zero(
    monkeypatch, tmp_path: Path
):
    async def fake_run_telegram(args, settings):
        del args, settings
        return CloudNotificationResult(
            status="already_delivered",
            mode="scheduled",
        )

    monkeypatch.setattr(cloud_job, "_run_telegram", fake_run_telegram)

    assert cloud_job.main(
        [
            "telegram",
            "--mode",
            "scheduled",
            "--store-root",
            str(tmp_path),
        ],
        settings_factory=github_settings,
    ) == 0


def test_cli_missing_publication_root_is_safe(capsys, tmp_path: Path):
    missing = tmp_path / "missing"

    code = cloud_job.main(
        ["sync", "--mode", "full", "--store-root", str(missing)],
        settings_factory=github_settings,
    )

    assert code == 2
    error = capsys.readouterr().err
    assert "publication root is not a directory" in error
    assert str(missing) not in error


def test_cli_timeout_returns_one(monkeypatch, tmp_path: Path, capsys):
    def timeout(awaitable, timeout):
        del timeout
        awaitable.close()
        raise asyncio.TimeoutError

    code = cloud_job.main(
        ["sync", "--mode", "full", "--store-root", str(tmp_path)],
        settings_factory=github_settings,
        run_async=timeout,
    )

    assert code == 1
    assert capsys.readouterr().err.strip() == "cloud job timed out"


def test_github_job_config_has_no_provider_credentials():
    config = github_settings().github_job_config()

    assert config.max_value_bytes == 20 * 1024 * 1024
    assert config.operation_ttl_seconds == 86400
    assert config.job_timeout_seconds == 1200
    assert not hasattr(config, "api_token")


def test_telegram_cli_requires_ledger_hmac_key(tmp_path: Path, capsys):
    code = cloud_job.main(
        [
            "telegram",
            "--mode",
            "scheduled",
            "--store-root",
            str(tmp_path),
        ],
        settings_factory=make_settings,
    )

    assert code == 2
    assert "NOTIFICATION_LEDGER_HMAC_KEY" in capsys.readouterr().err
