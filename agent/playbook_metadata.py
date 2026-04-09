from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .tools import get_ansible_playbook_registry
from .utils import build_agent, build_model

SYSTEM_PROMPT = """
Role:
You draft metadata for Ansible playbooks in this repository.

Repo constraints:
- Keep metadata consistent with the YAML
- Use concise registry-friendly names, descriptions, and tags.
- Do not create files.
"""


class GeneratedPlaybookMetadata(BaseModel):
    """Structured metadata for a generated Ansible playbook."""

    name: str = Field(description="Concise registry-friendly playbook name.")
    description: str = Field(
        description="Short summary of what the playbook does, consistent with the YAML."
    )
    target: Literal["control", "cluster"] = Field(
        description="Inventory target where the playbook is intended to run."
    )
    tags: list[str] = Field(description="Short registry tags that classify the playbook's purpose.")
    safe_to_run: bool = Field(
        default=True,
        description=(
            "Whether the playbook appears safe to run without human review "
            "because it does not include destructive actions."
        ),
    )


def build_metadata_prompt(
    user_request: str,
    *,
    target: str,
    playbook_yaml: str,
    existing_playbooks: list[dict[str, str | bool | list[str]]],
) -> str:
    return f"""\
Draft metadata for this Ansible playbook request:
{user_request}

Known context:
- Target inventory group: `{target}`
- Existing playbook registry entries: {existing_playbooks}

Generated playbook YAML:
```yaml
{playbook_yaml.strip()}
```

Requirements:
- Keep metadata consistent with the YAML
- Use concise names and descriptions suitable for the playbook registry
- Mark `safe_to_run` as true when the playbook does not appear to include destructive actions
- Mark `safe_to_run` as false if the playbook appears risky or destructive

Return:
- name
- description
- target
- tags
- safe_to_run
"""


class PlaybookMetadataAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(model_id="gpt-4o-mini"),
            system_prompt=SYSTEM_PROMPT,
            tools=[get_ansible_playbook_registry],
        )

    def run(
        self,
        prompt: str,
        *,
        target: str,
        playbook_yaml: str,
        existing_playbooks: list[dict[str, str | bool | list[str]]],
    ) -> GeneratedPlaybookMetadata:
        metadata_prompt = build_metadata_prompt(
            prompt,
            target=target,
            playbook_yaml=playbook_yaml,
            existing_playbooks=existing_playbooks,
        )
        return self.agent.structured_output(GeneratedPlaybookMetadata, metadata_prompt)
