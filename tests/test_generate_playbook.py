from typing import Any, cast

from agent.generate_playbook import GeneratePlaybookAgent
from agent.tools import get_ansible_inventory_groups, http_get, search_web


def test_generate_playbook_agent_registers_web_tools(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr("agent.generate_playbook.build_model", lambda **kwargs: "fake-model")

    def fake_build_agent(*, model: str, system_prompt: str, tools: list[Any]) -> str:
        captured["model"] = model
        captured["system_prompt"] = system_prompt
        captured["tools"] = tools
        return "fake-agent"

    monkeypatch.setattr("agent.generate_playbook.build_agent", fake_build_agent)

    agent = GeneratePlaybookAgent()

    assert agent.agent == "fake-agent"
    assert captured["model"] == "fake-model"
    assert captured["tools"] == [get_ansible_inventory_groups, search_web, http_get]


def test_generate_playbook_prompt_includes_research_guidance() -> None:
    prompt = cast(str, GeneratePlaybookAgent.__init__.__globals__["SYSTEM_PROMPT"])

    assert "search_web" in prompt
    assert "http_get" in prompt
    assert "Prefer official vendor or upstream documentation" in prompt
    assert "Never use HTTP for mutating actions." in prompt
