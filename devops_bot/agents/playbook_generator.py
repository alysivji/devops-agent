import yaml
from pydantic import BaseModel, Field, field_validator

from ..factory import build_agent, build_model
from ..history import record_event
from ..tools.ansible import ansible_list_inventory_groups, check_ansible_playbook_syntax
from ..tools.web import http_get, search_web

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
- Every playbook must verify that the user's requested end state was achieved,
  not every intermediate implementation detail.
- Prefer cheap, goal-oriented validation before remediation. If the requested
  end state is already true, skip disruptive or unnecessary mutation.
- For clustered services, use the cluster/API-level health signal as the primary
  success check when one exists. For example, a k3s install should verify that
  all expected nodes report `Ready`; service restarts, boot flags, package
  state, and kernel internals are diagnostics only when that end state is not
  met.
- Use retries, waits, and polling for distributed systems.
- Include explicit assertions that fail if the system is not in the expected state.
- Keep long-running remote service operations bounded. Avoid using
  `async`/`poll` as a timeout wrapper around `ansible.builtin.systemd`. Prefer
  module-native nonblocking behavior such as `no_block: true`, then validate the
  desired service or application state with retries/delay. Collect service
  status and logs in a rescue block when the platform exposes them. Do not let a
  service start/restart be the only place the playbook can wait indefinitely.

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
- When a task can reboot remote hosts, include an explicit reboot/wait/verify
  sequence in the playbook:
  - Read `/proc/sys/kernel/random/boot_id` before reboot on Linux hosts when
    the file exists.
  - Use `ansible.builtin.reboot` with conservative timeouts for low-power or
    slow-booting hosts (`reboot_timeout` of at least 1200 seconds,
    `connect_timeout` around 30 seconds, and `post_reboot_delay` of at least 20
    seconds).
  - Follow the reboot task with `ansible.builtin.wait_for_connection` using a
    matching timeout before collecting post-reboot facts or validation data.
  - Run `ansible.builtin.setup` after the connection returns.
  - Read `/proc/sys/kernel/random/boot_id` again and assert that it changed
    when a reboot was expected, then perform the desired-state validation.

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
            tools=[ansible_list_inventory_groups, search_web, http_get],
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
