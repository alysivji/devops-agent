import asyncio

from textual.binding import Binding
from textual.widgets import TextArea

from devops_bot.tui import DevopsAgentApp


def test_tui_keeps_prompt_focus_on_tab() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt-input")

            assert app.screen.focused is prompt

            await pilot.press("tab")

            assert app.screen.focused is prompt

    asyncio.run(run_test())


def test_tui_uses_ctrl_q_and_cmd_q_for_quit() -> None:
    bindings: dict[str, str] = {}
    for binding in DevopsAgentApp.BINDINGS:
        if isinstance(binding, Binding):
            bindings[binding.key] = binding.action
        else:
            bindings[binding[0]] = binding[1]

    assert bindings["ctrl+q"] == "quit"
    assert bindings["super+q"] == "quit"


def test_tui_chat_log_is_read_only_text_area() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            del pilot
            chat_log = app.query_one("#chat-log", TextArea)

            assert chat_log.read_only is True
            assert chat_log.show_cursor is False

    asyncio.run(run_test())
