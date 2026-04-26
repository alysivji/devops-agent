import json
import os
from collections.abc import Mapping
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from .config import RUN_HISTORY_ENABLED, secret_manager

MAX_TEXT_LENGTH = 500
RUN_HISTORY_ENV_VAR = "DEVOPS_AGENT_RUN_HISTORY_ENABLED"
RUN_HISTORY_PATH = Path("docs/autonomous-devops-run-history.jsonl")

type JSONPrimitive = None | bool | int | float | str
type JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]

_SENSITIVE_FIELD_MARKERS = ("secret", "token", "password", "key", "private_key")
_active_run_history: ContextVar["RunHistory | None"] = ContextVar(
    "active_run_history", default=None
)


class RunEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: str
    status: str
    what: str
    why: str | None = None
    details: dict[str, JSONValue] = Field(default_factory=dict)


class RunSession(BaseModel):
    session_id: str
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    prompt: str
    outcome: str | None = None
    events: list[RunEvent] = Field(default_factory=list)


def run_history_enabled() -> bool:
    return bool(secret_manager.get(bool, RUN_HISTORY_ENV_VAR, RUN_HISTORY_ENABLED))


class RunHistory:
    def __init__(self, *, prompt: str, session_id: str | None = None) -> None:
        self.session = RunSession(
            session_id=session_id or uuid4().hex,
            run_id=uuid4().hex,
            started_at=datetime.now(UTC),
            prompt=prompt,
        )

    def record_event(
        self,
        *,
        kind: str,
        status: str,
        what: str,
        why: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> RunEvent:
        event = RunEvent(
            kind=_truncate_required_text(kind),
            status=_truncate_required_text(status),
            what=_truncate_required_text(what),
            why=_truncate_text(why),
            details=_sanitize_details(details or {}),
        )
        self.session.events.append(event)
        return event

    def finalize(self, outcome: str) -> None:
        self.session.finished_at = datetime.now(UTC)
        self.session.outcome = _truncate_text(outcome)


def set_active_run_history(run_history: RunHistory | None) -> Token[RunHistory | None]:
    return _active_run_history.set(run_history)


def reset_active_run_history(token: Token[RunHistory | None]) -> None:
    _active_run_history.reset(token)


def get_active_run_history() -> RunHistory | None:
    return _active_run_history.get()


def record_event(
    *,
    kind: str,
    status: str,
    what: str,
    why: str | None = None,
    details: Mapping[str, object] | None = None,
) -> None:
    run_history = get_active_run_history()
    if run_history is None:
        return
    run_history.record_event(
        kind=kind,
        status=status,
        what=what,
        why=why,
        details=details,
    )


def append_session_jsonl(session: RunSession, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = _load_jsonl_records(path)
    updated = False

    for index, record in enumerate(records):
        if record.get("session_id") == session.session_id:
            records[index] = _append_turn(record, session)
            updated = True
            break

    if not updated:
        records.append(_build_session_record(session))

    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write(os.linesep)


def _load_jsonl_records(path: Path) -> list[dict[str, JSONValue]]:
    if not path.exists():
        return []

    records: list[dict[str, JSONValue]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _append_turn(record: dict[str, JSONValue], session: RunSession) -> dict[str, JSONValue]:
    session_payload = _session_payload(session)
    turns_value = record.get("turns")
    finished_at = session_payload["finished_at"]

    if isinstance(turns_value, list):
        next_turns = list(turns_value)
        next_turns.append(session_payload)
        return {
            "session_id": session.session_id,
            "started_at": record.get("started_at", session_payload["started_at"]),
            "finished_at": finished_at,
            "updated_at": finished_at,
            "turn_count": len(next_turns),
            "turns": next_turns,
        }

    existing_turn = _legacy_record_to_turn(record)
    return {
        "session_id": session.session_id,
        "started_at": existing_turn["started_at"],
        "finished_at": finished_at,
        "updated_at": finished_at,
        "turn_count": 2,
        "turns": [existing_turn, session_payload],
    }


def _build_session_record(session: RunSession) -> dict[str, JSONValue]:
    session_payload = _session_payload(session)
    return {
        "session_id": session.session_id,
        "started_at": session_payload["started_at"],
        "finished_at": session_payload["finished_at"],
        "updated_at": session_payload["finished_at"],
        "turn_count": 1,
        "turns": [session_payload],
    }


def _session_payload(session: RunSession) -> dict[str, JSONValue]:
    return session.model_dump(mode="json")


def _legacy_record_to_turn(record: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {
        "session_id": str(record.get("session_id") or record.get("run_id") or ""),
        "run_id": str(record.get("run_id") or ""),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
        "prompt": str(record.get("prompt") or ""),
        "outcome": record.get("outcome"),
        "events": record.get("events") if isinstance(record.get("events"), list) else [],
    }


def _sanitize_details(details: Mapping[str, object]) -> dict[str, JSONValue]:
    sanitized: dict[str, JSONValue] = {}
    for key, value in details.items():
        if _is_sensitive_key(key):
            sanitized[key] = "[REDACTED]"
            continue
        sanitized[key] = _sanitize_json(value)
    return sanitized


def _sanitize_json(value: object) -> JSONValue:
    if isinstance(value, dict):
        return _sanitize_details({str(key): item for key, item in value.items()})

    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]

    if isinstance(value, str):
        return _truncate_text(value)

    if value is None or isinstance(value, bool | int | float):
        return value

    return _truncate_text(str(value)) or ""


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(marker in normalized for marker in _SENSITIVE_FIELD_MARKERS)


def _truncate_text(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= MAX_TEXT_LENGTH:
        return value
    return f"{value[: MAX_TEXT_LENGTH - 3]}..."


def _truncate_required_text(value: str) -> str:
    truncated = _truncate_text(value)
    assert truncated is not None
    return truncated
