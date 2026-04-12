import pytest

from devops_bot import session as session_module
from devops_bot.session import ConfiguredBotoSession, build_session_manager


class FakeS3SessionManager:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls.append(kwargs)


def _patch_session_env(
    monkeypatch: pytest.MonkeyPatch,
    values: dict[str, str | None],
) -> None:
    def fake_get(secret_type: type[str], name: str, default: str | None) -> str | None:
        _ = secret_type
        return values.get(name, default)

    monkeypatch.setattr(session_module.secret_manager, "get", fake_get)


def test_build_session_manager_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_env(monkeypatch, {"DEVOPS_AGENT_SESSION_BACKEND": "none"})

    assert build_session_manager("run-123") is None


def test_build_session_manager_requires_s3_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_env(
        monkeypatch,
        {
            "DEVOPS_AGENT_SESSION_BACKEND": "s3",
            "DEVOPS_AGENT_SESSION_S3_BUCKET": None,
        },
    )

    with pytest.raises(ValueError, match="DEVOPS_AGENT_SESSION_S3_BUCKET is required"):
        build_session_manager("run-123")


def test_build_session_manager_configures_s3_compatible_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeS3SessionManager.calls = []
    monkeypatch.setattr(session_module, "S3SessionManager", FakeS3SessionManager)
    _patch_session_env(
        monkeypatch,
        {
            "DEVOPS_AGENT_SESSION_BACKEND": "s3",
            "DEVOPS_AGENT_SESSION_S3_BUCKET": "devops-agent-sessions",
            "DEVOPS_AGENT_SESSION_S3_PREFIX": "local/",
            "DEVOPS_AGENT_SESSION_S3_REGION": "us-east-1",
            "DEVOPS_AGENT_SESSION_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DEVOPS_AGENT_SESSION_S3_ADDRESSING_STYLE": "path",
            "DEVOPS_AGENT_SESSION_S3_ACCESS_KEY_ID": "minioadmin",
            "DEVOPS_AGENT_SESSION_S3_SECRET_ACCESS_KEY": "minioadmin",
        },
    )

    manager = build_session_manager("run-123")

    assert isinstance(manager, FakeS3SessionManager)
    call = FakeS3SessionManager.calls[0]
    assert call["session_id"] == "run-123"
    assert call["bucket"] == "devops-agent-sessions"
    assert call["prefix"] == "local/"
    assert call["region_name"] == "us-east-1"
    assert isinstance(call["boto_session"], ConfiguredBotoSession)
    assert call["boto_session"]._endpoint_url == "http://127.0.0.1:9000"
    assert call["boto_session"].get_credentials().access_key == "minioadmin"
    assert call["boto_client_config"].signature_version == "s3v4"
    assert call["boto_client_config"].s3 == {"addressing_style": "path"}


def test_session_storage_event_details_redacts_endpoint_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_env(
        monkeypatch,
        {
            "DEVOPS_AGENT_SESSION_BACKEND": "s3",
            "DEVOPS_AGENT_SESSION_S3_BUCKET": "devops-agent-sessions",
            "DEVOPS_AGENT_SESSION_S3_PREFIX": "devops-agent/",
            "DEVOPS_AGENT_SESSION_S3_ENDPOINT_URL": "https://user:pass@example.com:9000",
        },
    )

    details = session_module.get_session_storage_event_details(session_id="run-123")

    assert details == {
        "backend": "s3",
        "bucket": "devops-agent-sessions",
        "prefix": "devops-agent/",
        "endpoint_url": "https://[REDACTED]@example.com:9000",
        "session_id": "run-123",
    }
