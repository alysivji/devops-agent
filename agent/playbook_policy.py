from __future__ import annotations

import pathlib
from dataclasses import dataclass

from .playbook_metadata import GeneratedPlaybookMetadata
from .tools import (
    AnsiblePlaybookMetadata,
    build_playbook_path,
    render_metadata_header,
    write_playbook_file,
)


@dataclass(frozen=True)
class PolicyDecision:
    safe: bool
    summary: str
    risk_notes: list[str]
    warning: str


@dataclass(frozen=True)
class PlaybookDraft:
    metadata: GeneratedPlaybookMetadata
    playbook_yaml: str


@dataclass(frozen=True)
class PlaybookReview:
    draft: PlaybookDraft
    proposed_path: pathlib.Path
    policy: PolicyDecision


def evaluate_playbook_policy(playbook_yaml: str, *, target: str) -> PolicyDecision:
    normalized = playbook_yaml.lower()
    ping_only = " ping:" in normalized or " ansible.builtin.ping:" in normalized

    if ping_only:
        return PolicyDecision(
            safe=True,
            summary=f"Minimal connectivity check for the {target} group.",
            risk_notes=["Uses ansible ping only and should not change system state."],
            warning=(
                "This draft is a non-destructive connectivity check, but still requires approval."
            ),
        )

    return PolicyDecision(
        safe=False,
        summary=f"Playbook for the {target} group may change system state.",
        risk_notes=["Contains tasks beyond a connectivity check and needs manual review."],
        warning="This draft is marked unsafe and still requires explicit approval before creation.",
    )


def build_playbook_review(
    metadata: GeneratedPlaybookMetadata,
    playbook_yaml: str,
    *,
    playbooks_dir: pathlib.Path = pathlib.Path("ansible/playbooks"),
) -> PlaybookReview:
    proposed_path = build_playbook_path(metadata.name, playbooks_dir)
    if proposed_path.exists():
        raise FileExistsError(f"Playbook already exists: {proposed_path}")

    return PlaybookReview(
        draft=PlaybookDraft(metadata=metadata, playbook_yaml=playbook_yaml),
        proposed_path=proposed_path,
        policy=evaluate_playbook_policy(playbook_yaml, target=metadata.target),
    )


def render_review(review: PlaybookReview) -> str:
    metadata = review.draft.metadata
    risk_header = "Warning" if not review.policy.safe else "Safety"
    risk_notes = "\n".join(f"- {note}" for note in review.policy.risk_notes) or "- None"
    return "\n".join(
        [
            f"Proposed file: {review.proposed_path}",
            f"Target group: {metadata.target}",
            f"Safety: {review.policy.safe}",
            f"Summary: {review.policy.summary}",
            f"{risk_header}: {review.policy.warning}",
            "Risk notes:",
            risk_notes,
            "",
            "Metadata header:",
            render_metadata_header(
                AnsiblePlaybookMetadata(
                    name=metadata.name,
                    description=metadata.description,
                    target=metadata.target,
                    safe=review.policy.safe,
                    tags=metadata.tags,
                )
            ),
            "",
            "Playbook YAML:",
            review.draft.playbook_yaml.strip(),
        ]
    )


def save_playbook(
    draft: PlaybookDraft,
    *,
    approved: bool,
    playbooks_dir: pathlib.Path = pathlib.Path("ansible/playbooks"),
) -> pathlib.Path | None:
    if not approved:
        return None

    policy = evaluate_playbook_policy(draft.playbook_yaml, target=draft.metadata.target)
    return write_playbook_file(
        AnsiblePlaybookMetadata(
            name=draft.metadata.name,
            description=draft.metadata.description,
            target=draft.metadata.target,
            safe=policy.safe,
            tags=draft.metadata.tags,
        ),
        draft.playbook_yaml,
        playbooks_dir,
    )
