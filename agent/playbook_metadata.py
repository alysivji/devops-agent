from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .tools import get_ansible_playbook_registry
from .utils import build_agent, build_model

SYSTEM_PROMPT = """
Role:
You draft metadata for Ansible playbooks in this repository.

Repo constraints:
- Metadata must match the actual playbook YAML.
- The only supported targets in v1 are `control` and `cluster`.
- Use concise registry-friendly names, descriptions, and tags.
- Do not create files.
"""


class GeneratedPlaybookMetadata(BaseModel):
    name: str
    description: str
    target: Literal["control", "cluster"]
    tags: list[str]


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

Return:
- name
- description
- target
- tags
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
