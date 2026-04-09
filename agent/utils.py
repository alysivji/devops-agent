from collections.abc import Sequence
from typing import Any, Optional

from strands import Agent
from strands.models.openai import OpenAIModel

from .config import OPENAI_API_KEY


def build_model(*, model_id: str | None = None) -> OpenAIModel:
    return OpenAIModel(
        client_args={
            "api_key": OPENAI_API_KEY,
        },
        model_id=model_id or "gpt-5.4",
    )


def build_agent(
    model: OpenAIModel,
    *,
    system_prompt: str,
    tools: Optional[Sequence[Any]] = None,
) -> Agent:
    if tools is None:
        tools = []

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=list(tools),
    )
