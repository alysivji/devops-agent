import json
import sys
from pathlib import Path

import pytest

from agent import main as main_module


class SuccessfulOrchestrator:
    def run(self, prompt: str) -> str:
        return f"handled: {prompt}"


class FailingOrchestrator:
    def run(self, prompt: str) -> str:
        raise RuntimeError(f"boom: {prompt}")


def test_main_appends_run_history_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    monkeypatch.setattr(main_module, "OrchestratorAgent", SuccessfulOrchestrator)
    monkeypatch.setattr(sys, "argv", ["agent.main", "inspect the registry"])

    exit_code = main_module.main()

    captured = capsys.readouterr()
    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"

    assert exit_code == 0
    assert captured.out.strip() == "handled: inspect the registry"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["prompt"] == "inspect the registry"
    assert payload["outcome"] == "handled: inspect the registry"


def test_main_skips_run_history_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "false")
    monkeypatch.setattr(main_module, "OrchestratorAgent", SuccessfulOrchestrator)
    monkeypatch.setattr(sys, "argv", ["agent.main", "inspect the registry"])

    main_module.main()

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    assert not output_path.exists()


def test_main_records_failed_session_before_reraising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    monkeypatch.setattr(main_module, "OrchestratorAgent", FailingOrchestrator)
    monkeypatch.setattr(sys, "argv", ["agent.main", "inspect the registry"])

    with pytest.raises(RuntimeError, match="boom: inspect the registry"):
        main_module.main()

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

    assert payload["outcome"] == "failed: boom: inspect the registry"
    assert payload["events"][-1]["kind"] == "run_failed"
