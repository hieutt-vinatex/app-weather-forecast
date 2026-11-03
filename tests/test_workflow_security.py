from __future__ import annotations

from pathlib import Path


WORKFLOW_ROOT = Path(".github/workflows")
WRITER_NAMES = ("deploy-pages.yml", "data-sync.yml", "telegram.yml")


def workflow(name: str) -> str:
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def test_provider_workflow_is_removed_and_ci_is_github_only():
    assert not (WORKFLOW_ROOT / "deploy-worker.yml").exists()
    ci = workflow("ci.yml")
    assert "cloudflare/worker" not in ci.lower()
    assert "worker:" not in ci
    assert 'node-version: "20"' in ci
    assert 'python-version: "3.12"' in ci


def test_all_publication_writers_share_one_non_cancelling_mutex():
    for name in WRITER_NAMES:
        source = workflow(name)
        assert "group: github-pages-publication" in source
        assert "cancel-in-progress: false" in source
        assert "for attempt in 1 2 3" in source
        assert "fetch origin gh-pages" in source
        assert "--force" not in source


def test_workflows_have_no_provider_secrets_or_server_dispatch_path():
    source = "\n".join(workflow(name) for name in WRITER_NAMES)
    forbidden = (
        "cloudflare",
        "vercel",
        "repository_dispatch",
        "GITHUB_DISPATCH_TOKEN",
        "NOTIFICATION_ADMIN_TOKEN",
    )
    for value in forbidden:
        assert value.lower() not in source.lower()
    assert "echo ${{ secrets." not in source
    assert "echo $TELEGRAM_" not in source


def test_pages_workflows_use_official_actions_and_publish_only_site():
    for name in ("deploy-pages.yml", "data-sync.yml"):
        source = workflow(name)
        assert "actions/configure-pages@v5" in source
        assert "actions/upload-pages-artifact@v4" in source
        assert "actions/deploy-pages@v4" in source
        assert "path: publication/site" in source
        assert "pages: write" in source
        assert "id-token: write" in source
        assert "contents: write" in source
        assert "environment:" in source
        assert "name: github-pages" in source

    telegram = workflow("telegram.yml")
    assert "contents: write" in telegram
    assert "pages: write" not in telegram
    assert "id-token: write" not in telegram
    assert "upload-pages-artifact" not in telegram
    assert "deploy-pages" not in telegram
    assert "add state" in telegram


def test_site_deploy_is_gated_by_trusted_successful_ci_push():
    source = workflow("deploy-pages.yml")
    assert "workflows: [CI]" in source
    assert "github.event.workflow_run.conclusion == 'success'" in source
    assert "github.event.workflow_run.event == 'push'" in source
    assert "github.event.workflow_run.head_branch == 'develop'" in source
    assert (
        "github.event.workflow_run.head_repository.full_name == github.repository"
        in source
    )
    assert "ref: ${{ github.event.workflow_run.head_sha }}" in source
    assert "python source/scripts/prepare_pages.py" in source
    assert (
        "python source/scripts/verify_cloud_contracts.py --publication-root publication"
        in source
    )


def test_data_schedule_inputs_and_failure_publication_are_pinned():
    source = workflow("data-sync.yml")
    for cron in ('cron: "45 18 * * *"', 'cron: "45 19-23 * * *"'):
        assert cron in source
    assert source.count("cron:") == 2
    assert source.count('timezone: "Asia/Ho_Chi_Minh"') == 2
    assert "options: [full, incremental]" in source
    assert 'python-version: "3.12"' in source
    assert "continue-on-error: true" in source
    assert "steps.sync.outcome" in source
    assert 'mode="scheduled"' in source
    assert "sync --mode" in source
    assert "--store-root publication" in source
    assert "add --all site/data" in source
    assert "state/daily-data-update.json" in source


def test_data_workflow_has_no_telegram_credentials_and_preserves_its_ledger():
    source = workflow("data-sync.yml")
    for secret_name in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_IDS",
        "NOTIFICATION_LEDGER_HMAC_KEY",
    ):
        assert secret_name not in source
    assert "cp -a publication/site/data" in source
    assert "publication/state/daily-data-update.json" in source
    assert "rm -rf publication/site/data" in source
    assert "rm -rf publication/state" not in source
    assert "state/telegram-ledger.json" not in source


def test_telegram_schedule_inputs_secrets_and_state_boundary_are_pinned():
    source = workflow("telegram.yml")
    assert 'cron: "0-45/15 9-11 * * *"' in source
    assert 'cron: "0 12 * * *"' in source
    assert source.count("cron:") == 2
    assert source.count('timezone: "Asia/Ho_Chi_Minh"') == 2
    assert "options: [daily, manual]" in source
    assert "options: [data-failure" not in source
    assert 'python-version: "3.12"' in source
    assert "TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}" in source
    assert "TELEGRAM_CHAT_IDS: ${{ secrets.TELEGRAM_CHAT_IDS }}" in source
    assert (
        "NOTIFICATION_LEDGER_HMAC_KEY: ${{ secrets.NOTIFICATION_LEDGER_HMAC_KEY }}"
        in source
    )
    assert "NOTIFICATION_DRY_RUN: ${{ vars.NOTIFICATION_DRY_RUN || 'true' }}" in source
    assert "telegram --mode" in source
    assert "--store-root publication" in source
    assert 'mode="daily"' in source
    assert 'mode="data-failure"' in source


def test_telegram_workflow_run_is_trusted_and_cannot_modify_site_data():
    source = workflow("telegram.yml")
    assert 'workflows: ["Data sync and Pages deploy"]' in source
    assert "types: [completed]" in source
    assert "github.event.workflow_run.head_branch == 'develop'" in source
    assert (
        "github.event.workflow_run.head_repository.full_name == github.repository"
        in source
    )
    assert "ref: develop" in source
    assert "cp -a publication/state" in source
    assert "rm -rf publication/state" in source
    assert "rm -rf publication/site/data" not in source
    assert "add site/data" not in source


def test_runtime_versions_and_publication_root_are_consistent():
    deploy = workflow("deploy-pages.yml")
    data = workflow("data-sync.yml")
    telegram = workflow("telegram.yml")
    assert 'node-version: "20"' in deploy
    for source in (deploy, data, telegram):
        assert 'python-version: "3.12"' in source
        assert "--publication-root publication" in source
