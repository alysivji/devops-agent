import json
from pathlib import Path
from typing import Any, cast

import pytest

from devops_bot import approval
from devops_bot import workflow as workflow_module


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


class ApprovalAwareOrchestrator:
    def __init__(self, *, session_id: str) -> None:
        self.session_id = session_id

    def run(self, prompt: str) -> str:
        approved = approval.request_approval(
            prompt=f"Approve {prompt}? ",
            kind="deployment",
            context={"prompt": prompt},
        )
        return f"approved={approved}"


def _build_workflow(agent_cls: type[Any]) -> workflow_module.AgentWorkflow:
    return workflow_module.AgentWorkflow(
        session_id="session-1",
        agent_factory=lambda session_id: cast(
            workflow_module.WorkflowAgent,
            agent_cls(session_id=session_id),
        ),
    )


def test_workflow_records_successful_chat_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    SuccessfulOrchestrator.prompts = []
    SuccessfulOrchestrator.session_ids = []
    captured_events: list[workflow_module.WorkflowEvent] = []

    result = _build_workflow(SuccessfulOrchestrator).run(
        "inspect the registry",
        event_sink=captured_events.append,
        approval_resolver=lambda request: True,
    )

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

    assert result == workflow_module.WorkflowResult(
        status="completed",
        response="handled: inspect the registry",
    )
    assert SuccessfulOrchestrator.prompts == ["inspect the registry"]
    assert SuccessfulOrchestrator.session_ids == ["session-1"]
    assert [event["kind"] for event in captured_events] == [
        "run_started",
        "status",
        "message",
        "run_completed",
        "status",
    ]
    assert payload["prompt"] == "inspect the registry"
    assert payload["outcome"] == "handled: inspect the registry"
    assert workflow_module.get_workflow_runtime() is None


def test_workflow_records_failed_chat_turn_without_raising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "true")
    captured_events: list[workflow_module.WorkflowEvent] = []

    result = _build_workflow(FailingOrchestrator).run(
        "inspect the registry",
        event_sink=captured_events.append,
        approval_resolver=lambda request: True,
    )

    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

    assert result == workflow_module.WorkflowResult(
        status="failed",
        error="boom: inspect the registry",
    )
    assert captured_events[2] == {
        "kind": "message",
        "role": "error",
        "text": "boom: inspect the registry",
    }
    assert payload["outcome"] == "failed: boom: inspect the registry"
    assert payload["events"][-1]["kind"] == "run_failed"
    assert workflow_module.get_workflow_runtime() is None


def test_workflow_uses_context_scoped_approval_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "false")
    requests: list[approval.ApprovalRequest] = []

    def approve(request: approval.ApprovalRequest) -> bool:
        requests.append(request)
        return False

    result = _build_workflow(ApprovalAwareOrchestrator).run(
        "deployment",
        event_sink=lambda event: None,
        approval_resolver=approve,
    )

    assert requests == [
        {
            "kind": "deployment",
            "prompt": "Approve deployment? ",
            "context": {"prompt": "deployment"},
        }
    ]
    assert result == workflow_module.WorkflowResult(
        status="completed",
        response="approved=False",
    )


def test_workflow_can_pause_for_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "false")

    def pause(request: approval.ApprovalRequest) -> bool:
        raise approval.WaitingForApproval(request)

    result = _build_workflow(ApprovalAwareOrchestrator).run(
        "deployment",
        event_sink=lambda event: None,
        approval_resolver=pause,
    )

    assert result == workflow_module.WorkflowResult(
        status="paused_for_approval",
        approval_request={
            "kind": "deployment",
            "prompt": "Approve deployment? ",
            "context": {"prompt": "deployment"},
        },
    )
    assert workflow_module.get_workflow_runtime() is None


def test_workflow_runtime_tokens_restore_previous_context() -> None:
    runtime_one = workflow_module.WorkflowRuntime(
        event_sink=lambda event: None,
        approval_resolver=lambda request: True,
    )
    runtime_two = workflow_module.WorkflowRuntime(
        event_sink=lambda event: None,
        approval_resolver=lambda request: False,
    )

    token_one = workflow_module.set_workflow_runtime(runtime_one)
    token_two = workflow_module.set_workflow_runtime(runtime_two)

    assert workflow_module.get_workflow_runtime() is runtime_two

    workflow_module.reset_workflow_runtime(token_two)
    assert workflow_module.get_workflow_runtime() is runtime_one

    workflow_module.reset_workflow_runtime(token_one)
    assert workflow_module.get_workflow_runtime() is None
