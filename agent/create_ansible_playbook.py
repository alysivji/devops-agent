import re
from pathlib import Path

from pydantic import BaseModel
from strands import tool

from .generate_playbook import GeneratePlaybookAgent
from .playbook_metadata import GeneratedPlaybookMetadata, PlaybookMetadataAgent

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
        generated_playbook = self.generator.run(query)
        generated_metadata = self.metadata_agent.run(yaml=generated_playbook.yaml)
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

        written = confirm_write(playbook_path)
        if not written:
            print("Playbook not written.")
            return CreateAnsiblePlaybookResult(
                path=playbook_path,
                metadata=generated_metadata,
                rendered_playbook=rendered_playbook,
                written=False,
            )

        playbook_path.write_text(rendered_playbook, encoding="utf-8")
        print(f"Wrote playbook to {playbook_path}.")
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
