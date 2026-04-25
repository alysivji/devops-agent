import os
import readline  # noqa: F401 — enables line editing and up-arrow history as a side effect
import sys

from .runner import AgentRunner
from .ui import UIProtocol

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


class CliUI(UIProtocol):
    def post_message(self, role: str, text: str) -> None:
        stream = sys.stderr if role == "error" else sys.stdout
        color = {"you": CYAN, "agent": GREEN, "error": RED}.get(role, "")
        label = _colorize(role, color, stream=stream) if color else role
        print(file=stream)
        print(f"{label}", file=stream)
        print(_format_lines(text), file=stream)
        print(file=stream)

    def set_status(self, text: str) -> None:
        print(_colorize(f"[{text}]", DIM, stream=sys.stdout), file=sys.stdout, flush=True)

    def clear_status(self) -> None:
        return None

    def get_approval(self, prompt: str) -> bool:
        return input(prompt).strip().lower() in {"y", "yes"}


def main() -> int:
    readline.set_completer(_complete_command)
    readline.parse_and_bind("tab: complete")
    print(BANNER)
    ui = CliUI()
    runner = AgentRunner(ui)
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
            runner.reset()
            print("[new session started]\n")
            continue

        ui.post_message("you", user_input)
        runner.run(user_input)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
