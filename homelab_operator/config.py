import logging

from langfuse import Langfuse

from .secrets import SecretsManager

secret_manager = SecretsManager(path=".env")
RUN_HISTORY_ENV_VAR = "HOMELAB_OPERATOR_RUN_HISTORY_ENABLED"
LEGACY_RUN_HISTORY_ENV_VAR = "DEVOPS_AGENT_RUN_HISTORY_ENABLED"
SESSION_BACKEND_ENV_VAR = "HOMELAB_OPERATOR_SESSION_BACKEND"
LEGACY_SESSION_BACKEND_ENV_VAR = "DEVOPS_AGENT_SESSION_BACKEND"
SESSION_S3_BUCKET_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_BUCKET"
LEGACY_SESSION_S3_BUCKET_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_BUCKET"
SESSION_S3_PREFIX_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_PREFIX"
LEGACY_SESSION_S3_PREFIX_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_PREFIX"
SESSION_S3_REGION_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_REGION"
LEGACY_SESSION_S3_REGION_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_REGION"
SESSION_S3_ENDPOINT_URL_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_ENDPOINT_URL"
LEGACY_SESSION_S3_ENDPOINT_URL_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_ENDPOINT_URL"
SESSION_S3_ADDRESSING_STYLE_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_ADDRESSING_STYLE"
LEGACY_SESSION_S3_ADDRESSING_STYLE_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_ADDRESSING_STYLE"
SESSION_S3_ACCESS_KEY_ID_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_ACCESS_KEY_ID"
LEGACY_SESSION_S3_ACCESS_KEY_ID_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_ACCESS_KEY_ID"
SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_SECRET_ACCESS_KEY"
LEGACY_SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_SECRET_ACCESS_KEY"
SESSION_S3_SESSION_TOKEN_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_SESSION_TOKEN"
LEGACY_SESSION_S3_SESSION_TOKEN_ENV_VAR = "DEVOPS_AGENT_SESSION_S3_SESSION_TOKEN"

# https://strandsagents.com/docs/user-guide/observability-evaluation/logs/
logging.getLogger("strands").setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)


def _get_str(name: str, legacy_name: str, default: str | None) -> str | None:
    value = secret_manager.get(str, name, None)
    if value is not None:
        return value
    return secret_manager.get(str, legacy_name, default)


def _get_bool(name: str, legacy_name: str, default: bool) -> bool:
    value = secret_manager.get(bool, name, None)
    if value is not None:
        return bool(value)
    legacy_value = secret_manager.get(bool, legacy_name, default)
    return bool(legacy_value)


OPENAI_API_KEY = secret_manager.get(str, "OPENAI_API_KEY")

RUN_HISTORY_ENABLED = _get_bool(RUN_HISTORY_ENV_VAR, LEGACY_RUN_HISTORY_ENV_VAR, True)

LANGFUSE_ENABLED = secret_manager.get(bool, "LANGFUSE_ENABLED", False)
langfuse = (
    Langfuse(
        public_key=secret_manager.get(str, "LANGFUSE_PUBLIC_KEY", None),
        secret_key=secret_manager.get(str, "LANGFUSE_SECRET_KEY", None),
        base_url=secret_manager.get(str, "LANGFUSE_BASE_URL", None),
    )
    if LANGFUSE_ENABLED
    else None
)

SESSION_BACKEND = _get_str(SESSION_BACKEND_ENV_VAR, LEGACY_SESSION_BACKEND_ENV_VAR, "none")
SESSION_S3_BUCKET = _get_str(SESSION_S3_BUCKET_ENV_VAR, LEGACY_SESSION_S3_BUCKET_ENV_VAR, None)
SESSION_S3_PREFIX = _get_str(
    SESSION_S3_PREFIX_ENV_VAR,
    LEGACY_SESSION_S3_PREFIX_ENV_VAR,
    "homelab-operator/",
)
SESSION_S3_REGION = _get_str(
    SESSION_S3_REGION_ENV_VAR,
    LEGACY_SESSION_S3_REGION_ENV_VAR,
    "us-east-1",
)
SESSION_S3_ENDPOINT_URL = _get_str(
    SESSION_S3_ENDPOINT_URL_ENV_VAR,
    LEGACY_SESSION_S3_ENDPOINT_URL_ENV_VAR,
    None,
)
SESSION_S3_ADDRESSING_STYLE = _get_str(
    SESSION_S3_ADDRESSING_STYLE_ENV_VAR,
    LEGACY_SESSION_S3_ADDRESSING_STYLE_ENV_VAR,
    "path",
)
SESSION_S3_ACCESS_KEY_ID = secret_manager.get(
    str,
    SESSION_S3_ACCESS_KEY_ID_ENV_VAR,
    _get_str(
        LEGACY_SESSION_S3_ACCESS_KEY_ID_ENV_VAR,
        LEGACY_SESSION_S3_ACCESS_KEY_ID_ENV_VAR,
        secret_manager.get(
            str,
            "MINIO_ROOT_USER",
            secret_manager.get(str, "AWS_ACCESS_KEY_ID", None),
        ),
    ),
)
SESSION_S3_SECRET_ACCESS_KEY = secret_manager.get(
    str,
    SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR,
    _get_str(
        LEGACY_SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR,
        LEGACY_SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR,
        secret_manager.get(
            str,
            "MINIO_ROOT_PASSWORD",
            secret_manager.get(str, "AWS_SECRET_ACCESS_KEY", None),
        ),
    ),
)
SESSION_S3_SESSION_TOKEN = secret_manager.get(
    str,
    SESSION_S3_SESSION_TOKEN_ENV_VAR,
    secret_manager.get(
        str,
        LEGACY_SESSION_S3_SESSION_TOKEN_ENV_VAR,
        secret_manager.get(str, "AWS_SESSION_TOKEN", None),
    ),
)
