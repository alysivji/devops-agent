from __future__ import annotations

import threading
from typing import Protocol, cast

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, OptionList, TextArea
from textual.widgets.option_list import Option

from .approval import ApprovalRequest
from .workflow import AgentWorkflow, InteractiveAdapter, WorkflowEvent

COMMANDS = {
    "/exit": "Quit the app.",
    "/quit": "Quit the app.",
    "/reset": "Start a new session.",
}

PROMPT_MIN_LINES = 1
PROMPT_MAX_LINES = 5
PROMPT_CHROME_HEIGHT = 2


class PromptSubmittingApp(Protocol):
    def _submit_prompt(self) -> None: ...

    def _paste_into_prompt(self) -> None: ...

    def _insert_into_prompt(self, text: str) -> None: ...


class PromptInput(TextArea):
    BINDINGS = [
        Binding("ctrl+c", "copy", "Copy", key_display="^c"),
        Binding("super+c", "copy", "Copy", show=False),
        Binding("ctrl+v", "paste", "Paste", key_display="^v"),
        Binding("super+v", "paste", "Paste", show=False),
    ]

    def on_key(self, event: events.Key) -> None:
        if event.key != "enter":
            return

        event.stop()
        event.prevent_default()
        cast(PromptSubmittingApp, self.app)._submit_prompt()


class ChatLog(TextArea):
    BINDINGS = [
        Binding("ctrl+c", "copy", "Copy", key_display="^c"),
        Binding("super+c", "copy", "Copy", show=False),
        Binding("ctrl+v", "paste", "Paste", key_display="^v"),
        Binding("super+v", "paste", "Paste", show=False),
    ]

    def action_paste(self) -> None:
        cast(PromptSubmittingApp, self.app)._paste_into_prompt()

    def on_key(self, event: events.Key) -> None:
        if event.character is None or not event.character.isprintable():
            return

        event.stop()
        event.prevent_default()
        cast(PromptSubmittingApp, self.app)._insert_into_prompt(event.character)


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

    TextArea {
        height: 1fr;
        border: solid $primary;
    }

    #prompt-input {
        height: 3;
        min-height: 3;
        max-height: 7;
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

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("super+q", "quit", "Quit", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ChatLog(
            "",
            id="chat-log",
            read_only=True,
            show_cursor=False,
            soft_wrap=True,
            highlight_cursor_line=False,
        )
        yield Label("", id="status")
        yield OptionList(id="command-menu")
        yield PromptInput(
            "",
            id="prompt-input",
            soft_wrap=True,
            compact=True,
            placeholder="Ask the devops agent...",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._chat_log = self.query_one("#chat-log", ChatLog)
        self._status = self.query_one("#status", Label)
        self._command_menu = self.query_one("#command-menu", OptionList)
        self._prompt = self.query_one("#prompt-input", PromptInput)
        self._workflow = AgentWorkflow()
        self._adapter: InteractiveAdapter = TextualAdapter(self)
        self._busy = False
        self._chat_history: list[str] = []
        self._prompt.focus()
        self._resize_prompt()
        self._hide_command_menu()

    def write_message(self, role: str, text: str) -> None:
        self._chat_history.append(f"{role}> {text}")
        self._chat_log.load_text("\n".join(self._chat_history))
        self._chat_log.scroll_end(animate=False, immediate=True)

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

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area is not self._prompt:
            return
        self._update_command_menu(self._prompt.text)
        self.call_after_refresh(self._resize_prompt)

    def on_key(self, event: events.Key) -> None:
        if self.screen.focused is self._prompt and event.key in {"tab", "shift+tab"}:
            event.stop()
            event.prevent_default()
            return

        if self.screen.focused is not self._prompt:
            return

        if event.key == "enter" and self._command_menu.display:
            self._apply_highlighted_command()
            event.stop()
            event.prevent_default()
            return

        if event.key == "enter":
            self._submit_prompt()
            event.stop()
            event.prevent_default()
            return

        if not self._command_menu.display:
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

    def _submit_prompt(self) -> None:
        text = self._prompt.text.strip()
        self._prompt.load_text("")
        self._resize_prompt()
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

        with self.prevent(TextArea.Changed):
            self._prompt.load_text(option.id)
        self._resize_prompt()
        self._hide_command_menu()
        self._prompt.focus()

    def _resize_prompt(self) -> None:
        content_height = max(1, self._prompt.virtual_size.height)
        visible_lines = min(PROMPT_MAX_LINES, max(PROMPT_MIN_LINES, content_height))
        prompt_height = visible_lines + PROMPT_CHROME_HEIGHT
        self._prompt.styles.height = prompt_height

    def _paste_into_prompt(self) -> None:
        self._prompt.focus()
        self._prompt.action_paste()

    def _insert_into_prompt(self, text: str) -> None:
        self._prompt.focus()
        self._prompt.insert(text)
        self._resize_prompt()


def main() -> int:
    DevopsAgentApp().run()
    return 0
