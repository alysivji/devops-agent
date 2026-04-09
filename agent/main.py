import argparse
import re
from pathlib import Path

from .generate_playbook import GeneratePlaybookAgent
from .playbook_metadata import GeneratedPlaybookMetadata, PlaybookMetadataAgent

PLAYBOOKS_DIR = Path("ansible/playbooks")


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Dev Ops Agent.")
    parser.add_argument("prompt", help="Natural-language prompt.")
    args = parser.parse_args()

    generated_playbook = GeneratePlaybookAgent().run(args.prompt)
    generated_metadata = PlaybookMetadataAgent().run(yaml=generated_playbook.yaml)
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

    if not confirm_write(playbook_path):
        print("Playbook not written.")
        return 0

    playbook_path.write_text(rendered_playbook)
    print(f"Wrote playbook to {playbook_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
