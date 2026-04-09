from __future__ import annotations

from pydantic import BaseModel

from .tools import get_ansible_inventory_groups
from .utils import build_agent, build_model, validate_generated_playbook_yaml

SYSTEM_PROMPT = """
Role:
You draft Ansible playbooks for this repository.

Repo constraints:
- Return valid Ansible playbook YAML only.
- Do not create files.
- Do not include commentary outside the YAML returned in `playbook_yaml`.

Supported targets:
- `control`: local execution on the control node
- `cluster`: remote execution over SSH on the Raspberry Pi cluster nodes

Hardware and role context:
- The `control` node is an Intel i5-6500T system with 16GB DDR4 RAM.
- The `control` node hosts control plane and management services.
- The `cluster` nodes are Raspberry Pi Compute Module 3+ systems.
- The `cluster` nodes run distributed workloads and containers.
"""


class UnsupportedPlaybookRequest(ValueError):
    pass


class GeneratedPlaybookYaml(BaseModel):
    playbook_yaml: str


def classify_request(user_prompt: str) -> str:
    normalized = user_prompt.lower()

    control_terms = ("local", "localhost", "control")
    cluster_terms = ("remote", "cluster", "worker", "workers")

    if any(term in normalized for term in control_terms):
        return "control"
    if any(term in normalized for term in cluster_terms):
        return "cluster"

    raise UnsupportedPlaybookRequest(
        "Request must clearly target either the control node or cluster nodes."
    )


def build_generation_prompt(user_prompt: str, *, target: str) -> str:
    return f"""\
Generate Ansible playbook YAML for this request:
{user_prompt}

Target inventory group: `{target}`

Requirements:
- Return valid YAML only
- Set `hosts` to `{target}`
"""


class PlaybookDraftAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(),
            system_prompt=SYSTEM_PROMPT,
            tools=[get_ansible_inventory_groups],
        )

    def run(self, prompt: str, *, target: str) -> GeneratedPlaybookYaml:
        playbook_prompt = build_generation_prompt(prompt, target=target)
        draft = self.agent.structured_output(GeneratedPlaybookYaml, playbook_prompt)
        validate_generated_playbook_yaml(draft.playbook_yaml)
        return draft
