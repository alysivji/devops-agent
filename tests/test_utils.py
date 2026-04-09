from agent.utils import build_model


def test_build_model_omits_none_params() -> None:
    model = build_model()

    assert model.get_config() == {"model_id": "gpt-5.4"}


def test_build_model_preserves_explicit_params() -> None:
    model = build_model(params={"temperature": 0.2})

    assert model.get_config() == {"model_id": "gpt-5.4", "params": {"temperature": 0.2}}
