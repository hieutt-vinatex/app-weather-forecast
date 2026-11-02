from __future__ import annotations

from pathlib import Path


ACTIVE_DOCS = (
    Path("README.md"),
    Path("docs/CLOUD_DEPLOYMENT.md"),
    Path("docs/TELEGRAM_GROUP.md"),
    Path("docs/INSTALLATION.md"),
    Path(".env.example"),
    Path("frontend/.env.example"),
)


def text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def all_active_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in ACTIVE_DOCS)


def test_runbook_names_exact_github_configuration():
    runbook = text("docs/CLOUD_DEPLOYMENT.md")
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_IDS",
        "NOTIFICATION_LEDGER_HMAC_KEY",
        "NOTIFICATION_DRY_RUN",
    ):
        assert name in runbook
    assert "Source: GitHub Actions" in runbook
    assert "repository public" in runbook
    assert "default branch `develop`" in runbook
    assert "https://hieutt-vinatex.github.io/app-weather-forecast/" in runbook


def test_bootstrap_order_and_manual_workflow_paths_are_explicit():
    runbook = text("docs/CLOUD_DEPLOYMENT.md")
    ordered_markers = (
        "1. Chuyển repository sang public",
        "2. Xác nhận `develop` là default branch",
        "3. Chọn Pages Source: GitHub Actions",
        "4. Tạo ba secret và biến dry-run",
        "5. Push code lên `develop`",
        "6. Chờ CI và site deploy",
        "7. Chạy full sync",
        "8. Kiểm tra 30/60/90 ngày",
        "9. Chạy Telegram dry-run",
        "10. Bật gửi Telegram thật",
        "11. Theo dõi lịch tự động",
    )
    positions = [runbook.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions)
    assert "Actions → Data sync and Pages deploy → Run workflow" in runbook
    assert "Actions → Telegram notification → Run workflow" in runbook
    assert "mode=full" in runbook
    assert "mode=incremental" in runbook
    assert "mode=scheduled" in runbook
    assert "mode=manual" in runbook


def test_schedules_freshness_telegram_and_operational_caveats_are_documented():
    docs = all_active_docs()
    assert "03:17" in docs
    assert "17:47–19:02" in docs
    assert "09:07–12:07" in docs
    assert "10–15 phút" in docs
    assert "dữ liệu mới nhất đã xuất bản" in docs
    assert "không cần chờ dữ liệu của ngày đang quay" in docs
    assert "có thể bị trễ" in docs
    assert "60 ngày" in docs
    assert "commit tốt gần nhất" in docs
    assert "manifest trước" in docs


def test_active_docs_do_not_instruct_retired_provider_setup():
    docs = all_active_docs().lower()
    for forbidden in (
        "cloudflare",
        "vercel",
        "workers kv",
        "vite_api_base_url",
        "notification_admin_token",
        "github_dispatch_token",
        "repository_dispatch",
    ):
        assert forbidden not in docs


def test_local_server_is_optional_and_frontend_env_is_public_only():
    readme = text("README.md")
    install = text("docs/INSTALLATION.md")
    frontend_env = text("frontend/.env.example")
    assert "FastAPI local là tùy chọn" in readme
    assert "không bắt buộc cho production" in install
    assert "VITE_ACTIVE_POLL_MS" in frontend_env
    assert "VITE_IDLE_POLL_MS" in frontend_env
    assert "VITE_MANIFEST_CACHE_MS" in frontend_env
    assert "TOKEN" not in frontend_env
    assert "SECRET" not in frontend_env
