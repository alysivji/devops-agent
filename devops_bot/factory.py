from collections.abc import Sequence
from typing import Any, Optional

from strands import Agent, Plugin
from strands.models.openai import OpenAIModel
from strands.session.session_manager import SessionManager

from .config import OPENAI_API_KEY


def build_model(
    *, model_id: str | None = None, params: dict[str, Any] | None = None
) -> OpenAIModel:
    model_config: dict[str, Any] = {
        "model_id": model_id,
    }
    if params is not None:
        model_config["params"] = params

    return OpenAIModel(
        client_args={
            "api_key": OPENAI_API_KEY,
        },
        **model_config,
    )


def build_agent(
    model: OpenAIModel,
    *,
    system_prompt: str,
    tools: Optional[Sequence[Any]] = None,
    plugins: Optional[Sequence[Plugin]] = None,
    session_manager: SessionManager | None = None,
) -> Agent:
    if tools is None:
        tools = []
    if plugins is None:
        plugins = []

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=list(tools),
        plugins=list(plugins),
        session_manager=session_manager,
    )
