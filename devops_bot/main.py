import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Dev Ops Agent.")
    parser.add_argument("prompt", help="Natural-language prompt.")
    parser.add_argument("--session-id", help="Specify the Strands session ID for this run.")
    args = parser.parse_args()

    run_history = RunHistory(prompt=args.prompt) if run_history_enabled() else None
    token = set_active_run_history(run_history) if run_history is not None else None
    session_id = (
        args.session_id
        if args.session_id is not None
        else (run_history.session.run_id if run_history is not None else uuid4().hex)
    )

    if run_history is not None:
        record_event(
            kind="run_started",
            status="started",
            what="Started CLI invocation.",
            why="Capture the initial user request before orchestration begins.",
            details={"prompt": args.prompt},
        )
        session_details = get_session_storage_event_details(session_id=session_id)
        if session_details is not None:
            record_event(
                kind="session_storage_configured",
                status="configured",
                what="Configured Strands session storage.",
                why=("Persist agent messages and state separately from the JSONL run history."),
                details=session_details,
            )

    try:
        response = OrchestratorAgent(session_id=session_id).run(args.prompt)
    except Exception as exc:
        if run_history is not None:
            record_event(
                kind="run_failed",
                status="failed",
                what="CLI invocation failed.",
                why="The orchestrator raised an exception before completing the request.",
                details={"error": str(exc), "exception_type": exc.__class__.__name__},
            )
            run_history.finalize(f"failed: {exc}")
            _append_run_history(run_history)
        if token is not None:
            reset_active_run_history(token)
        raise

    if run_history is not None:
        record_event(
            kind="run_completed",
            status="completed",
            what="CLI invocation completed successfully.",
            why="Persist the final agent response for later review.",
            details={"response": response},
        )
        run_history.finalize(response)
        _append_run_history(run_history)
        if token is not None:
            reset_active_run_history(token)

    print(response)
    return 0


def _append_run_history(run_history: RunHistory) -> None:
    try:
        append_session_jsonl(run_history.session, RUN_HISTORY_PATH)
    except OSError as exc:
        print(f"Failed to write run history: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
