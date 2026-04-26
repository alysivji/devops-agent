from typing import Any, cast

from strands.models.openai import OpenAIModel
from strands.session.session_manager import SessionManager

from devops_bot import factory as factory_module
from devops_bot.factory import build_agent, build_model


def test_build_model_omits_none_params() -> None:
    model = build_model(model_id="gpt-5.4")

    assert model.get_config() == {"model_id": "gpt-5.4"}


def test_build_model_preserves_explicit_params() -> None:
    model = build_model(model_id="gpt-5.4", params={"temperature": 0.2})

    assert model.get_config() == {"model_id": "gpt-5.4", "params": {"temperature": 0.2}}


def test_build_agent_passes_session_manager(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    model = cast(OpenAIModel, object())
    session_manager = cast(SessionManager, object())
    monkeypatch.setattr(factory_module, "Agent", FakeAgent)

    agent = build_agent(
        model=model,
        system_prompt="system",
        tools=["tool"],
        session_manager=session_manager,
    )

    assert isinstance(agent, FakeAgent)
    assert captured == {
        "model": model,
        "system_prompt": "system",
        "tools": ["tool"],
        "plugins": [],
        "session_manager": session_manager,
        "trace_attributes": None,
    }


def test_build_agent_passes_plugins(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    model = cast(OpenAIModel, object())
    plugin = object()
    monkeypatch.setattr(factory_module, "Agent", FakeAgent)

    agent = build_agent(
        model=model,
        system_prompt="system",
        tools=["tool"],
        plugins=[cast(Any, plugin)],
    )

    assert isinstance(agent, FakeAgent)
    assert captured == {
        "model": model,
        "system_prompt": "system",
        "tools": ["tool"],
        "plugins": [plugin],
        "session_manager": None,
        "trace_attributes": None,
    }


def test_build_agent_passes_trace_attributes(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    model = cast(OpenAIModel, object())
    monkeypatch.setattr(factory_module, "Agent", FakeAgent)

    agent = build_agent(
        model=model,
        system_prompt="system",
        trace_attributes={"session.id": "session-1"},
    )

    assert isinstance(agent, FakeAgent)
    assert captured["trace_attributes"] == {"session.id": "session-1"}
