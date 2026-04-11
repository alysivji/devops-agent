from pathlib import Path
from typing import Callable, Protocol, TypedDict

import yaml
from pydantic import BaseModel, Field, field_validator
from strands import tool

from .run_history import record_event
from .tools.ansible import (
    PLAYBOOKS_DIR,
    check_ansible_playbook_syntax,
    get_ansible_playbook_registry,
)
from .utils import build_agent, build_model

SYSTEM_PROMPT = """
You edit existing Ansible playbooks for this repository.

Output Requirements:
- Return the complete edited playbook file content, including the existing
  metadata header comments.
- Preserve the metadata header fields: name, description, target,
  requires_approval, and tags.
- Keep unrelated playbook behavior unchanged.
- Keep control flow top-down and obvious.
- Do not add external files or references to files that do not already exist.
- Do not include commentary outside the structured response fields.

Editing Rules:
- Make the smallest practical change that satisfies the requested repair.
- Prefer deterministic Ansible modules and clear assertions over opaque shell.
- Prefer goal-state validation over exhaustive implementation checks. If the
  requested end state is already true, preserve or add guards that skip
  disruptive remediation such as service restarts, boot edits, or reboot logic.
- For k3s cluster installation, treat all expected nodes reporting `Ready` from
  the control-plane API as the primary success signal; service state, cgroup
  state, and boot flags should be diagnostics when that signal is failing.
- Preserve explicit failure messages and structured debug context.
- If repairing JSON/Jinja access, prefer bracket lookup for dictionary keys that
  can collide with Python method names, such as `items`.
- If repairing a playbook that starts or restarts long-running remote services
  on Raspberry Pi or other `cluster` hosts, keep the service operation bounded.
  Do not use `async`/`poll` as a timeout wrapper around
  `ansible.builtin.systemd`. Prefer `ansible.builtin.systemd` with
  `no_block: true`, then validate with `ansible.builtin.service_facts` using
  retries/delay and collect
  `systemctl status` plus `journalctl` output in a rescue block.
- If repairing a playbook that can reboot Raspberry Pi or other remote `cluster`
  hosts, preserve or add an explicit reboot/wait/verify sequence: capture
  `/proc/sys/kernel/random/boot_id` before reboot when available, use
  `ansible.builtin.reboot` with conservative Raspberry Pi timeouts, follow it
  with `ansible.builtin.wait_for_connection`, refresh facts with
  `ansible.builtin.setup`, and assert the boot id changed before post-reboot
  desired-state validation.
"""


class EditedAnsiblePlaybook(BaseModel):
    content: str = Field(description="Complete edited playbook file content.")
    summary: str = Field(description="Short summary of the local playbook edit.")
    requires_remote_rerun: bool = Field(
        description="Whether validating the change requires rerunning the playbook."
    )

    @field_validator("content")
    @classmethod
    def validate_playbook_content(cls, value: str) -> str:
        validate_playbook_file_content(value)
        return value


class EditAnsiblePlaybookResult(BaseModel):
    path: Path
    summary: str
    edited_content: str
    written: bool
    requires_remote_rerun: bool
    syntax_check_passed: bool


class EditAnsiblePlaybookToolResult(TypedDict):
    path: str
    summary: str
    written: bool
    requires_remote_rerun: bool
    syntax_check_passed: bool


class AnsiblePlaybookEditor(Protocol):
    def run(
        self,
        *,
        playbook_path: Path,
        current_content: str,
        requested_change: str,
    ) -> EditedAnsiblePlaybook: ...


class EditAnsiblePlaybookAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(model_id="gpt-5.4"),
            system_prompt=SYSTEM_PROMPT,
        )

    def run(
        self,
        *,
        playbook_path: Path,
        current_content: str,
        requested_change: str,
    ) -> EditedAnsiblePlaybook:
        prompt = build_edit_prompt(
            playbook_path=playbook_path,
            current_content=current_content,
            requested_change=requested_change,
        )
        return self.agent.structured_output(EditedAnsiblePlaybook, prompt)


@tool
def edit_ansible_playbook(
    playbook_path: str,
    requested_change: str,
) -> EditAnsiblePlaybookToolResult:
    """
    Edit a validated Ansible playbook locally and syntax-check the result.

    Args:
        playbook_path: Relative path to an existing playbook in the validated registry.
        requested_change: Natural-language description of the local edit to make.

    Returns:
        A dictionary describing whether the syntax-checked edit was written.
    """
    result = EditAnsiblePlaybookWorkflow().run(
        playbook_path=playbook_path,
        requested_change=requested_change,
    )
    return {
        "path": str(result.path),
        "summary": result.summary,
        "written": result.written,
        "requires_remote_rerun": result.requires_remote_rerun,
        "syntax_check_passed": result.syntax_check_passed,
    }


