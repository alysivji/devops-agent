import yaml
from pydantic import BaseModel, Field, field_validator

from .run_history import record_event
from .tools import get_ansible_inventory_groups, http_get, search_web
from .tools.ansible import check_ansible_playbook_syntax
from .utils import build_agent, build_model

SYSTEM_PROMPT = """
## Execution Contract
You generate Ansible playbooks that are safe, idempotent, and verifiable.

## Output Requirements
- Return valid Ansible playbook YAML only.
- Do not create or reference external files.
- Do not include any commentary outside the YAML.
- Structure playbooks so they can be executed directly with `ansible-playbook`.

## Operational Guarantees
- Prefer idempotent tasks and Ansible modules over shell commands.
- Avoid shell unless no suitable module exists.
- Ensure tasks are safe to re-run without causing unintended changes.

## State Validation (Required)
- Every playbook must verify that the desired state was achieved.
- Use retries, waits, and polling for distributed systems.
- Include explicit assertions that fail if the system is not in the expected state.

## Failure Handling (Required)
- Task names must clearly describe the intended state being enforced or validated.
- All validation steps must use explicit assertions with clear, actionable failure messages.
- When a validation step fails, include structured debug output that captures relevant
  state (e.g., command output, status).
- Prefer `block`/`rescue` patterns for critical validation steps to emit failure context
  before failing.

## Resilience & Recovery
- Include an optional reset or teardown mechanism controlled via a variable
  (e.g., `*_reset: false`).
- Reset operations must be safe, explicit, and not run by default.

## Observability
- Emit structured debug output summarizing the final system state.
- Output must be machine-readable where possible (e.g., JSON-like dictionaries).
- Surface key values (e.g., endpoints, node counts, status).

## Execution Targets
- `control`: control plane node (Intel i5-6500T, 16GB RAM)
- `cluster`: Raspberry Pi Compute Module 3+ worker nodes

## Research Guidance
- Use `search_web` for up-to-date package names, module syntax, or distro-specific behavior.
- Prefer official upstream/vendor documentation.
- Use `http_get` only for reading documentation.
- Never use HTTP for mutating system state.
"""


class GeneratedPlaybookYaml(BaseModel):
    yaml: str = Field(description="Rendered Ansible playbook YAML as a non-empty top-level list.")

    @field_validator("yaml")
    @classmethod
    def validate_playbook_yaml(cls, value: str) -> str:
        parsed = yaml.safe_load(value)
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("generated playbook YAML must be a non-empty YAML list")
        check_ansible_playbook_syntax(value)
        return value


class GeneratePlaybookAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(model_id="gpt-5.4"),
            system_prompt=SYSTEM_PROMPT,
            tools=[get_ansible_inventory_groups, search_web, http_get],
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
