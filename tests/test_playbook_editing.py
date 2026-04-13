from pathlib import Path
from typing import Any

import pytest

from devops_bot.agents.playbook_editor import (
    SYSTEM_PROMPT,
    EditAnsiblePlaybookAgent,
    EditedAnsiblePlaybook,
)
from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools.playbooks import (
    EditAnsiblePlaybook,
)

ORIGINAL_PLAYBOOK = """\
# name: hello-control
# description: Ping the control node group.
# target: control
# requires_approval: true
# tags:
#   - connectivity
#   - control

---
- name: Hello control
  hosts: control
  tasks:
    - name: Ping control
      ansible.builtin.ping:
"""

EDITED_PLAYBOOK = """\
# name: hello-control
# description: Ping the control node group.
# target: control
# requires_approval: true
# tags:
#   - connectivity
#   - control

---
- name: Hello control
  hosts: control
  tasks:
    - name: Ping control node
      ansible.builtin.ping:
"""


class StubEditor:
    def __init__(self, edited: EditedAnsiblePlaybook) -> None:
        self.edited = edited
        self.requests: list[tuple[Path, str, str]] = []

    def run(
        self,
        *,
        playbook_path: Path,
        current_content: str,
        requested_change: str,
    ) -> EditedAnsiblePlaybook:
        self.requests.append((playbook_path, current_content, requested_change))
        return self.edited


