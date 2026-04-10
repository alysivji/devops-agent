from collections.abc import Iterable
from typing import Any

from strands.hooks.events import (
    AfterInvocationEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    MessageAddedEvent,
)

from .create_ansible_playbook import create_ansible_playbook
from .run_history import record_event
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
- Before each tool call, give one short operational sentence explaining what
  you are about to do and why.
- Keep those rationale sentences concrete and externally understandable.
- Do not reveal hidden reasoning or long narration.
- Keep responses concise and concrete.
"""


class OrchestratorAgent:
    def __init__(self, *, thinking: ThinkingLevel = "medium") -> None:
        _ = thinking
        self._latest_rationale: str | None = None
        self.agent = build_agent(
            model=build_model(model_id="gpt-5.4"),
            system_prompt=MAIN_SYSTEM_PROMPT,
            tools=[
                get_ansible_playbook_registry,
                run_ansible_playbook,
                create_ansible_playbook,
            ],
        )
        self.agent.add_hook(self._on_before_invocation, BeforeInvocationEvent)
        self.agent.add_hook(self._on_message_added, MessageAddedEvent)
        self.agent.add_hook(self._on_before_tool_call, BeforeToolCallEvent)
        self.agent.add_hook(self._on_after_tool_call, AfterToolCallEvent)
        self.agent.add_hook(self._on_after_invocation, AfterInvocationEvent)

    def run(self, prompt: str) -> str:
        return str(self.agent(prompt)).strip()

    def _on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        self._latest_rationale = None
        record_event(
            kind="orchestrator_invocation_started",
            status="started",
            what="Started orchestrator invocation.",
            why="Begin selecting whether to inspect, create, or run automation.",
            details={"message_count": len(event.messages or [])},
        )

    def _on_message_added(self, event: MessageAddedEvent) -> None:
        role = _get_message_field(event.message, "role")
        if role != "assistant":
            return

        text = _extract_message_text(event.message)
        if not text:
            return

        self._latest_rationale = text

    def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
        tool_name = _tool_name_from_use(event.tool_use)
        tool_arguments = _tool_arguments_from_use(event.tool_use)
        record_event(
            kind="tool_call_requested",
            status="started",
            what=f"Preparing to call tool `{tool_name}`.",
            why=self._latest_rationale or _fallback_rationale(),
            details={"tool_name": tool_name, "arguments": tool_arguments},
        )

    def _on_after_tool_call(self, event: AfterToolCallEvent) -> None:
        tool_name = _tool_name_from_use(event.tool_use)
        if event.exception is not None:
            record_event(
                kind="tool_call_completed",
                status="failed",
                what=f"Tool `{tool_name}` failed.",
                why=self._latest_rationale or _fallback_rationale(),
                details={
                    "tool_name": tool_name,
                    "error": str(event.exception),
                    "exception_type": event.exception.__class__.__name__,
                },
            )
            return

        record_event(
            kind="tool_call_completed",
            status="completed",
            what=f"Tool `{tool_name}` completed.",
            why=self._latest_rationale or _fallback_rationale(),
            details={
                "tool_name": tool_name,
                "result_preview": _summarize_value(event.result),
            },
        )

    def _on_after_invocation(self, event: AfterInvocationEvent) -> None:
        stop_reason = None
        if event.result is not None:
            stop_reason = getattr(event.result, "stop_reason", None)

        record_event(
            kind="orchestrator_invocation_completed",
            status="completed",
            what="Finished orchestrator invocation.",
            why="The orchestrator has completed its tool selection loop for this request.",
            details={"stop_reason": str(stop_reason) if stop_reason is not None else None},
        )


def _get_message_field(message: Any, field_name: str) -> Any:
    if isinstance(message, dict):
        return message.get(field_name)
    return getattr(message, field_name, None)


def _extract_message_text(message: Any) -> str | None:
    content = _get_message_field(message, "content")
    if isinstance(content, str):
        return content.strip() or None

    if not isinstance(content, Iterable):
        return None

    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
                continue
            nested_text = block.get("content")
            if isinstance(nested_text, str) and nested_text.strip():
                parts.append(nested_text.strip())
        else:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())

    if not parts:
        return None
    return " ".join(parts)


def _tool_name_from_use(tool_use: Any) -> str:
    if isinstance(tool_use, dict):
        name = tool_use.get("name")
        if isinstance(name, str) and name:
            return name
    name = getattr(tool_use, "name", None)
    if isinstance(name, str) and name:
        return name
    return "unknown_tool"


def _tool_arguments_from_use(tool_use: Any) -> dict[str, Any]:
    if isinstance(tool_use, dict):
        tool_input = tool_use.get("input")
        if isinstance(tool_input, dict):
            return dict(tool_input)
    tool_input = getattr(tool_use, "input", None)
    if isinstance(tool_input, dict):
        return dict(tool_input)
    return {}


def _summarize_value(value: Any) -> str:
    preview = str(value).strip()
    if len(preview) <= 200:
        return preview
    return f"{preview[:197]}..."


def _fallback_rationale() -> str:
    return "Tool selected by orchestrator to satisfy the current request."
