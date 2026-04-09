import pathlib
from typing import Literal

import pytest

from agent.playbook_drafter import (
    UnsupportedPlaybookRequest,
    classify_request,
    draft_playbook,
    render_review,
    save_playbook,
)
from agent.tools import GeneratedPlaybookDraft, normalize_playbook_name, write_playbook_file


class FakeDraftingAgent:
    def __init__(self, draft: GeneratedPlaybookDraft):
        self.draft = draft
        self.prompts: list[str] = []

    def structured_output(self, output_model, prompt: str):
        self.prompts.append(prompt)
        return output_model.model_validate(self.draft)


def make_draft(
    target: Literal["control", "cluster"] = "control", safe: bool = True
) -> GeneratedPlaybookDraft:
    group_tag = "control" if target == "control" else "cluster"
    return GeneratedPlaybookDraft(
        name=f"hello-{group_tag}-draft",
        description=f"Ping the {group_tag} node group.",
        target=target,
        safe=safe,
        tags=["connectivity", group_tag],
        reasoning_summary="Minimal connectivity check.",
        risk_notes=["Uses ansible.builtin.ping only."],
        playbook_yaml="\n".join(
            [
                f"# name: hello-{group_tag}-draft",
                f"# description: Ping the {group_tag} node group.",
                f"# target: {target}",
                f"# safe: {'true' if safe else 'false'}",
                "# tags:",
                "#   - connectivity",
                f"#   - {group_tag}",
                "",
                f"- hosts: {target}",
                "  become: yes",
                "  tasks:",
                "    - name: Ping",
                "      ping:",
            ]
        ),
    )


def write_inventory(path: pathlib.Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[control]",
                "localhost ansible_connection=local",
                "",
                "[cluster]",
                "tp1 ansible_host=tp1",
            ]
        ),
        encoding="utf-8",
    )


def test_classify_request_control():
    assert classify_request("create a hello world playbook for local nodes") == "control"


def test_classify_request_cluster():
    assert classify_request("draft a remote playbook for cluster nodes") == "cluster"


def test_classify_request_workers_alias():
    assert classify_request("draft a remote playbook for workers") == "cluster"


def test_classify_request_rejects_unsupported():
    with pytest.raises(UnsupportedPlaybookRequest):
        classify_request("draft something for the database tier")


def test_normalize_playbook_name():
    assert normalize_playbook_name("Hello World Workers!") == "hello-world-workers"


def test_write_playbook_file_rejects_collisions(tmp_path: pathlib.Path):
    draft = make_draft()
    existing = tmp_path / "hello-control-draft.yaml"
    existing.write_text("occupied\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_playbook_file(draft, tmp_path)


def test_draft_playbook_for_control(tmp_path: pathlib.Path):
    inventory = tmp_path / "inventory.ini"
    write_inventory(inventory)
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    review = draft_playbook(
        FakeDraftingAgent(make_draft("control")),
        "create a hello world playbook for local nodes",
        playbooks_dir=playbooks_dir,
        inventory_path=inventory,
    )

    assert review.draft.target == "control"
    assert review.draft.safe is True
    assert review.proposed_path == playbooks_dir / "hello-control-draft.yaml"
    assert "approval" in review.warning.lower()


def test_draft_playbook_for_cluster(tmp_path: pathlib.Path):
    inventory = tmp_path / "inventory.ini"
    write_inventory(inventory)
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    review = draft_playbook(
        FakeDraftingAgent(make_draft("cluster")),
        "draft a remote hello world playbook for cluster nodes",
        playbooks_dir=playbooks_dir,
        inventory_path=inventory,
    )

    assert review.draft.target == "cluster"
    assert review.proposed_path == playbooks_dir / "hello-cluster-draft.yaml"


def test_rejection_does_not_create_files(tmp_path: pathlib.Path):
    inventory = tmp_path / "inventory.ini"
    write_inventory(inventory)
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    review = draft_playbook(
        FakeDraftingAgent(make_draft("control")),
        "create a hello world playbook for local nodes",
        playbooks_dir=playbooks_dir,
        inventory_path=inventory,
    )
    result = save_playbook(review.draft, approved=False, playbooks_dir=playbooks_dir)

    assert result is None
    assert list(playbooks_dir.iterdir()) == []


def test_approval_creates_file(tmp_path: pathlib.Path):
    inventory = tmp_path / "inventory.ini"
    write_inventory(inventory)
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    review = draft_playbook(
        FakeDraftingAgent(make_draft("control")),
        "create a hello world playbook for local nodes",
        playbooks_dir=playbooks_dir,
        inventory_path=inventory,
    )
    result = save_playbook(review.draft, approved=True, playbooks_dir=playbooks_dir)

    assert result == playbooks_dir / "hello-control-draft.yaml"
    assert result.read_text(encoding="utf-8").startswith("# name: hello-control-draft")


def test_build_review_text_includes_yaml(tmp_path: pathlib.Path):
    inventory = tmp_path / "inventory.ini"
    write_inventory(inventory)
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    review = draft_playbook(
        FakeDraftingAgent(make_draft("control", safe=False)),
        "create a hello world playbook for local nodes",
        playbooks_dir=playbooks_dir,
        inventory_path=inventory,
    )
    rendered = render_review(review)

    assert "Safety: False" in rendered
    assert "Playbook YAML:" in rendered
    assert "# safe: false" in rendered
