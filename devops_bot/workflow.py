from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict
from uuid import uuid4

from .history import (
    RUN_HISTORY_PATH,
    RunHistory,
    append_session_jsonl,
    record_event,
    reset_active_run_history,
    run_history_enabled,
    set_active_run_history,
)
from .session import get_session_storage_event_details

if TYPE_CHECKING:
    from .agents.orchestrator import OrchestratorAgent
    from .approval import ApprovalRequest

type JSONPrimitive = None | bool | int | float | str
type JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
type EventSink = Callable[["WorkflowEvent"], None]
type ApprovalResolver = Callable[["ApprovalRequest"], bool]


class WorkflowAgent(Protocol):
    def run(self, prompt: str) -> str: ...


class InteractiveAdapter(Protocol):
    def render_event(self, event: "WorkflowEvent") -> None: ...

    def resolve_approval(self, request: "ApprovalRequest") -> bool: ...


type AgentFactory = Callable[[str], WorkflowAgent]


class WorkflowEvent(TypedDict, total=False):
    kind: Literal[
        "run_started",
        "status",
        "message",
        "preview",
        "notice",
        "approval_requested",
        "approval_resolved",
        "run_completed",
        "run_failed",
    ]
    role: Literal["user", "agent", "system", "error"]
    text: str
    level: Literal["info", "warning", "error"]
    title: str
    body: str
    preview_type: str
    approved: bool
    prompt: str
    request_kind: str
    context: dict[str, JSONValue]


@dataclass(slots=True)
class WorkflowRuntime:
    # `contextvars` is the ambient bridge for framework-managed callbacks such as
    # Strands tool functions and hooks, which do not naturally receive a runtime argument.
    event_sink: EventSink
    approval_resolver: ApprovalResolver

    def emit(self, event: WorkflowEvent) -> None:
        self.event_sink(event)

    def resolve_approval(self, request: ApprovalRequest) -> bool:
        return self.approval_resolver(request)


@dataclass(slots=True)
class WorkflowResult:
    status: Literal["completed", "failed", "paused_for_approval"]
    response: str | None = None
    error: str | None = None
    approval_request: ApprovalRequest | None = None


_current_workflow_runtime: ContextVar[WorkflowRuntime | None] = ContextVar(
    "workflow_runtime",
    default=None,
)


def set_workflow_runtime(runtime: WorkflowRuntime) -> Token[WorkflowRuntime | None]:
    return _current_workflow_runtime.set(runtime)


def reset_workflow_runtime(token: Token[WorkflowRuntime | None]) -> None:
    _current_workflow_runtime.reset(token)


def get_workflow_runtime() -> WorkflowRuntime | None:
    return _current_workflow_runtime.get()


def emit_event(event: WorkflowEvent) -> None:
    runtime = get_workflow_runtime()
    if runtime is None:
        return
    runtime.emit(event)


def emit_status(text: str) -> None:
    emit_event({"kind": "status", "text": text})


def emit_message(role: Literal["user", "agent", "system", "error"], text: str) -> None:
    emit_event({"kind": "message", "role": role, "text": text})


def emit_notice(text: str, *, level: Literal["info", "warning", "error"] = "info") -> None:
    emit_event({"kind": "notice", "text": text, "level": level})


def emit_preview(
    *,
    preview_type: str,
    title: str,
    body: str,
    metadata: dict[str, JSONValue] | None = None,
) -> None:
    emit_event(
        {
            "kind": "preview",
            "preview_type": preview_type,
            "title": title,
            "body": body,
            "context": metadata or {},
        }
    )


class AgentWorkflow:
    def __init__(
        self,
        *,
        session_id: str | None = None,
        agent_factory: AgentFactory | None = None,
    ) -> None:
        self._agent_factory = agent_factory or self._default_agent_factory
        self.session_id = session_id or uuid4().hex
        self._agent = self._agent_factory(self.session_id)

    def reset(self) -> None:
        self.session_id = uuid4().hex
        self._agent = self._agent_factory(self.session_id)

    def run(
        self,
        prompt: str,
        *,
        event_sink: EventSink,
        approval_resolver: ApprovalResolver,
    ) -> WorkflowResult:
        from .approval import WaitingForApproval

        runtime = WorkflowRuntime(
            event_sink=event_sink,
            approval_resolver=approval_resolver,
        )
        runtime_token = set_workflow_runtime(runtime)
        run_history = RunHistory(prompt=prompt) if run_history_enabled() else None
        history_token = set_active_run_history(run_history) if run_history is not None else None

        try:
            emit_event({"kind": "run_started", "prompt": prompt})
            emit_status("Running...")

            if run_history is not None:
                record_event(
                    kind="run_started",
                    status="started",
                    what="Started chat turn.",
                    why="Capture the user message before orchestration begins.",
                    details={"prompt": prompt},
                )
                session_details = get_session_storage_event_details(session_id=self.session_id)
                if session_details is not None:
                    record_event(
                        kind="session_storage_configured",
                        status="configured",
                        what="Configured Strands session storage.",
                        why=(
                            "Persist agent messages and state separately from the "
                            "JSONL run history."
                        ),
                        details=session_details,
                    )

            try:
                response = self._agent.run(prompt)
            except WaitingForApproval as exc:
                if run_history is not None:
                    record_event(
                        kind="run_paused",
                        status="paused",
                        what="Chat turn paused for approval.",
                        why=(
                            "The workflow stopped cleanly while waiting for approval "
                            "to be resolved."
                        ),
                        details={
                            "prompt": exc.request["prompt"],
                            "request_kind": exc.request["kind"],
                        },
                    )
                return WorkflowResult(
                    status="paused_for_approval",
                    approval_request=exc.request,
                )
            except Exception as exc:
                if run_history is not None:
                    record_event(
                        kind="run_failed",
                        status="failed",
                        what="Chat turn failed.",
                        why="The orchestrator raised an exception.",
                        details={"error": str(exc), "exception_type": exc.__class__.__name__},
                    )
                    run_history.finalize(f"failed: {exc}")
                    self._append_run_history(run_history)
                emit_message("error", str(exc))
                emit_event({"kind": "run_failed", "text": str(exc)})
                return WorkflowResult(status="failed", error=str(exc))

            if run_history is not None:
                record_event(
                    kind="run_completed",
                    status="completed",
                    what="Chat turn completed successfully.",
                    why="Persist the agent response for later review.",
                    details={"response": response},
                )
                run_history.finalize(response)
                self._append_run_history(run_history)

            emit_message("agent", response)
            emit_event({"kind": "run_completed", "text": response})
            return WorkflowResult(status="completed", response=response)
        finally:
            emit_status("")
            if history_token is not None:
                reset_active_run_history(history_token)
            reset_workflow_runtime(runtime_token)

    @staticmethod
    def _default_agent_factory(session_id: str) -> OrchestratorAgent:
        from .agents.orchestrator import OrchestratorAgent

        return OrchestratorAgent(session_id=session_id)

    @staticmethod
    def _append_run_history(run_history: RunHistory) -> None:
        try:
            append_session_jsonl(run_history.session, RUN_HISTORY_PATH)
        except OSError as exc:
            emit_notice(f"Failed to write run history: {exc}", level="warning")
