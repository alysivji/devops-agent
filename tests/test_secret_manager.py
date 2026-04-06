from pathlib import Path

import pytest

from agent.secret_manager import SecretNotFound, SecretsManager


def write_env_file(tmp_path: Path, contents: str) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text(contents)
    return env_path


def test_loads_values_from_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)

    env_path = write_env_file(
        tmp_path,
        "\n".join(
            [
                "DEBUG=true",
                "ALLOWED_HOSTS=localhost,127.0.0.1",
                "",
            ]
        ),
    )

    secrets_manager = SecretsManager(path=env_path)

    assert secrets_manager.get(bool, "DEBUG") is True
    assert secrets_manager.get(list, "ALLOWED_HOSTS") == ["localhost", "127.0.0.1"]


def test_os_env_overrides_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_path = write_env_file(tmp_path, "DEBUG=false\n")
    monkeypatch.setenv("DEBUG", "true")

    secrets_manager = SecretsManager(path=env_path)

    assert secrets_manager.get(bool, "DEBUG") is True


def test_default_value_is_returned_when_missing(tmp_path: Path) -> None:
    env_path = write_env_file(tmp_path, "")
    secrets_manager = SecretsManager(path=env_path)

    assert secrets_manager.get(list, "ALLOWED_HOSTS", ["localhost"]) == ["localhost"]


def test_none_default_is_returned_when_missing(tmp_path: Path) -> None:
    env_path = write_env_file(tmp_path, "")
    secrets_manager = SecretsManager(path=env_path)

    assert secrets_manager.get(str, "SECRET_KEY", None) is None


def test_missing_required_value_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)

    env_path = write_env_file(tmp_path, "")
    secrets_manager = SecretsManager(path=env_path)

    with pytest.raises(SecretNotFound):
        secrets_manager.get(str, "SECRET_KEY")
