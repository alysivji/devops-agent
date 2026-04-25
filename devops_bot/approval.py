from __future__ import annotations

from typing import TypedDict

type JSONPrimitive = None | bool | int | float | str
type JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


class ApprovalRequest(TypedDict):
    kind: str
    prompt: str
    context: dict[str, JSONValue]


class WaitingForApproval(Exception):
    def __init__(self, request: ApprovalRequest) -> None:
        super().__init__(request["prompt"])
        self.request = request


def _default_handler(prompt: str) -> bool:
    return input(prompt).strip().lower() in {"y", "yes"}


def request_approval(
    *,
    prompt: str,
    kind: str = "confirmation",
    context: dict[str, JSONValue] | None = None,
) -> bool:
    from .workflow import emit_event, get_workflow_runtime

    request: ApprovalRequest = {
        "kind": kind,
        "prompt": prompt,
        "context": context or {},
    }
    runtime = get_workflow_runtime()
    if runtime is None:
        return _default_handler(prompt)

    emit_event(
        {
            "kind": "approval_requested",
            "prompt": prompt,
            "request_kind": kind,
            "context": request["context"],
        }
    )
    approved = runtime.resolve_approval(request)
    emit_event(
        {
            "kind": "approval_resolved",
            "prompt": prompt,
            "request_kind": kind,
            "approved": approved,
            "context": request["context"],
        }
    )
    return approved


def get_approval(prompt: str) -> bool:
    return request_approval(prompt=prompt)
