import argparse
import sys
from uuid import uuid4

from .agents.orchestrator import OrchestratorAgent
from .approval import ApprovalRequest
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
from .workflow import (
    WorkflowEvent,
    WorkflowRuntime,
    emit_notice,
    reset_workflow_runtime,
    set_workflow_runtime,
)


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
    runtime_token = set_workflow_runtime(
        WorkflowRuntime(
            event_sink=_render_workflow_event,
            approval_resolver=_resolve_cli_approval,
        )
    )

    try:
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
    finally:
        if token is not None:
            reset_active_run_history(token)
        reset_workflow_runtime(runtime_token)

    print(response)
    return 0


def _append_run_history(run_history: RunHistory) -> None:
    try:
        append_session_jsonl(run_history.session, RUN_HISTORY_PATH)
    except OSError as exc:
        emit_notice(f"Failed to write run history: {exc}", level="warning")


def _resolve_cli_approval(request: ApprovalRequest) -> bool:
    return input(request["prompt"]).strip().lower() in {"y", "yes"}


def _render_workflow_event(event: WorkflowEvent) -> None:
    if event["kind"] == "preview":
        print()
        print(event["title"])
        print(event["body"])
        print()
        return

    if event["kind"] != "notice":
        return

    stream = sys.stderr if event.get("level") in {"warning", "error"} else sys.stdout
    print(event["text"], file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
