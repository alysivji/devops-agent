from typing import Any, TypedDict
from urllib.parse import urlsplit, urlunsplit

import boto3
from botocore.config import Config as BotocoreConfig
from strands.session.s3_session_manager import S3SessionManager
from strands.session.session_manager import SessionManager

from .config import (
    SESSION_BACKEND,
    SESSION_S3_ACCESS_KEY_ID,
    SESSION_S3_ADDRESSING_STYLE,
    SESSION_S3_BUCKET,
    SESSION_S3_ENDPOINT_URL,
    SESSION_S3_PREFIX,
    SESSION_S3_REGION,
    SESSION_S3_SECRET_ACCESS_KEY,
    SESSION_S3_SESSION_TOKEN,
    secret_manager,
)

SESSION_BACKEND_ENV_VAR = "DEVOPS_AGENT_SESSION_BACKEND"
SESSION_S3_BUCKET_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_BUCKET"
SESSION_S3_PREFIX_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_PREFIX"
SESSION_S3_REGION_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_REGION"
SESSION_S3_ENDPOINT_URL_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_ENDPOINT_URL"
SESSION_S3_ADDRESSING_STYLE_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_ADDRESSING_STYLE"
SESSION_S3_ACCESS_KEY_ID_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_ACCESS_KEY_ID"
SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_SECRET_ACCESS_KEY"
SESSION_S3_SESSION_TOKEN_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_SESSION_TOKEN"


class SessionStorageConfig(TypedDict):
    backend: str
    bucket: str | None
    prefix: str
    region: str | None
    endpoint_url: str | None
    addressing_style: str
    access_key_id: str | None
    secret_access_key: str | None
    session_token: str | None
    session_id: str


class ConfiguredBotoSession(boto3.Session):
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        region_name: str | None,
        aws_access_key_id: str | None,
        aws_secret_access_key: str | None,
        aws_session_token: str | None,
    ) -> None:
        super().__init__(
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
        )
        self._endpoint_url = endpoint_url

    def client(self, *args: Any, **kwargs: Any) -> Any:
        service_name = kwargs.get("service_name")
        if service_name is None and args:
            service_name = args[0]

        if service_name == "s3" and self._endpoint_url and "endpoint_url" not in kwargs:
            kwargs["endpoint_url"] = self._endpoint_url

        return super().client(*args, **kwargs)


def build_session_manager(session_id: str) -> SessionManager | None:
    config = get_session_storage_config(session_id=session_id)
    if config["backend"] == "none":
        return None

    if config["backend"] != "s3":
        raise ValueError(
            "Unsupported DEVOPS_AGENT_SESSION_BACKEND="
            f"{config['backend']!r}; expected 'none' or 's3'"
        )

    bucket = config["bucket"]
    if not bucket:
        raise ValueError(
            "DEVOPS_AGENT_SESSION_S3_BUCKET is required when DEVOPS_AGENT_SESSION_BACKEND=s3"
        )

    region_name = config["region"]
    boto_session = _build_boto_session(config=config)
    boto_client_config = BotocoreConfig(
        signature_version="s3v4",
        s3={"addressing_style": config["addressing_style"]},
    )

    return S3SessionManager(
        session_id=session_id,
        bucket=bucket,
        prefix=config["prefix"],
        boto_session=boto_session,
        boto_client_config=boto_client_config,
        region_name=region_name,
    )


def get_session_storage_config(*, session_id: str) -> SessionStorageConfig:
    backend = _get_config(str, SESSION_BACKEND_ENV_VAR, SESSION_BACKEND)
    return {
        "backend": (backend or "none").strip().lower(),
        "bucket": _get_config(str, SESSION_S3_BUCKET_ENV_VAR, SESSION_S3_BUCKET),
        "prefix": _get_config(str, SESSION_S3_PREFIX_ENV_VAR, SESSION_S3_PREFIX) or "",
        "region": _get_config(str, SESSION_S3_REGION_ENV_VAR, SESSION_S3_REGION),
        "endpoint_url": _get_config(str, SESSION_S3_ENDPOINT_URL_ENV_VAR, SESSION_S3_ENDPOINT_URL),
        "addressing_style": _get_config(
            str, SESSION_S3_ADDRESSING_STYLE_ENV_VAR, SESSION_S3_ADDRESSING_STYLE
        )
        or "path",
        "access_key_id": _get_config(
            str, SESSION_S3_ACCESS_KEY_ID_ENV_VAR, SESSION_S3_ACCESS_KEY_ID
        ),
        "secret_access_key": _get_config(
            str, SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR, SESSION_S3_SECRET_ACCESS_KEY
        ),
        "session_token": _get_config(
            str, SESSION_S3_SESSION_TOKEN_ENV_VAR, SESSION_S3_SESSION_TOKEN
        ),
        "session_id": session_id,
    }


def get_session_storage_event_details(*, session_id: str) -> dict[str, str | None] | None:
    config = get_session_storage_config(session_id=session_id)
    if config["backend"] == "none":
        return None

    return {
        "backend": config["backend"],
        "bucket": config["bucket"],
        "prefix": config["prefix"],
        "endpoint_url": _redact_url(config["endpoint_url"]),
        "session_id": config["session_id"],
    }


def _get_config(secret_type: type[str], name: str, default: str | None) -> str | None:
    return secret_manager.get(secret_type, name, default)


def _build_boto_session(*, config: SessionStorageConfig) -> ConfiguredBotoSession | None:
    if not any(
        (
            config["endpoint_url"],
            config["access_key_id"],
            config["secret_access_key"],
            config["session_token"],
        )
    ):
        return None

    return ConfiguredBotoSession(
        endpoint_url=config["endpoint_url"],
        region_name=config["region"],
        aws_access_key_id=config["access_key_id"],
        aws_secret_access_key=config["secret_access_key"],
        aws_session_token=config["session_token"],
    )


def _redact_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlsplit(url)
    if parsed.username is None and parsed.password is None:
        return url

    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (
            parsed.scheme,
            f"[REDACTED]@{hostname}{port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )
