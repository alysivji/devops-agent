import readline  # noqa: F401 — enables line editing and up-arrow history as a side effect
import sys

from .runner import AgentRunner
from .ui import UIProtocol

BANNER = """\
devops-agent chat
  /reset  start a new session (clears conversation history)
  /exit   quit  (also Ctrl-D)
"""


class CliUI(UIProtocol):
    def post_message(self, role: str, text: str) -> None:
        stream = sys.stderr if role == "error" else sys.stdout
        print(f"\n{role}> {text}\n", file=stream)

    def set_status(self, text: str) -> None:
        print(f"[{text}]", end="\r", flush=True)

    def clear_status(self) -> None:
        print(" " * 60, end="\r", flush=True)

    def get_approval(self, prompt: str) -> bool:
        return input(prompt).strip().lower() in {"y", "yes"}


def main() -> int:
    print(BANNER)
    ui = CliUI()
    runner = AgentRunner(ui)

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
            runner.reset()
            print("[new session started]\n")
            continue

        ui.post_message("you", user_input)
        runner.run(user_input)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
