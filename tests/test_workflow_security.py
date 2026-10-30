from pathlib import Path


def test_worker_deploy_accepts_only_trusted_pushes_from_this_repository():
    workflow = Path(".github/workflows/deploy-worker.yml").read_text(encoding="utf-8")

    assert "github.event.workflow_run.event == 'push'" in workflow
    assert (
        "github.event.workflow_run.head_repository.full_name == github.repository"
        in workflow
    )
