from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_ci_workflow_runs_pytest_on_push_and_pr() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"

    assert workflow_path.exists()

    content = workflow_path.read_text(encoding="utf-8")

    assert "on:" in content
    assert "push:" in content
    assert "pull_request:" in content
    assert "python-version: '3.11'" in content
    assert "pip install" in content
    assert "pytest" in content
    assert "tests/" in content
