import readline  # noqa: F401 — enables line editing and up-arrow history as a side effect
import sys
from uuid import uuid4

from .agents.orchestrator import OrchestratorAgent
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

BANNER = """\
devops-agent chat
  /reset  start a new session (clears conversation history)
  /exit   quit  (also Ctrl-D)
"""


def _new_session() -> tuple[str, OrchestratorAgent]:
    session_id = uuid4().hex
    return session_id, OrchestratorAgent(session_id=session_id)


def _append_run_history(run_history: RunHistory) -> None:
    try:
        append_session_jsonl(run_history.session, RUN_HISTORY_PATH)
    except OSError as exc:
        print(f"Failed to write run history: {exc}", file=sys.stderr)


def main() -> int:
    print(BANNER)
    session_id, agent = _new_session()

    while True:
        try:
            user_input = input("you> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            break
        if user_input == "/reset":
            session_id, agent = _new_session()
            print("[new session started]\n")
            continue

        run_history = RunHistory(prompt=user_input) if run_history_enabled() else None
        token = set_active_run_history(run_history) if run_history is not None else None

        if run_history is not None:
            record_event(
                kind="run_started",
                status="started",
                what="Started chat turn.",
                why="Capture the user message before orchestration begins.",
                details={"prompt": user_input},
            )
            session_details = get_session_storage_event_details(session_id=session_id)
            if session_details is not None:
                record_event(
                    kind="session_storage_configured",
                    status="configured",
                    what="Configured Strands session storage.",
                    why="Persist agent messages and state separately from the JSONL run history.",
                    details=session_details,
                )

        try:
            response = agent.run(user_input)
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
                _append_run_history(run_history)
            if token is not None:
                reset_active_run_history(token)
            print(f"error: {exc}\n", file=sys.stderr)
            continue

        if run_history is not None:
            record_event(
                kind="run_completed",
                status="completed",
                what="Chat turn completed successfully.",
                why="Persist the agent response for later review.",
                details={"response": response},
            )
            run_history.finalize(response)
            _append_run_history(run_history)

        if token is not None:
            reset_active_run_history(token)

        print(f"\nagent> {response}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
