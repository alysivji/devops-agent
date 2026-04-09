from .create_ansible_playbook import create_ansible_playbook
from .tools.ansible import get_ansible_playbook_registry, run_ansible_playbook
from .utils import build_agent, build_model

ThinkingLevel = str

MAIN_SYSTEM_PROMPT = """
You orchestrate Ansible playbook workflows for this repository.

Available tools:
- `get_ansible_playbook_registry`: inspect the validated playbook registry
- `run_ansible_playbook`: execute an existing registry playbook by path
- `create_ansible_playbook`: generate and write a new playbook through the agent workflow

Workflow:
- Start by inspecting the current playbook registry when the request might map
  to existing automation.
- If the registry already contains the right playbook, run it with `run_ansible_playbook`.
- If the registry does not contain the needed automation, create a new playbook
  with `create_ansible_playbook`.
- After creating a new playbook, inspect the registry again and run the appropriate playbook.
- For simple registry lookup questions, answer using the registry without
  creating or running anything.
- Do not invent playbook names or paths. Use the registry.
- Keep responses concise and concrete.
"""


class OrchestratorAgent:
    def __init__(self, *, thinking: ThinkingLevel = "medium") -> None:
        _ = thinking
        self.agent = build_agent(
            # The current Strands OpenAI adapter uses chat.completions for tool calls.
            # GPT-5 reasoning settings are rejected on that endpoint when tools are enabled.
            model=build_model(),
            system_prompt=MAIN_SYSTEM_PROMPT,
            tools=[
                get_ansible_playbook_registry,
                run_ansible_playbook,
                create_ansible_playbook,
            ],
        )

    def run(self, prompt: str) -> str:
        return str(self.agent(prompt)).strip()
