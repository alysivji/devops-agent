import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from .run_history import record_event
from .tools import get_ansible_inventory_groups
from .utils import build_agent, build_model

SYSTEM_PROMPT = """
Role:
You generate Ansible playbooks.

Repo constraints:
- Return valid Ansible playbook YAML only.
- Do not create files.
- Do not include commentary outside the YAML returned.
- Prefer idempotent tasks and modules when practical for the requested automation.
- Avoid unnecessary shell commands when a purpose-built Ansible module can express the same change.

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
            model=build_model(model_id="gpt-5.4"),
            system_prompt=SYSTEM_PROMPT,
            # TODO add web search and http request tools for getting info
            tools=[get_ansible_inventory_groups],
        )

    def run(self, prompt: str) -> GeneratedPlaybookYaml:
        record_event(
            kind="structured_playbook_generation_started",
            status="started",
            what="Started structured playbook generation.",
            why="Translate the user request into valid Ansible YAML before any file write.",
            details={"prompt": prompt},
        )
        try:
            generated_playbook = self.agent.structured_output(GeneratedPlaybookYaml, prompt)
        except Exception as exc:
            record_event(
                kind="structured_playbook_generation_failed",
                status="failed",
                what="Structured playbook generation failed.",
                why="The model did not return valid playbook YAML for this request.",
                details={"error": str(exc), "exception_type": exc.__class__.__name__},
            )
            raise

        summary = summarize_generated_yaml(generated_playbook.yaml)
        record_event(
            kind="structured_playbook_generation_completed",
            status="completed",
            what="Structured playbook generation completed.",
            why="The generated YAML passed validation as a non-empty playbook list.",
            details=summary,
        )
        return generated_playbook


def summarize_generated_yaml(yaml_text: str) -> dict[str, int | list[str]]:
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
