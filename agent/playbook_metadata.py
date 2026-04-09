from typing import Literal

from pydantic import BaseModel, Field

from .utils import build_agent, build_model

SYSTEM_PROMPT = """
Role:
You draft metadata for Ansible playbooks.

Repo constraints:
- Keep metadata consistent with the YAML
- Use concise registry-friendly names, descriptions, and tags.
- Do not create files.
- Use `target: both` when the playbook installs or configures things on both host groups.
- Set `requires_approval` based on whether a human should approve execution
  before the playbook is run.
"""


class GeneratedPlaybookMetadata(BaseModel):
    """Structured metadata for a generated Ansible playbook."""

    name: str = Field(description="Concise registry-friendly playbook name.")
    description: str = Field(
        description="Short summary of what the playbook does, consistent with the YAML."
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
        return self.agent.structured_output(GeneratedPlaybookMetadata, metadata_prompt)
