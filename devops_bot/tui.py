from __future__ import annotations

import threading

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, OptionList, RichLog
from textual.widgets.option_list import Option

from .approval import ApprovalRequest
from .workflow import AgentWorkflow, InteractiveAdapter, WorkflowEvent

COMMANDS = {
    "/exit": "Quit the app.",
    "/quit": "Quit the app.",
    "/reset": "Start a new session.",
}


class TextualAdapter:
    def __init__(self, app: "DevopsAgentApp") -> None:
        self._app = app

    def render_event(self, event: WorkflowEvent) -> None:
        self._app.call_from_thread(self._app.handle_workflow_event, event)

    def resolve_approval(self, request: ApprovalRequest) -> bool:
        result: list[bool] = []
        done = threading.Event()

        def handle_result(approved: bool | None) -> None:
            result.append(bool(approved))
            done.set()

        def show_prompt() -> None:
            self._app.push_screen(YesNoScreen(request["prompt"]), callback=handle_result)

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

    #command-menu {
        display: none;
        height: auto;
        max-height: 6;
        border: solid $accent;
        margin: 0 0 1 0;
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
        yield OptionList(id="command-menu")
        yield Input(placeholder="Ask the devops agent...", id="prompt-input")
        yield Footer()

    def on_mount(self) -> None:
        self._chat_log = self.query_one("#chat-log", RichLog)
        self._status = self.query_one("#status", Label)
        self._command_menu = self.query_one("#command-menu", OptionList)
        self._prompt = self.query_one("#prompt-input", Input)
        self._workflow = AgentWorkflow()
        self._adapter: InteractiveAdapter = TextualAdapter(self)
        self._busy = False
        self._prompt.focus()
        self._hide_command_menu()

    def write_message(self, role: str, text: str) -> None:
        self._chat_log.write(f"{role}> {text}")

    def set_status_text(self, text: str) -> None:
        self._status.update(text)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._prompt.disabled = busy
        if not busy:
            self._prompt.focus()

    def handle_workflow_event(self, event: WorkflowEvent) -> None:
        kind = event["kind"]
        if kind == "status":
            self.set_status_text(event["text"])
            return

        if kind == "message":
            self.write_message(event["role"], event["text"])
            return

        if kind == "preview":
            self.write_message("system", f"{event['title']}\n{event['body']}")
            return

        if kind == "notice":
            role = "error" if event.get("level") == "error" else "system"
            self.write_message(role, event["text"])
            return

        if kind == "approval_resolved":
            decision = "approved" if event["approved"] else "declined"
            self.write_message("system", f"Approval {decision}.")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is not self._prompt:
            return
        self._update_command_menu(event.value)

    def on_key(self, event: events.Key) -> None:
        if self.screen.focused is not self._prompt or not self._command_menu.display:
            return

        if event.key == "down":
            self._command_menu.action_cursor_down()
            event.stop()
            event.prevent_default()
            return
        if event.key == "up":
            self._command_menu.action_cursor_up()
            event.stop()
            event.prevent_default()
            return
        if event.key == "enter":
            self._apply_highlighted_command()
            event.stop()
            event.prevent_default()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text in {"/exit", "/quit"}:
            self.exit()
            return
        if text == "/reset":
            self._workflow.reset()
            self.write_message("system", "new session started")
            return
        if self._busy:
            self.write_message("system", "A run is already in progress.")
            return

        self.write_message("you", text)
        self.set_busy(True)
        self.run_worker(lambda: self._run_prompt(text), thread=True)

    def _run_prompt(self, text: str) -> None:
        try:
            self._workflow.run(
                text,
                event_sink=self._adapter.render_event,
                approval_resolver=self._adapter.resolve_approval,
            )
        finally:
            self.call_from_thread(self.set_busy, False)

    def _update_command_menu(self, value: str) -> None:
        if not value.startswith("/"):
            self._hide_command_menu()
            return

        matches = [command for command in COMMANDS if command.startswith(value)] or list(COMMANDS)
        options = [Option(f"{command}  {COMMANDS[command]}", id=command) for command in matches]
        self._command_menu.set_options(options)
        self._command_menu.highlighted = 0 if options else None
        self._command_menu.display = bool(options)

    def _hide_command_menu(self) -> None:
        self._command_menu.display = False
        self._command_menu.clear_options()

    def _apply_highlighted_command(self) -> None:
        option = self._command_menu.highlighted_option
        if option is None or option.id is None:
            return

        with self.prevent(Input.Changed):
            self._prompt.value = option.id
        self._hide_command_menu()
        self._prompt.focus()


def main() -> int:
    DevopsAgentApp().run()
    return 0
