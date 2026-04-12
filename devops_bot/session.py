from dataclasses import dataclass
from typing import Any
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
SESSION_S3_BACKEND = "s3"


@dataclass(frozen=True)
class _SessionStorageSettings:
    backend: str
    bucket: str | None
    prefix: str
    region: str | None
    endpoint_url: str | None
    addressing_style: str
    access_key_id: str | None
    secret_access_key: str | None
    session_token: str | None


def build_session_manager(session_id: str) -> SessionManager | None:
    settings = _load_session_storage_settings()
    if settings.backend == "none":
        return None

    if settings.backend != SESSION_S3_BACKEND:
        raise ValueError(
            "Unsupported DEVOPS_AGENT_SESSION_BACKEND="
            f"{settings.backend!r}; expected 'none' or 's3'"
        )

    if not settings.bucket:
        raise ValueError(
            "DEVOPS_AGENT_SESSION_S3_BUCKET is required when DEVOPS_AGENT_SESSION_BACKEND=s3"
        )

    return S3SessionManager(
        session_id=session_id,
        bucket=settings.bucket,
        prefix=settings.prefix,
        boto_session=_build_boto_session(settings),
        boto_client_config=BotocoreConfig(
            signature_version="s3v4",
            s3={"addressing_style": settings.addressing_style},
        ),
        region_name=settings.region,
    )


def get_session_storage_event_details(*, session_id: str) -> dict[str, str | None] | None:
    settings = _load_session_storage_settings()
    if settings.backend == "none":
        return None

    return {
        "backend": settings.backend,
        "bucket": settings.bucket,
        "prefix": settings.prefix,
        "endpoint_url": _redact_url(settings.endpoint_url),
        "session_id": session_id,
    }


def _load_session_storage_settings() -> _SessionStorageSettings:
    backend = _config(SESSION_BACKEND_ENV_VAR, SESSION_BACKEND)
    return _SessionStorageSettings(
        backend=(backend or "none").strip().lower(),
        bucket=_config(SESSION_S3_BUCKET_ENV_VAR, SESSION_S3_BUCKET),
        prefix=_config(SESSION_S3_PREFIX_ENV_VAR, SESSION_S3_PREFIX) or "",
        region=_config(SESSION_S3_REGION_ENV_VAR, SESSION_S3_REGION),
        endpoint_url=_config(SESSION_S3_ENDPOINT_URL_ENV_VAR, SESSION_S3_ENDPOINT_URL),
        addressing_style=_config(
            SESSION_S3_ADDRESSING_STYLE_ENV_VAR,
            SESSION_S3_ADDRESSING_STYLE,
        )
        or "path",
        access_key_id=_config(
            SESSION_S3_ACCESS_KEY_ID_ENV_VAR,
            SESSION_S3_ACCESS_KEY_ID,
        ),
        secret_access_key=_config(
            SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR,
            SESSION_S3_SECRET_ACCESS_KEY,
        ),
        session_token=_config(SESSION_S3_SESSION_TOKEN_ENV_VAR, SESSION_S3_SESSION_TOKEN),
    )


def _config(name: str, default: str | None) -> str | None:
    return secret_manager.get(str, name, default)


def _build_boto_session(settings: _SessionStorageSettings) -> boto3.Session | None:
    if not any(
        (
            settings.endpoint_url,
            settings.access_key_id,
            settings.secret_access_key,
            settings.session_token,
        )
    ):
        return None

    return _EndpointBotoSession(
        endpoint_url=settings.endpoint_url,
        region_name=settings.region,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        aws_session_token=settings.session_token,
    )


class _EndpointBotoSession(boto3.Session):
    def __init__(self, *, endpoint_url: str | None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._endpoint_url = endpoint_url

    def client(self, *args: Any, **kwargs: Any) -> Any:
        service_name = kwargs.get("service_name") or (args[0] if args else None)
        if service_name == "s3" and self._endpoint_url and "endpoint_url" not in kwargs:
            kwargs["endpoint_url"] = self._endpoint_url

        return super().client(*args, **kwargs)


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