def test_ansible_edit_playbook_records_approved_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    playbooks_dir = tmp_path / "ansible" / "playbooks"
    playbooks_dir.mkdir(parents=True)
    playbook_path = playbooks_dir / "hello-control.yaml"
    playbook_path.write_text(ORIGINAL_PLAYBOOK, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("devops_bot.tools.ansible.PLAYBOOKS_DIR", Path("ansible/playbooks"))
    monkeypatch.setattr("devops_bot.tools.playbooks.PLAYBOOKS_DIR", Path("ansible/playbooks"))
    monkeypatch.setattr("builtins.input", lambda _: "y")

    syntax_checked: list[str] = []
    playbook_tool = EditAnsiblePlaybook(
        editor=StubEditor(
            EditedAnsiblePlaybook(
                content=EDITED_PLAYBOOK,
                summary="Renamed the ping task for clarity.",
                requires_remote_rerun=True,
            )
        ),
        syntax_checker=syntax_checked.append,
    )
    run_history = RunHistory(prompt="fix the ping playbook")
    token = set_active_run_history(run_history)

    try:
        result = playbook_tool.run(
            playbook_path="ansible/playbooks/hello-control.yaml",
            requested_change="Rename the ping task for clarity.",
        )
    finally:
        reset_active_run_history(token)

    assert result.written is True
    assert result.syntax_check_passed is True
    assert result.requires_remote_rerun is True
    assert playbook_path.read_text(encoding="utf-8") == EDITED_PLAYBOOK
    assert syntax_checked == [EDITED_PLAYBOOK]
    event_kinds = [event.kind for event in run_history.session.events]
    assert "playbook_edit_preview_presented" in event_kinds
    assert "playbook_edit_written" in event_kinds


def test_ansible_edit_playbook_records_declined_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    playbooks_dir = tmp_path / "ansible" / "playbooks"
    playbooks_dir.mkdir(parents=True)
    playbook_path = playbooks_dir / "hello-control.yaml"
    playbook_path.write_text(ORIGINAL_PLAYBOOK, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("devops_bot.tools.ansible.PLAYBOOKS_DIR", Path("ansible/playbooks"))
    monkeypatch.setattr("devops_bot.tools.playbooks.PLAYBOOKS_DIR", Path("ansible/playbooks"))
    monkeypatch.setattr("builtins.input", lambda _: "n")

    playbook_tool = EditAnsiblePlaybook(
        editor=StubEditor(
            EditedAnsiblePlaybook(
                content=EDITED_PLAYBOOK,
                summary="Renamed the ping task for clarity.",
                requires_remote_rerun=True,
            )
        ),
        syntax_checker=lambda _: None,
    )
    run_history = RunHistory(prompt="fix the ping playbook")
    token = set_active_run_history(run_history)

    try:
        result = playbook_tool.run(
            playbook_path="ansible/playbooks/hello-control.yaml",
            requested_change="Rename the ping task for clarity.",
        )
    finally:
        reset_active_run_history(token)

    assert result.written is False
    assert playbook_path.read_text(encoding="utf-8") == ORIGINAL_PLAYBOOK
    event_kinds = [event.kind for event in run_history.session.events]
    assert "playbook_edit_declined" in event_kinds
    assert "playbook_edit_written" not in event_kinds


def test_ansible_edit_playbook_requires_registry_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    playbooks_dir = tmp_path / "ansible" / "playbooks"
    playbooks_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("devops_bot.tools.ansible.PLAYBOOKS_DIR", Path("ansible/playbooks"))
    monkeypatch.setattr("devops_bot.tools.playbooks.PLAYBOOKS_DIR", Path("ansible/playbooks"))

    playbook_tool = EditAnsiblePlaybook(
        editor=StubEditor(
            EditedAnsiblePlaybook(
                content=EDITED_PLAYBOOK,
                summary="Renamed the ping task for clarity.",
                requires_remote_rerun=True,
            )
        ),
        syntax_checker=lambda _: None,
    )

    with pytest.raises(ValueError, match="not in the registry"):
        playbook_tool.run(
            playbook_path="ansible/playbooks/missing.yaml",
            requested_change="Rename the ping task for clarity.",
        )


def test_editor_prompt_preserves_remote_reboot_wait_verification() -> None:
    assert "remote hosts" in SYSTEM_PROMPT
    assert "wait_for_connection" in SYSTEM_PROMPT
    assert "/proc/sys/kernel/random/boot_id" in SYSTEM_PROMPT
    assert "boot id changed" in SYSTEM_PROMPT


def test_editor_prompt_preserves_bounded_remote_service_operations() -> None:
    assert "long-running remote services" in SYSTEM_PROMPT
    assert "Do not use `async`/`poll`" in SYSTEM_PROMPT
    assert "no_block: true" in SYSTEM_PROMPT
    assert "application state with retries/delay" in SYSTEM_PROMPT


def test_editor_prompt_preserves_goal_oriented_validation() -> None:
    assert "goal-state validation" in SYSTEM_PROMPT
    assert "cluster/API-level health" in SYSTEM_PROMPT
    assert "diagnostics when that signal is failing" in SYSTEM_PROMPT


def test_editor_prompt_preserves_env_backed_sensitive_values() -> None:
    assert "sensitive value" in SYSTEM_PROMPT
    assert "lookup('ansible.builtin.env', 'NAME', default='')" in SYSTEM_PROMPT
    assert "Do not hardcode real" in SYSTEM_PROMPT
    assert "ansible.builtin.assert" in SYSTEM_PROMPT
    assert "untracked `.env` file" in SYSTEM_PROMPT


def test_editor_prompt_preserves_restart_or_reload_after_service_config_changes() -> None:
    assert "systemd service unit, environment file, or service" in SYSTEM_PROMPT
    assert "`reloaded` or" in SYSTEM_PROMPT
    assert "`restarted`" in SYSTEM_PROMPT
    assert "registered file-change results" in SYSTEM_PROMPT
    assert "Use `started` only as the steady" in SYSTEM_PROMPT


def test_editor_prompt_requires_official_docs_research() -> None:
    assert "When a repair involves module syntax" in SYSTEM_PROMPT
    assert "use `search_web`\n  to find current official documentation" in SYSTEM_PROMPT
    assert "use `http_get` to read the\n  relevant page before editing" in SYSTEM_PROMPT
    assert "Prefer official upstream/vendor documentation" in SYSTEM_PROMPT


def test_editor_agent_has_web_research_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_build_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("devops_bot.agents.playbook_editor.build_model", lambda **_: object())
    monkeypatch.setattr("devops_bot.agents.playbook_editor.build_agent", fake_build_agent)

    EditAnsiblePlaybookAgent()

    tool_names = [tool.tool_name for tool in captured["tools"]]
    assert tool_names == ["search_web", "http_get"]
