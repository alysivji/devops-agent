from collections.abc import Sequence
from typing import Any

import yaml
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
    tools: Sequence[Any],
) -> Agent:
    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=list(tools),
    )


def validate_generated_playbook_yaml(playbook_yaml: str) -> None:
    stripped = playbook_yaml.lstrip()
    if stripped.startswith("#"):
        raise ValueError("generated playbook YAML must not include the metadata header")

    parsed = yaml.safe_load(playbook_yaml)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("generated playbook YAML must be a non-empty YAML list")

    for play in parsed:
        if not isinstance(play, dict):
            raise ValueError("generated playbook YAML must contain mapping plays")
        if "hosts" not in play:
            raise ValueError("generated playbook YAML must declare hosts for each play")
