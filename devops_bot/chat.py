import os
import readline  # noqa: F401 - enables line editing and up-arrow history as a side effect
import sys

from .approval import ApprovalRequest
from .workflow import AgentWorkflow, InteractiveAdapter, WorkflowEvent

BANNER = """\
devops-agent chat
  /reset  start a new session (clears conversation history)
  /exit   quit  (also Ctrl-D)
"""
COMMANDS = {
    "/exit": "quit  (also Ctrl-D)",
    "/quit": "quit",
    "/reset": "start a new session (clears conversation history)",
}

RESET = "\033[0m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"


def _supports_color(stream: object) -> bool:
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    return "NO_COLOR" not in os.environ


def _format_lines(text: str) -> str:
    lines = text.splitlines() or [text]
    return "\n".join(f"  {line}" if line else "" for line in lines)


def _colorize(text: str, color: str, *, stream: object) -> str:
    if not _supports_color(stream):
        return text
    return f"{color}{text}{RESET}"


def _complete_command(text: str, state: int) -> str | None:
    buffer = readline.get_line_buffer()
    if not buffer.startswith("/"):
        return None

    matches = [command for command in COMMANDS if command.startswith(buffer)]
    if state >= len(matches):
        return None
    return matches[state]


def _print_command_help() -> None:
    print()
    print("Commands")
    for command, description in COMMANDS.items():
        print(f"  {command:<7} {description}")
    print()


class CliRenderer:
    def render_event(self, event: WorkflowEvent) -> None:
        kind = event["kind"]
        if kind == "status":
            text = event["text"]
            if text:
                print(_colorize(f"[{text}]", DIM, stream=sys.stdout), file=sys.stdout, flush=True)
            return

        if kind == "message":
            self._print_block(event["role"], event["text"])
            return

        if kind == "preview":
            preview_text = f"{event['title']}\n{event['body']}"
            self._print_block("system", preview_text)
            return

        if kind == "notice":
            role = "error" if event.get("level") == "error" else "system"
            self._print_block(role, event["text"])
            return

        if kind == "approval_resolved":
            decision = "approved" if event["approved"] else "declined"
            self._print_block("system", f"Approval {decision}.")

    def resolve_approval(self, request: ApprovalRequest) -> bool:
        return input(request["prompt"]).strip().lower() in {"y", "yes"}

    def _print_block(self, role: str, text: str) -> None:
        stream = sys.stderr if role == "error" else sys.stdout
        color = {"you": CYAN, "agent": GREEN, "error": RED}.get(role, "")
        label = _colorize(role, color, stream=stream) if color else role
        print(file=stream)
        print(label, file=stream)
        print(_format_lines(text), file=stream)
        print(file=stream)


def main() -> int:
    readline.set_completer(_complete_command)
    readline.parse_and_bind("tab: complete")
    print(BANNER)
    renderer: InteractiveAdapter = CliRenderer()
    workflow = AgentWorkflow()
    prompt = _colorize("you> ", CYAN, stream=sys.stdout)

    while True:
        try:
            user_input = input(prompt).strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue

        if not user_input:
            continue
        if user_input == "/":
            _print_command_help()
            continue
        if user_input in ("/exit", "/quit"):
            break
        if user_input == "/reset":
            workflow.reset()
            print("[new session started]\n")
            continue

        renderer.render_event({"kind": "message", "role": "user", "text": user_input})
        workflow.run(
            user_input,
            event_sink=renderer.render_event,
            approval_resolver=renderer.resolve_approval,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
