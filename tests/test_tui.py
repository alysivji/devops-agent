import asyncio
from typing import cast

from textual.binding import Binding
from textual.widgets import TextArea

from devops_bot.tui import DevopsAgentApp
from devops_bot.workflow import AgentWorkflow


class DummyWorkflow:
    def __init__(self) -> None:
        self.runs: list[str] = []
        self.reset_calls = 0

    def run(self, text: str, event_sink, approval_resolver) -> None:  # noqa: ANN001
        del event_sink, approval_resolver
        self.runs.append(text)

    def reset(self) -> None:
        self.reset_calls += 1


def prompt_height(prompt: TextArea) -> float:
    assert prompt.styles.height is not None
    return prompt.styles.height.value


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


def test_tui_prompt_exposes_visible_copy_and_paste_bindings() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            copy_binding = app.screen.active_bindings["ctrl+c"][1]
            paste_binding = app.screen.active_bindings["ctrl+v"][1]

            assert copy_binding.action == "copy"
            assert copy_binding.show is True
            assert app.get_key_display(copy_binding) == "^c"

            assert paste_binding.action == "paste"
            assert paste_binding.show is True
            assert app.get_key_display(paste_binding) == "^v"

    asyncio.run(run_test())


def test_tui_chat_log_keeps_copy_and_paste_bindings_visible_when_focused() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            chat_log = app.query_one("#chat-log", TextArea)
            chat_log.focus()
            await pilot.pause()

            copy_binding = app.screen.active_bindings["ctrl+c"][1]
            paste_binding = app.screen.active_bindings["ctrl+v"][1]

            assert copy_binding.action == "copy"
            assert copy_binding.show is True
            assert app.get_key_display(copy_binding) == "^c"

            assert paste_binding.action == "paste"
            assert paste_binding.show is True
            assert app.get_key_display(paste_binding) == "^v"

    asyncio.run(run_test())


def test_tui_paste_from_chat_log_redirects_to_prompt() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            del pilot
            chat_log = app.query_one("#chat-log", TextArea)
            prompt = app.query_one("#prompt-input", TextArea)
            pasted: list[str] = []

            def fake_paste() -> None:
                pasted.append("called")

            prompt.action_paste = fake_paste  # type: ignore[method-assign]
            chat_log.focus()

            chat_log.action_paste()

            assert app.screen.focused is prompt
            assert pasted == ["called"]

    asyncio.run(run_test())


def test_tui_typing_from_chat_log_redirects_to_prompt() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            chat_log = app.query_one("#chat-log", TextArea)
            prompt = app.query_one("#prompt-input", TextArea)

            chat_log.focus()
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()

            assert app.screen.focused is prompt
            assert prompt.text == "a"

    asyncio.run(run_test())


def test_tui_chat_log_is_read_only_text_area() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            del pilot
            chat_log = app.query_one("#chat-log", TextArea)

            assert chat_log.read_only is True
            assert chat_log.show_cursor is False

    asyncio.run(run_test())


def test_tui_prompt_is_multiline_and_resizes_with_content() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            del pilot
            prompt = app.query_one("#prompt-input", TextArea)

            assert prompt.soft_wrap is True
            assert prompt_height(prompt) == 3

            prompt.load_text("one\ntwo\nthree")
            app._resize_prompt()

            assert prompt_height(prompt) == 5

            prompt.load_text("one\ntwo\nthree\nfour\nfive\nsix")
            app._resize_prompt()

            assert prompt_height(prompt) == 7

    asyncio.run(run_test())


def test_tui_submits_multiline_prompt_with_enter() -> None:
    async def run_test() -> None:
        app = DevopsAgentApp()

        async with app.run_test() as pilot:
            workflow = DummyWorkflow()
            app._workflow = cast(AgentWorkflow, workflow)
            prompt = app.query_one("#prompt-input", TextArea)
            chat_log = app.query_one("#chat-log", TextArea)

            prompt.load_text("deploy\nnginx")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert workflow.runs == ["deploy\nnginx"]
            assert prompt.text == ""
            assert "you> deploy\nnginx" in chat_log.text

    asyncio.run(run_test())
