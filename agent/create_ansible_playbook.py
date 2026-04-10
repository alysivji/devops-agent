import re
from pathlib import Path

import yaml
from pydantic import BaseModel
from strands import tool

from .generate_playbook import GeneratePlaybookAgent
from .playbook_metadata import GeneratedPlaybookMetadata, PlaybookMetadataAgent
from .run_history import record_event

PLAYBOOKS_DIR = Path("ansible/playbooks")


class CreateAnsiblePlaybookResult(BaseModel):
    path: Path
    metadata: GeneratedPlaybookMetadata
    rendered_playbook: str
    written: bool


@tool
def create_ansible_playbook(query: str) -> Path | None:
    """
    Generate an Ansible playbook from a natural-language request.

    Args:
        query: A natural-language request describing the playbook to create

    Returns:
        The path to the written playbook under ansible/playbooks, or None if declined
    """
    result = CreateAnsiblePlaybookWorkflow().run(query)
    if not result.written:
        return None
    return result.path


class CreateAnsiblePlaybookWorkflow:
    def __init__(
        self,
        *,
        generator: GeneratePlaybookAgent | None = None,
        metadata_agent: PlaybookMetadataAgent | None = None,
    ) -> None:
        self.generator = generator or GeneratePlaybookAgent()
        self.metadata_agent = metadata_agent or PlaybookMetadataAgent()

    def run(self, query: str) -> CreateAnsiblePlaybookResult:
        record_event(
            kind="playbook_generation_started",
            status="started",
            what="Started generating a new playbook.",
            why="The registry did not contain a suitable existing playbook for the request.",
            details={"query": query},
        )
        generated_playbook = self.generator.run(query)
        playbook_summary = summarize_generated_playbook(generated_playbook.yaml)
        record_event(
            kind="playbook_yaml_generated",
            status="completed",
            what="Generated playbook YAML.",
            why="Draft the requested automation before reviewing metadata and filename.",
            details=playbook_summary,
        )
        generated_metadata = self.metadata_agent.run(yaml=generated_playbook.yaml)
        record_event(
            kind="playbook_metadata_generated",
            status="completed",
            what="Generated playbook metadata.",
            why="Summarize the new playbook with registry-friendly fields before any write.",
            details={
                "name": generated_metadata.name,
                "description": generated_metadata.description,
                "target": generated_metadata.target,
                "requires_approval": generated_metadata.requires_approval,
                "tags": generated_metadata.tags,
            },
        )
        playbook_path = build_playbook_path(generated_metadata.name)
        rendered_playbook = render_playbook_file(
            yaml=generated_playbook.yaml,
            metadata=generated_metadata,
        )

        print_preview(
            path=playbook_path,
            metadata=generated_metadata,
            rendered_playbook=rendered_playbook,
        )
        record_event(
            kind="playbook_preview_presented",
            status="completed",
            what="Presented the generated playbook preview.",
            why="Show the path, metadata, and YAML before asking for write approval.",
            details={"path": str(playbook_path), **playbook_summary},
        )

        written = confirm_write(playbook_path)
        if not written:
            print("Playbook not written.")
            record_event(
                kind="playbook_write_declined",
                status="declined",
                what="Playbook write was declined.",
                why=(
                    "The workflow requires explicit confirmation before "
                    "creating a new playbook file."
                ),
                details={"path": str(playbook_path), "approved": False},
            )
            return CreateAnsiblePlaybookResult(
                path=playbook_path,
                metadata=generated_metadata,
                rendered_playbook=rendered_playbook,
                written=False,
            )

        record_event(
            kind="playbook_write_approved",
            status="approved",
            what="Playbook write was approved.",
            why="The generated playbook is ready to be written under ansible/playbooks.",
            details={"path": str(playbook_path), "approved": True},
        )
        playbook_path.write_text(rendered_playbook, encoding="utf-8")
        print(f"Wrote playbook to {playbook_path}.")
        record_event(
            kind="playbook_written",
            status="completed",
            what="Wrote the generated playbook file.",
            why=(
                "Persist the approved playbook so it can be validated and "
                "executed through the registry."
            ),
            details={"path": str(playbook_path)},
        )
        return CreateAnsiblePlaybookResult(
            path=playbook_path,
            metadata=generated_metadata,
            rendered_playbook=rendered_playbook,
            written=True,
        )


def build_playbook_path(name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("generated metadata name did not produce a valid filename")
    return PLAYBOOKS_DIR / f"{slug}.yaml"


def confirm_write(path: Path) -> bool:
    response = input(f"Write playbook to {path}? [y/N]: ").strip().lower()
    return response in {"y", "yes"}


def render_playbook_file(*, yaml: str, metadata: GeneratedPlaybookMetadata) -> str:
    lines = [
        f"# name: {metadata.name}",
        f"# description: {metadata.description}",
        f"# target: {metadata.target}",
        f"# requires_approval: {str(metadata.requires_approval).lower()}",
        "# tags:",
    ]
    lines.extend(f"#   - {tag}" for tag in metadata.tags)
    lines.append("")
    lines.append(yaml.rstrip())
    lines.append("")
    return "\n".join(lines)


def print_preview(
    *, path: Path, metadata: GeneratedPlaybookMetadata, rendered_playbook: str
) -> None:
    print(f"Path: {path}")
    print("Metadata:")
    print(f"  name: {metadata.name}")
    print(f"  description: {metadata.description}")
    print(f"  target: {metadata.target}")
    print(f"  requires_approval: {str(metadata.requires_approval).lower()}")
    print("  tags:")
    for tag in metadata.tags:
        print(f"    - {tag}")
    print()
    print(rendered_playbook)


def summarize_generated_playbook(yaml_text: str) -> dict[str, str | int | list[str]]:
    parsed = yaml.safe_load(yaml_text)
    hosts: list[str] = []
    task_count = 0

    if isinstance(parsed, list):
        for play in parsed:
            if not isinstance(play, dict):
                continue
            hosts_value = play.get("hosts")
            if isinstance(hosts_value, str):
                hosts.append(hosts_value)
            tasks = play.get("tasks")
            if isinstance(tasks, list):
                task_count += len(tasks)

    return {"hosts": hosts, "task_count": task_count}
