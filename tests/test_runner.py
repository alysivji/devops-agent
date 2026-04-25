import json
from pathlib import Path

import pytest

from devops_bot import approval
from devops_bot import runner as runner_module


class FakeUI:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.statuses: list[str] = []
        self.cleared = 0
        self.approval_prompts: list[str] = []

    def post_message(self, role: str, text: str) -> None:
        self.messages.append((role, text))

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def clear_status(self) -> None:
        self.cleared += 1

    def get_approval(self, prompt: str) -> bool:
        self.approval_prompts.append(prompt)
        return True


class SuccessfulOrchestrator:
    prompts: list[str] = []
    session_ids: list[str] = []

    def __init__(self, *, session_id: str) -> None:
        self.session_ids.append(session_id)

    def run(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"handled: {prompt}"


class FailingOrchestrator:
    def __init__(self, *, session_id: str) -> None:
        self.session_id = session_id

    def run(self, prompt: str) -> str:
        raise RuntimeError(f"boom: {prompt}")


def test_runner_records_successful_chat_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    SuccessfulOrchestrator.prompts = []
    SuccessfulOrchestrator.session_ids = []
    monkeypatch.setattr(runner_module, "OrchestratorAgent", SuccessfulOrchestrator)

    ui = FakeUI()
    runner = runner_module.AgentRunner(ui)
    runner.run("inspect the registry")

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

    assert ui.statuses == ["Running..."]
    assert ui.cleared == 1
    assert ui.messages == [("agent", "handled: inspect the registry")]
    assert SuccessfulOrchestrator.prompts == ["inspect the registry"]
    assert SuccessfulOrchestrator.session_ids == [runner.session_id]
    assert payload["prompt"] == "inspect the registry"
    assert payload["outcome"] == "handled: inspect the registry"


def test_runner_records_failed_chat_turn_without_raising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    monkeypatch.setattr(runner_module, "OrchestratorAgent", FailingOrchestrator)

    ui = FakeUI()
    runner = runner_module.AgentRunner(ui)
    runner.run("inspect the registry")

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

    assert ui.messages == [("error", "boom: inspect the registry")]
    assert ui.cleared == 1
    assert payload["outcome"] == "failed: boom: inspect the registry"
    assert payload["events"][-1]["kind"] == "run_failed"


def test_runner_installs_and_resets_approval_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "false")

    class ApprovalAwareOrchestrator:
        def __init__(self, *, session_id: str) -> None:
            self.session_id = session_id

        def run(self, prompt: str) -> str:
            approved = approval.get_approval(f"Approve {prompt}? ")
            return f"approved={approved}"

    monkeypatch.setattr(runner_module, "OrchestratorAgent", ApprovalAwareOrchestrator)
    monkeypatch.setattr("builtins.input", lambda prompt: "no")

    ui = FakeUI()
    runner = runner_module.AgentRunner(ui)
    runner.run("deployment")

    assert ui.approval_prompts == ["Approve deployment? "]
    assert ui.messages == [("agent", "approved=True")]
    assert approval.get_approval("fallback? ") is False
