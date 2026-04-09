from __future__ import annotations

import configparser
import pathlib
from dataclasses import dataclass
from typing import Protocol

from .tools import (
    GeneratedPlaybookDraft,
    build_playbook_path,
    get_ansible_playbook_registry,
    validate_generated_playbook_yaml,
    write_playbook_file,
)

INVENTORY_PATH = pathlib.Path("ansible/inventory.ini")
SUPPORTED_TARGETS = ("control", "cluster")

SYSTEM_PROMPT = """
Role:
You draft Ansible playbooks for this repository.

Repo constraints:
- The only supported targets in v1 are the inventory groups `control` and `cluster`.
- The first iteration only drafts a minimal hello-world connectivity playbook.
- Do not create files or assume approval has been granted.

Supported targets:
- `control`: local execution on the control node
- `cluster`: remote execution over SSH on the Raspberry Pi cluster nodes

Hardware and role context:
- The `control` node is an Intel i5-6500T system with 16GB DDR4 RAM.
- The `control` node is intended to host the control plane, observability sink, and related management services.
- The `cluster` nodes are Raspberry Pi Compute Module 3+ systems with 1.2GHz CPUs, 1GB LPDDR2 SDRAM, and 32GB eMMC storage.
- The `cluster` nodes are intended to run distributed workloads and containers, including Kubernetes workloads.

Safety policy:
- Use `safe: true` only for non-destructive checks such as Ansible ping/connectivity verification.
- Use `safe: false` for actions that change system state, edit files, install
  software, or restart services.

Output schema:
- Return a complete structured object matching the provided schema.
- `playbook_yaml` must contain the commented metadata header followed by valid YAML.
- Keep metadata and YAML fully consistent.

Approval rule:
- Always produce a draft only.
- A human must explicitly approve before any file is created.
"""


class StructuredDraftAgent(Protocol):
    def structured_output(
        self, output_model: type[GeneratedPlaybookDraft], prompt: str
    ) -> GeneratedPlaybookDraft: ...


class UnsupportedPlaybookRequest(ValueError):
    pass


@dataclass(frozen=True)
class PlaybookReview:
    draft: GeneratedPlaybookDraft
    inventory_groups: list[str]
    existing_playbooks: list[dict[str, str | bool | list[str]]]
    proposed_path: pathlib.Path
    warning: str


def list_inventory_groups(inventory_path: pathlib.Path = INVENTORY_PATH) -> list[str]:
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(inventory_path, encoding="utf-8")
    return sorted(
        section
        for section in parser.sections()
        if ":" not in section and section in SUPPORTED_TARGETS
    )


def classify_request(prompt: str) -> str:
    normalized = prompt.lower()
    if any(token in normalized for token in ("cluster", "worker", "workers", "remote")):
        return "cluster"
    if any(token in normalized for token in ("control", "local", "localhost")):
        return "control"
    raise UnsupportedPlaybookRequest(
        "Unsupported target request. Please specify either the control node or cluster nodes."
    )


def build_generation_prompt(
    user_request: str,
    *,
    target: str,
    inventory_groups: list[str],
    existing_playbooks: list[dict[str, str | bool | list[str]]],
) -> str:
    return f"""\
Draft a hello-world Ansible playbook for this request:
{user_request}

Requirements:
- Supported inventory groups in this repo: {", ".join(inventory_groups)}
- Target the `{target}` group
- Keep the playbook minimal and reversible
- Safety should be `true` for this hello-world connectivity check
- Existing playbook registry entries: {existing_playbooks}

Return:
- name
- description
- target
- safe
- tags
- reasoning_summary
- risk_notes
- playbook_yaml
"""


def draft_playbook(
    drafting_agent: StructuredDraftAgent,
    user_request: str,
    *,
    playbooks_dir: pathlib.Path = pathlib.Path("ansible/playbooks"),
    inventory_path: pathlib.Path = INVENTORY_PATH,
) -> PlaybookReview:
    target = classify_request(user_request)
    inventory_groups = list_inventory_groups(inventory_path)
    existing_playbooks = get_ansible_playbook_registry()
    prompt = build_generation_prompt(
        user_request,
        target=target,
        inventory_groups=inventory_groups,
        existing_playbooks=existing_playbooks,
    )
    draft = drafting_agent.structured_output(GeneratedPlaybookDraft, prompt)
    if draft.target != target:
        raise ValueError(f"Draft target mismatch: expected {target}, got {draft.target}")

    validate_generated_playbook_yaml(draft)
    proposed_path = build_playbook_path(draft.name, playbooks_dir)
    if proposed_path.exists():
        raise FileExistsError(f"Playbook already exists: {proposed_path}")

    warning = (
        "This draft is marked unsafe and still requires explicit approval before creation."
        if not draft.safe
        else "This draft is a non-destructive connectivity check, but still requires approval."
    )
    return PlaybookReview(
        draft=draft,
        inventory_groups=inventory_groups,
        existing_playbooks=existing_playbooks,
        proposed_path=proposed_path,
        warning=warning,
    )


def render_review(review: PlaybookReview) -> str:
    draft = review.draft
    risk_header = "Warning" if not draft.safe else "Safety"
    risk_notes = "\n".join(f"- {note}" for note in draft.risk_notes) or "- None"
    return "\n".join(
        [
            f"Proposed file: {review.proposed_path}",
            f"Target group: {draft.target}",
            f"Safety: {draft.safe}",
            f"Summary: {draft.reasoning_summary}",
            f"{risk_header}: {review.warning}",
            "Risk notes:",
            risk_notes,
            "",
            "Playbook YAML:",
            draft.playbook_yaml.strip(),
        ]
    )


def save_playbook(
    draft: GeneratedPlaybookDraft,
    *,
    approved: bool,
    playbooks_dir: pathlib.Path = pathlib.Path("ansible/playbooks"),
) -> pathlib.Path | None:
    if not approved:
        return None
    return write_playbook_file(draft, playbooks_dir)
