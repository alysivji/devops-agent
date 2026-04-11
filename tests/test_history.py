import json
from pathlib import Path

from devops_bot.history import RunHistory, append_session_jsonl, run_history_enabled


def test_run_history_enabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        "devops_bot.history.secret_manager.get",
        lambda secret_type, name, default: default,
    )

    assert run_history_enabled() is True


def test_run_history_can_be_disabled_with_env_var(monkeypatch) -> None:
    monkeypatch.setenv("DEVOPS_AGENT_RUN_HISTORY_ENABLED", "false")

    assert run_history_enabled() is False


def test_run_history_redacts_sensitive_fields_and_truncates_text() -> None:
    run_history = RunHistory(prompt="deploy the cluster")
    run_history.record_event(
        kind="tool_call",
        status="completed",
        what="x" * 600,
        why="y" * 600,
        details={
            "token": "abc123",
            "nested": {"private_key": "hidden", "note": "z" * 600},
            "items": [{"password": "secret"}],
        },
    )

    event = run_history.session.events[0]

    assert event.what.endswith("...")
    assert event.why is not None and event.why.endswith("...")
    assert event.details["token"] == "[REDACTED]"
    assert event.details["nested"] == {"private_key": "[REDACTED]", "note": ("z" * 497) + "..."}
    assert event.details["items"] == [{"password": "[REDACTED]"}]


def test_append_session_jsonl_persists_prompt_and_outcome(tmp_path: Path) -> None:
    output_path = tmp_path / "docs" / "autonomous-devops-run-history.jsonl"
    run_history = RunHistory(prompt="inspect the registry")
    run_history.record_event(
        kind="run_started",
        status="started",
        what="Started.",
        why="Capture the prompt.",
        details={"prompt": "inspect the registry"},
    )
    run_history.finalize("used existing playbook")

    append_session_jsonl(run_history.session, output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["prompt"] == "inspect the registry"
    assert payload["outcome"] == "used existing playbook"
    assert payload["events"][0]["kind"] == "run_started"
