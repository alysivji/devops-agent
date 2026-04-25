from collections.abc import Callable

type ApprovalHandler = Callable[[str], bool]


def _default_handler(prompt: str) -> bool:
    return input(prompt).strip().lower() in {"y", "yes"}


_handler: ApprovalHandler = _default_handler


def get_approval(prompt: str) -> bool:
    return _handler(prompt)


def set_approval_handler(handler: ApprovalHandler) -> None:
    global _handler
    _handler = handler


def reset_approval_handler() -> None:
    global _handler
    _handler = _default_handler
