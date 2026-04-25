from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from devops_bot.agents.playbook_metadata import GeneratedPlaybookMetadata
from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools.playbooks import CreateAnsiblePlaybook
from devops_bot.workflow import (
    WorkflowEvent,
    WorkflowRuntime,
    reset_workflow_runtime,
    set_workflow_runtime,
)


class StubGenerator:
    def __init__(self, yaml_text: str) -> None:
        self.yaml_text = yaml_text

    def run(self, prompt: str) -> SimpleNamespace:
        return SimpleNamespace(yaml=self.yaml_text)


class StubMetadataAgent:
    def __init__(self, metadata: GeneratedPlaybookMetadata) -> None:
        self.metadata = metadata

    def run(self, *, yaml: str) -> GeneratedPlaybookMetadata:
        return self.metadata


def test_create_playbook_records_approved_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "devops_bot.tools.playbooks.PLAYBOOKS_DIR", tmp_path / "ansible" / "playbooks"
    )
    (tmp_path / "ansible" / "playbooks").mkdir(parents=True)
    monkeypatch.setattr("builtins.input", lambda _: "y")

    metadata = GeneratedPlaybookMetadata(
        name="hello-control",
        description="Ping the control node group.",
        target="control",
        tags=["connectivity"],
        requires_approval=True,
    )
    playbook_tool = CreateAnsiblePlaybook(
        generator=cast(
            Any,
            StubGenerator(
                "- hosts: control\n  tasks:\n    - name: Ping\n      ansible.builtin.ping:\n"
            ),
        ),
        metadata_agent=cast(Any, StubMetadataAgent(metadata)),
    )
    run_history = RunHistory(prompt="create a ping playbook")
    token = set_active_run_history(run_history)
    emitted_events: list[WorkflowEvent] = []
    runtime_token = set_workflow_runtime(
        WorkflowRuntime(
            event_sink=emitted_events.append,
            approval_resolver=lambda request: True,
        )
    )

    try:
        result = playbook_tool.run("create a ping playbook")
    finally:
        reset_workflow_runtime(runtime_token)
        reset_active_run_history(token)

    event_kinds = [event.kind for event in run_history.session.events]

    assert result.written is True
    assert "playbook_write_approved" in event_kinds
    assert "playbook_written" in event_kinds
    assert [event["kind"] for event in emitted_events] == [
        "preview",
        "approval_requested",
        "approval_resolved",
        "notice",
    ]
    assert emitted_events[0]["preview_type"] == "ansible_playbook_create"
    assert "Generated playbook preview" in emitted_events[0]["title"]
    assert emitted_events[-1]["text"] == (
        f"Wrote playbook to {tmp_path / 'ansible' / 'playbooks' / 'hello-control.yaml'}."
    )
    yaml_event = next(
        event for event in run_history.session.events if event.kind == "playbook_yaml_generated"
    )
    assert yaml_event.details == {"hosts": ["control"], "task_count": 1}


def test_create_playbook_records_declined_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "devops_bot.tools.playbooks.PLAYBOOKS_DIR", tmp_path / "ansible" / "playbooks"
    )
    (tmp_path / "ansible" / "playbooks").mkdir(parents=True)
    monkeypatch.setattr("builtins.input", lambda _: "n")

    metadata = GeneratedPlaybookMetadata(
        name="hello-control",
        description="Ping the control node group.",
        target="control",
        tags=["connectivity"],
        requires_approval=True,
    )
    playbook_tool = CreateAnsiblePlaybook(
        generator=cast(
            Any,
            StubGenerator(
                "- hosts: control\n  tasks:\n    - name: Ping\n      ansible.builtin.ping:\n"
            ),
        ),
        metadata_agent=cast(Any, StubMetadataAgent(metadata)),
    )
    run_history = RunHistory(prompt="create a ping playbook")
    token = set_active_run_history(run_history)
    emitted_events: list[WorkflowEvent] = []
    runtime_token = set_workflow_runtime(
        WorkflowRuntime(
            event_sink=emitted_events.append,
            approval_resolver=lambda request: False,
        )
    )

    try:
        result = playbook_tool.run("create a ping playbook")
    finally:
        reset_workflow_runtime(runtime_token)
        reset_active_run_history(token)

    assert result.written is False
    event_kinds = [event.kind for event in run_history.session.events]
    assert "playbook_write_declined" in event_kinds
    assert "playbook_written" not in event_kinds
    assert emitted_events[-1] == {
        "kind": "notice",
        "text": "Playbook not written.",
        "level": "info",
    }
