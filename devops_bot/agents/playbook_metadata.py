from typing import Literal

from pydantic import BaseModel, Field

from ..factory import build_agent, build_model
from ..history import record_event

SYSTEM_PROMPT = """
Role:
You draft metadata for Ansible playbooks.

Repo constraints:
- Keep metadata consistent with the YAML
- Use concise registry-friendly names and tags.
- Write a medium-sized one-line description with enough detail to identify
  the playbook in the registry. Prefer 25-45 words, and include the main
  action, target scope, important safety gates, and validation or rollback
  behavior when present in the YAML.
- Keep the description as plain text without Markdown, bullets, or newlines.
- Do not claim behavior that is not present in the YAML.
- Do not create files.
- Use `target: both` when the playbook installs or configures things on both host groups.
- Set `requires_approval` based on whether a human should approve execution
  before the playbook is run.
- Use `requires_approval: true` for playbooks that make remote changes, use
  privilege escalation, install or remove packages, restart services, reboot
  hosts, write system files, modify cluster state, or depend on external
  credentials or services. Use `false` only for low-risk local inspection or
  read-only checks.
- Use a lowercase snake_case name that reflects the requested outcome rather
  than an implementation detail.
- Use 3-6 short lowercase tags that cover the technology, action, and target
  area. Avoid duplicate or overly broad tags.
"""


class GeneratedPlaybookMetadata(BaseModel):
    """Structured metadata for a generated Ansible playbook."""

    name: str = Field(description="Concise registry-friendly playbook name.")
    description: str = Field(
        description=(
            "Medium-sized one-line summary, preferably 25-45 words, that describes "
            "the playbook's main action, target scope, and notable validation or "
            "safety behavior while staying consistent with the YAML."
        )
    )
    target: Literal["control", "cluster", "both"] = Field(
        description=(
            "Inventory target where the playbook is intended to run: "
            "`control`, `cluster`, or `both` when it applies to both groups."
        )
    )
    tags: list[str] = Field(description="Short registry tags that classify the playbook's purpose.")
    requires_approval: bool = Field(
        default=True,
        description=("Whether a human should approve execution before the playbook is run."),
    )


def build_metadata_prompt(yaml: str) -> str:
    return f"""\
Draft metadata for this Ansible playbook:

Generated playbook YAML:
```yaml
{yaml.strip()}
```
"""


class PlaybookMetadataAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(model_id="gpt-4o-mini"),
            system_prompt=SYSTEM_PROMPT,
        )

    def run(self, *, yaml: str) -> GeneratedPlaybookMetadata:
        metadata_prompt = build_metadata_prompt(yaml)
        record_event(
            kind="playbook_metadata_generation_started",
            status="started",
            what="Started structured metadata generation.",
            why=(
                "Draft registry metadata that matches the generated playbook before any file write."
            ),
            details={},
        )
        try:
            metadata = self.agent.structured_output(GeneratedPlaybookMetadata, metadata_prompt)
        except Exception as exc:
            record_event(
                kind="playbook_metadata_generation_failed",
                status="failed",
                what="Structured metadata generation failed.",
                why="The model did not return valid metadata for the generated playbook.",
                details={"error": str(exc), "exception_type": exc.__class__.__name__},
            )
            raise

        record_event(
            kind="playbook_metadata_generation_completed",
            status="completed",
            what="Structured metadata generation completed.",
            why="The playbook now has name, description, target, tags, and approval metadata.",
            details=metadata.model_dump(),
        )
        return metadata
