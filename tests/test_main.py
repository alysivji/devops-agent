import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from devops_bot import main as main_module


class SuccessfulOrchestrator:
    session_ids: list[str] = []

    def __init__(self, *, session_id: str) -> None:
        self.session_ids.append(session_id)

    def run(self, prompt: str) -> str:
        return f"handled: {prompt}"


class FailingOrchestrator:
    def __init__(self, *, session_id: str) -> None:
        self.session_id = session_id

    def run(self, prompt: str) -> str:
        raise RuntimeError(f"boom: {prompt}")


def test_main_appends_run_history_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    SuccessfulOrchestrator.session_ids = []
    monkeypatch.setattr(main_module, "OrchestratorAgent", SuccessfulOrchestrator)
    monkeypatch.setattr(sys, "argv", ["devops_bot", "inspect the registry"])

    exit_code = main_module.main()

    captured = capsys.readouterr()
    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"

    assert exit_code == 0
    assert captured.out.strip() == "handled: inspect the registry"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["turns"][0]["prompt"] == "inspect the registry"
    assert payload["turns"][0]["outcome"] == "handled: inspect the registry"
    assert SuccessfulOrchestrator.session_ids == [payload["session_id"]]


def test_main_skips_run_history_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "false")
    SuccessfulOrchestrator.session_ids = []
    monkeypatch.setattr(main_module, "uuid4", lambda: SimpleNamespace(hex="generated-session"))
    monkeypatch.setattr(main_module, "OrchestratorAgent", SuccessfulOrchestrator)
    monkeypatch.setattr(sys, "argv", ["devops_bot", "inspect the registry"])

    main_module.main()

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    assert not output_path.exists()
    assert SuccessfulOrchestrator.session_ids == ["generated-session"]


def test_main_uses_explicit_cli_session_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    SuccessfulOrchestrator.session_ids = []
    monkeypatch.setattr(main_module, "OrchestratorAgent", SuccessfulOrchestrator)
    monkeypatch.setattr(
        sys,
        "argv",
        ["devops_bot", "--session-id", "support-session", "inspect the registry"],
    )

    main_module.main()

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

    assert payload["session_id"] == "support-session"
    assert payload["turns"][0]["run_id"] != "support-session"
    assert SuccessfulOrchestrator.session_ids == ["support-session"]


def test_main_records_failed_session_before_reraising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    monkeypatch.setattr(main_module, "OrchestratorAgent", FailingOrchestrator)
    monkeypatch.setattr(sys, "argv", ["devops_bot", "inspect the registry"])

    with pytest.raises(RuntimeError, match="boom: inspect the registry"):
        main_module.main()

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

    assert payload["turns"][0]["outcome"] == "failed: boom: inspect the registry"
    assert payload["turns"][0]["events"][-1]["kind"] == "run_failed"
