import sys
from uuid import uuid4

from .agents.orchestrator import OrchestratorAgent
from .approval import reset_approval_handler, set_approval_handler
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
from .ui import UIProtocol


class AgentRunner:
    def __init__(self, ui: UIProtocol) -> None:
        self._ui = ui
        self.session_id, self._agent = self._new_session()

    def reset(self) -> None:
        self.session_id, self._agent = self._new_session()

    def run(self, prompt: str) -> None:
        set_approval_handler(self._ui.get_approval)
        self._ui.set_status("Running...")
        run_history = RunHistory(prompt=prompt) if run_history_enabled() else None
        token = set_active_run_history(run_history) if run_history is not None else None

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
                    why=("Persist agent messages and state separately from the JSONL run history."),
                    details=session_details,
                )

        try:
            response = self._agent.run(prompt)
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
            self._ui.post_message("error", str(exc))
            return
        finally:
            self._ui.clear_status()
            reset_approval_handler()
            if token is not None:
                reset_active_run_history(token)

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

        self._ui.post_message("agent", response)

    def _append_run_history(self, run_history: RunHistory) -> None:
        try:
            append_session_jsonl(run_history.session, RUN_HISTORY_PATH)
        except OSError as exc:
            print(f"Failed to write run history: {exc}", file=sys.stderr)

    @staticmethod
    def _new_session() -> tuple[str, OrchestratorAgent]:
        session_id = uuid4().hex
        return session_id, OrchestratorAgent(session_id=session_id)
