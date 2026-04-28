import importlib
import sys
from types import ModuleType


def test_langfuse_client_receives_dotenv_configuration(
    monkeypatch,
    tmp_path,
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-openai-key",
                "LANGFUSE_ENABLED=true",
                "LANGFUSE_PUBLIC_KEY=test-public-key",
                "LANGFUSE_SECRET_KEY=test-secret-key",
                "LANGFUSE_BASE_URL=https://langfuse.example.test",
                "",
            ]
        )
    )

    previous_config = sys.modules.pop("homelab_operator.config", None)
    previous_langfuse = sys.modules.get("langfuse")

    for name in (
        "OPENAI_API_KEY",
        "LANGFUSE_ENABLED",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    fake_langfuse = ModuleType("langfuse")
    captured: dict[str, str | None] = {}

    class FakeLangfuse:
        def __init__(
            self,
            *,
            public_key: str | None = None,
            secret_key: str | None = None,
            base_url: str | None = None,
        ) -> None:
            captured.update(
                {
                    "public_key": public_key,
                    "secret_key": secret_key,
                    "base_url": base_url,
                }
            )

    fake_langfuse.Langfuse = FakeLangfuse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.chdir(tmp_path)

    try:
        config = importlib.import_module("homelab_operator.config")
        assert config.LANGFUSE_ENABLED is True
        assert isinstance(config.langfuse, FakeLangfuse)
        assert captured == {
            "public_key": "test-public-key",
            "secret_key": "test-secret-key",
            "base_url": "https://langfuse.example.test",
        }
    finally:
        sys.modules.pop("homelab_operator.config", None)
        if previous_config is not None:
            sys.modules["homelab_operator.config"] = previous_config
        if previous_langfuse is not None:
            sys.modules["langfuse"] = previous_langfuse
