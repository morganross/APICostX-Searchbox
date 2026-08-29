import importlib.util
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


def load_runner(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CODEX_RUNNER_DATA_DIR", str(tmp_path / "data"))
    spec = importlib.util.spec_from_file_location("codex_api_runner_test_app", RUNNER / "app.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_api_runner_maps_apicostx_high_to_codex_xhigh(tmp_path, monkeypatch) -> None:
    runner = load_runner(tmp_path, monkeypatch)

    args = runner.build_codex_args(
        model="gpt-5.6-sol",
        workspace=str(tmp_path),
        sandbox="workspace-write",
        ephemeral=True,
        reasoning_effort="high",
        final_path=tmp_path / "final.txt",
    )

    assert 'model_reasoning_effort="xhigh"' in args


def test_codex_api_runner_keeps_low_and_medium_unchanged(tmp_path, monkeypatch) -> None:
    runner = load_runner(tmp_path, monkeypatch)

    assert runner.resolve_reasoning_effort("low") == "low"
    assert runner.resolve_reasoning_effort("medium") == "medium"


def test_codex_api_runner_rejects_unknown_reasoning(tmp_path, monkeypatch) -> None:
    runner = load_runner(tmp_path, monkeypatch)

    try:
        runner.resolve_reasoning_effort("xhigh")
    except ValueError as exc:
        assert "Unsupported reasoning_effort" in str(exc)
    else:
        raise AssertionError("unknown reasoning effort must fail closed")
