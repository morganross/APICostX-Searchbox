from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "codex-api-runner"


def test_codex_api_runner_deployment_files_are_preserved() -> None:
    expected = {
        "app.py",
        "environment.example",
        "requirements.txt",
        "codex-api-runner.service",
        "README.md",
    }

    assert expected.issubset({path.name for path in RUNNER.iterdir()})


def test_codex_api_runner_source_keeps_authentication_and_health_contract() -> None:
    source = (RUNNER / "app.py").read_text(encoding="utf-8")

    assert 'APP = FastAPI(title="CodexExecAPI"' in source
    assert '@APP.get("/health")' in source
    assert '@APP.get("/v1/models")' in source
    assert '@APP.post("/v1/chat/completions")' in source
    assert "secrets.compare_digest" in source
    assert "CODEX_RUNNER_TOKEN" in source


def test_codex_api_runner_secrets_and_state_remain_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".env" in gitignore
    assert "data/" in gitignore
