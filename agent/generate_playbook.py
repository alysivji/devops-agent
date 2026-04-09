import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from .tools.ansible import get_ansible_inventory_groups
from .utils import build_agent, build_model

SYSTEM_PROMPT = """
Role:
You generate Ansible playbooks.

Repo constraints:
- Return valid Ansible playbook YAML only.
- Do not create files.
- Do not include commentary outside the YAML returned.

Supported targets:
- `control`: execution on the control node
- `cluster`: execution on the Raspberry Pi cluster nodes

Hardware and role context:
- The `control` node is an Intel i5-6500T system with 16GB DDR4 RAM.
- The `control` node hosts control plane and management services.
- The `cluster` nodes are Raspberry Pi Compute Module 3+ systems.
- The `cluster` nodes run distributed workloads and containers.
"""


class GeneratedPlaybookYaml(BaseModel):
    yaml: str = Field(description="Rendered Ansible playbook YAML as a non-empty top-level list.")

    @field_validator("yaml")
    @classmethod
    def validate_playbook_yaml(cls, value: str) -> str:
        parsed = yaml.safe_load(value)
        if not isinstance(parsed, list) or not parsed:
            raise ValidationError("generated playbook YAML must be a non-empty YAML list")
        return value


class GeneratePlaybookAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(),
            system_prompt=SYSTEM_PROMPT,
            # TODO add web search and http request tools for getting info
            tools=[get_ansible_inventory_groups],
        )

    def run(self, prompt: str) -> GeneratedPlaybookYaml:
        generated_playbook = self.agent.structured_output(GeneratedPlaybookYaml, prompt)
        return generated_playbook