class EditAnsiblePlaybookWorkflow:
    def __init__(
        self,
        *,
        editor: AnsiblePlaybookEditor | None = None,
        syntax_checker: Callable[[str], None] = check_ansible_playbook_syntax,
    ) -> None:
        self.editor = editor or EditAnsiblePlaybookAgent()
        self.syntax_checker = syntax_checker

    def run(self, *, playbook_path: str, requested_change: str) -> EditAnsiblePlaybookResult:
        target_path = _validate_registry_playbook_path(playbook_path)
        record_event(
            kind="playbook_edit_started",
            status="started",
            what=f"Started local edit for playbook `{playbook_path}`.",
            why="Repair an existing validated playbook before considering another remote run.",
            details={"path": playbook_path, "requested_change": requested_change},
        )

        current_content = target_path.read_text(encoding="utf-8")
        edited = self.editor.run(
            playbook_path=target_path,
            current_content=current_content,
            requested_change=requested_change,
        )
        self.syntax_checker(edited.content)
        validate_playbook_file_content(edited.content)

        print_edit_preview(path=target_path, edited=edited)
        record_event(
            kind="playbook_edit_preview_presented",
            status="completed",
            what="Presented the edited playbook preview.",
            why="Show the local edit summary before asking for write approval.",
            details={
                "path": str(target_path),
                "summary": edited.summary,
                "requires_remote_rerun": edited.requires_remote_rerun,
            },
        )

        written = confirm_edit(target_path)
        if not written:
            print("Playbook edit not written.")
            record_event(
                kind="playbook_edit_declined",
                status="declined",
                what=f"Declined local edit for playbook `{playbook_path}`.",
                why="The workflow requires explicit confirmation before editing a playbook file.",
                details={"path": str(target_path), "approved": False},
            )
            return EditAnsiblePlaybookResult(
                path=target_path,
                summary=edited.summary,
                edited_content=edited.content,
                written=False,
                requires_remote_rerun=edited.requires_remote_rerun,
                syntax_check_passed=True,
            )

        target_path.write_text(_normalize_file_content(edited.content), encoding="utf-8")
        print(f"Edited playbook at {target_path}.")
        record_event(
            kind="playbook_edit_written",
            status="completed",
            what=f"Wrote local edit for playbook `{playbook_path}`.",
            why="Persist the syntax-checked playbook repair under ansible/playbooks.",
            details={
                "path": str(target_path),
                "approved": True,
                "summary": edited.summary,
                "requires_remote_rerun": edited.requires_remote_rerun,
                "syntax_check_passed": True,
            },
        )
        return EditAnsiblePlaybookResult(
            path=target_path,
            summary=edited.summary,
            edited_content=edited.content,
            written=True,
            requires_remote_rerun=edited.requires_remote_rerun,
            syntax_check_passed=True,
        )


def build_edit_prompt(
    *,
    playbook_path: Path,
    current_content: str,
    requested_change: str,
) -> str:
    return f"""\
Edit this existing Ansible playbook.

Path: {playbook_path}

Requested change:
{requested_change.strip()}

Current playbook file:
```yaml
{current_content.rstrip()}
```
"""


def validate_playbook_file_content(content: str) -> None:
    metadata = _extract_metadata_header(content)
    required_fields = {"name", "description", "target", "requires_approval", "tags"}
    missing_fields = required_fields.difference(metadata)
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"edited playbook is missing metadata header fields: {missing}")

    parsed = yaml.safe_load(content)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("edited playbook content must contain a non-empty playbook list")


def _extract_metadata_header(content: str) -> dict[str, object]:
    metadata_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("#"):
            metadata_lines.append(line.removeprefix("#"))
            continue
        if metadata_lines:
            break

    if not metadata_lines:
        raise ValueError("edited playbook is missing a metadata header")

    metadata = yaml.safe_load("\n".join(metadata_lines))
    if not isinstance(metadata, dict):
        raise ValueError("edited playbook metadata header must be a mapping")
    return metadata


def _validate_registry_playbook_path(playbook_path: str) -> Path:
    requested_path = Path(playbook_path)
    if requested_path.is_absolute():
        raise ValueError("playbook path must be relative")

    registry_paths = {entry["path"] for entry in get_ansible_playbook_registry()}
    if playbook_path not in registry_paths:
        raise ValueError(f"Playbook path is not in the registry: {playbook_path}")

    resolved_playbooks_dir = PLAYBOOKS_DIR.resolve()
    resolved_path = requested_path.resolve()
    if resolved_playbooks_dir not in resolved_path.parents:
        raise ValueError(f"Playbook path must be under {PLAYBOOKS_DIR}: {playbook_path}")
    return requested_path


def confirm_edit(path: Path) -> bool:
    response = input(f"Write edited playbook to {path}? [y/N]: ").strip().lower()
    return response in {"y", "yes"}


def print_edit_preview(*, path: Path, edited: EditedAnsiblePlaybook) -> None:
    print(f"Path: {path}")
    print(f"Summary: {edited.summary}")
    print(f"Requires remote rerun: {str(edited.requires_remote_rerun).lower()}")
    print()
    print(edited.content)


def _normalize_file_content(content: str) -> str:
    return f"{content.rstrip()}\n"
