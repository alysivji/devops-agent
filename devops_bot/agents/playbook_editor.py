from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from ..factory import build_agent, build_model
from ..tools.web import http_get, search_web

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
- If a playbook needs a sensitive value such as a password, token, key, or
  credential, read it from a runtime environment variable with
  `lookup('ansible.builtin.env', 'NAME', default='')`. Do not hardcode real
  secrets, secret-looking sample values, or generated passwords in playbook
  vars, tasks, comments, or debug output.
- For every required sensitive environment variable, preserve or add an early
  `ansible.builtin.assert` before remote-changing tasks. The assertion must
  check that the value is present and meets any minimum safety requirements, and
  the failure message must name the exact environment variable users need to set
  in their untracked `.env` file.
- When a playbook changes a systemd service unit, environment file, or service
  configuration file, preserve or add an appropriate `reloaded` or `restarted`
  service state guarded by the registered file-change results, then validate the
  service or application health. Use `started` only as the steady state guard
  for an unhealthy or stopped service; it does not apply new config to an
  already-running service.
- Prefer goal-state validation over exhaustive implementation checks. If the
  requested end state is already true, preserve or add guards that skip
  disruptive remediation such as service restarts, boot edits, or reboot logic.
- For clustered services, preserve or add cluster/API-level health as the
  primary success signal when one exists. For example, a k3s install should
  verify all expected nodes report `Ready`; service state, boot flags, and
  kernel internals should be diagnostics when that signal is failing.
- Preserve explicit failure messages and structured debug context.
- If repairing JSON/Jinja access, prefer bracket lookup for dictionary keys that
  can collide with Python method names, such as `items`.
- If repairing a playbook that starts or restarts long-running remote services,
  keep the service operation bounded. Do not use `async`/`poll` as a timeout
  wrapper around `ansible.builtin.systemd`. Prefer module-native nonblocking
  behavior such as `no_block: true`, then validate the desired service or
  application state with retries/delay and collect service status and logs in a
  rescue block when the platform exposes them.
- If repairing a playbook that can reboot remote hosts, preserve or add an
  explicit reboot/wait/verify sequence: capture
  `/proc/sys/kernel/random/boot_id` before reboot on Linux hosts when available,
  use `ansible.builtin.reboot` with conservative timeouts for low-power or
  slow-booting hosts, follow it with `ansible.builtin.wait_for_connection`,
  refresh facts with `ansible.builtin.setup`, and assert the boot id changed
  before post-reboot desired-state validation.

Research Guidance:
- When a repair involves module syntax, CLI flags, installation methods,
  package names, chart values, or version-specific behavior, use `search_web`
  to find current official documentation, then use `http_get` to read the
  relevant page before editing.
- Prefer official upstream/vendor documentation over examples, blog posts, or
  forum answers.
- Use `http_get` only for reading documentation.
- Never use HTTP for mutating system state.
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


class EditAnsiblePlaybookAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(model_id="gpt-5.4"),
            system_prompt=SYSTEM_PROMPT,
            tools=[search_web, http_get],
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
