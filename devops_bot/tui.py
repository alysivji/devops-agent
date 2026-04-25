from __future__ import annotations

import threading

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog

from .runner import AgentRunner
from .ui import UIProtocol


class TextualUI(UIProtocol):
    def __init__(self, app: "DevopsAgentApp") -> None:
        self._app = app

    def post_message(self, role: str, text: str) -> None:
        self._app.call_from_thread(self._app.write_message, role, text)

    def set_status(self, text: str) -> None:
        self._app.call_from_thread(self._app.set_status_text, text)

    def clear_status(self) -> None:
        self._app.call_from_thread(self._app.set_status_text, "")

    def get_approval(self, prompt: str) -> bool:
        result: list[bool] = []
        done = threading.Event()

        def handle_result(approved: bool | None) -> None:
            result.append(bool(approved))
            done.set()

        def show_prompt() -> None:
            self._app.push_screen(YesNoScreen(prompt), callback=handle_result)

        self._app.call_from_thread(show_prompt)
        done.wait()
        return result[0]


class YesNoScreen(ModalScreen[bool]):
    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        yield Label(self._prompt, id="approval-prompt")
        with Horizontal(id="approval-actions"):
            yield Button("Yes", id="yes", variant="success")
            yield Button("No", id="no", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class DevopsAgentApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    RichLog {
        height: 1fr;
        border: solid $primary;
    }

    #status {
        height: 1;
        color: $warning;
        padding: 0 1;
    }

    #approval-prompt {
        padding: 1 2;
    }

    #approval-actions {
        align: center middle;
        height: auto;
        padding: 0 2 1 2;
    }

    #approval-actions Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="chat-log", wrap=True)
        yield Label("", id="status")
        yield Input(placeholder="Ask the devops agent...", id="prompt-input")
        yield Footer()

    def on_mount(self) -> None:
        self._chat_log = self.query_one("#chat-log", RichLog)
        self._status = self.query_one("#status", Label)
        self._prompt = self.query_one("#prompt-input", Input)
        self._ui = TextualUI(self)
        self._runner = AgentRunner(self._ui)
        self._prompt.focus()

    def write_message(self, role: str, text: str) -> None:
        self._chat_log.write(f"{role}> {text}")

    def set_status_text(self, text: str) -> None:
        self._status.update(text)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text in {"/exit", "/quit"}:
            self.exit()
            return
        if text == "/reset":
            self._runner.reset()
            self.write_message("system", "new session started")
            return

        self.write_message("you", text)
        self.run_worker(lambda: self._runner.run(text), thread=True)


def main() -> int:
    DevopsAgentApp().run()
    return 0
