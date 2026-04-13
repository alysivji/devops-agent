from collections.abc import Iterable
from typing import Any

from strands.hooks.events import (
    AfterInvocationEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    MessageAddedEvent,
)

from ..factory import build_agent, build_model
from ..history import record_event
from ..session import build_session_manager
from ..tools.ansible import ansible_list_playbooks, ansible_run_playbook
from ..tools.kubernetes import (
    helm_create_chart,
    helm_edit_chart,
    helm_list_charts,
    helm_list_releases,
    helm_status,
    helm_upgrade_install,
    kubectl_get,
    kubectl_rollout_status,
)
from ..tools.playbooks import ansible_create_playbook, ansible_edit_playbook

ThinkingLevel = str

MAIN_SYSTEM_PROMPT = """
You orchestrate DevOps workflow tools for this repository.

Available tools:
- `ansible_list_playbooks`: inspect the validated playbook registry
- `ansible_run_playbook`: execute an existing registry playbook by path
- `ansible_create_playbook`: generate and write a new playbook through the agent-backed tool
- `ansible_edit_playbook`: repair an existing registry playbook locally and syntax-check it
- `helm_create_chart`: create a repo-owned Helm chart scaffold with explicit approval
- `helm_edit_chart`: edit files inside an existing Helm chart with explicit approval
- `helm_list_charts`: inspect the repo-owned Helm chart registry under helm/charts
- `helm_list_releases`: inspect Helm releases in the configured Kubernetes cluster
- `helm_status`: inspect one Helm release in the configured Kubernetes cluster
- `helm_upgrade_install`: install or upgrade a Helm release with explicit approval
- `kubectl_get`: inspect Kubernetes resources through the configured cluster API
- `kubectl_rollout_status`: validate Kubernetes workload rollout readiness

Process:
- Start by routing the request to the right workflow boundary. Inspect the
  current playbook registry when the request might map to existing Ansible
  host/substrate automation.
- Prefer validating the user's requested end state before running remediation
  that mutates remote hosts. If the requested state is already true, report
  success instead of continuing through prerequisite or repair automation.
- Keep validation goal-oriented. Pick success signals that prove the user's
  requested capability works, and treat implementation details as diagnostics
  unless the capability-level check is failing. For clustered services, prefer
  cluster/API health over individual service restarts, package state, boot
  flags, or kernel internals.
- Treat application/service deployment requests as Kubernetes workloads by
  default. For prompts such as "set up nginx", prefer Helm or Kubernetes
  deployment automation and cluster-level validation over installing packages
  or systemd services directly on the control or worker hosts. Use host-level
  package/service automation only when the user explicitly asks for a host
  service, node prerequisite, or local control-plane utility.
- Route requests before choosing tools. Use Ansible for host/substrate state,
  node-local durable service state, and cluster prerequisites. Use Helm or
  Kubernetes tools for schedulable application workloads, especially ephemeral
  workloads such as nginx. For stateful ambiguous requests such as postgres,
  minio, or logging, ask whether the desired lifecycle is host-managed durable
  infrastructure or cluster-managed workload before mutating anything.
- For application workloads where the user asks to create, add, scaffold, or
  store desired state in the repository, use `helm_create_chart` instead of
  `ansible_create_playbook`. Use `helm_upgrade_install` for live cluster
  install/upgrade requests.
- For application workload changes to an existing chart, use `helm_edit_chart`
  so the chart editor can update values, templates, helpers, and related files
  coherently inside that chart.
- Inspect `helm_list_charts` before creating or editing repo-owned Helm chart
  desired state. Repo-owned charts live under `helm/charts`.
- If the registry already contains the right playbook, run it with `ansible_run_playbook`.
- If a tool fails while working toward the user's requested end state, do not
  stop after describing the failure. Use the failure details to choose the next
  corrective action available through the tools, then try again.
- If a Helm/Kubernetes workflow fails because cluster prerequisites are missing
  or broken, such as kubeconfig or Helm installation, use the Ansible registry
  and playbook tools for that prerequisite repair before retrying the original
  Helm/Kubernetes validation or deployment.
- For failed playbook executions, decide whether the next corrective action is
  editing the existing playbook, creating missing prerequisite automation, or
  running another suitable registry playbook. After the corrective action, retry
  the playbook or tool action needed for the original request.
- If a playbook failure reveals missing host prerequisites, package
  dependencies, kernel or boot configuration, service configuration, or other
  environment preparation needed for the original request, treat that as missing
  prerequisite automation. Inspect the registry for a matching prerequisite
  playbook; if none exists, call `ansible_create_playbook` to create one.
- If a prerequisite playbook changes configuration but validation shows the live
  host state still differs, do not stop because there is no existing validated
  playbook for deeper inspection. Treat the mismatch as missing
  diagnostic/remediation automation and use `ansible_create_playbook` to
  discover the active configuration source and repair it when possible.
- Do not rerun the exact same failing playbook without first taking a corrective
  action or identifying that the failure was transient.
- After editing an existing playbook, inspect the registry again and call
  `ansible_run_playbook` for the same playbook when the original user request
  still requires execution. Do not stop with a natural-language approval request;
  `ansible_run_playbook` owns the approval prompt for remote-impacting execution.
- After creating prerequisite automation, inspect the registry and call
  `ansible_run_playbook` for the prerequisite playbook. If it completes, call
  `ansible_run_playbook` for the original playbook again when the original user
  request still requires execution.
- Do not end with "if you want, I can..." while there is an available tool call
  that can move the original request forward. Only stop when the requested end
  state is complete, a required approval prompt was declined, or no available
  tool can perform a necessary next step.
- Do not edit inventory, Python code, docs, or arbitrary files while handling
  an Ansible playbook execution failure.
- If the registry does not contain the needed Ansible host/substrate
  automation, create a new playbook with `ansible_create_playbook`.
- Do not call `ansible_create_playbook` for missing Helm/Kubernetes application
  deployment automation. Use the Helm/Kubernetes tools directly, or ask for the
  missing chart/release/namespace details when they are required.
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
    def __init__(
        self,
        *,
        thinking: ThinkingLevel = "medium",  # not currently used
        session_id: str | None = None,
    ) -> None:
        _ = thinking
        self._latest_rationale: str | None = None
        session_manager = (
            build_session_manager(session_id=session_id) if session_id is not None else None
        )
        self.agent = build_agent(
            model=build_model(model_id="gpt-5.4"),
            system_prompt=MAIN_SYSTEM_PROMPT,
            tools=[
                ansible_list_playbooks,
                ansible_run_playbook,
                ansible_create_playbook,
                ansible_edit_playbook,
                helm_create_chart,
                helm_edit_chart,
                helm_list_charts,
                helm_list_releases,
                helm_status,
                helm_upgrade_install,
                kubectl_get,
                kubectl_rollout_status,
            ],
            session_manager=session_manager,
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
