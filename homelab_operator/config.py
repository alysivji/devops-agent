import logging

from langfuse import Langfuse

from .secrets import SecretsManager

secret_manager = SecretsManager(path=".env")
RUN_HISTORY_ENV_VAR = "HOMELAB_OPERATOR_RUN_HISTORY_ENABLED"
SESSION_BACKEND_ENV_VAR = "HOMELAB_OPERATOR_SESSION_BACKEND"
SESSION_S3_BUCKET_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_BUCKET"
SESSION_S3_PREFIX_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_PREFIX"
SESSION_S3_REGION_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_REGION"
SESSION_S3_ENDPOINT_URL_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_ENDPOINT_URL"
SESSION_S3_ADDRESSING_STYLE_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_ADDRESSING_STYLE"
SESSION_S3_ACCESS_KEY_ID_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_ACCESS_KEY_ID"
SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_SECRET_ACCESS_KEY"
SESSION_S3_SESSION_TOKEN_ENV_VAR = "HOMELAB_OPERATOR_SESSION_S3_SESSION_TOKEN"

# https://strandsagents.com/docs/user-guide/observability-evaluation/logs/
logging.getLogger("strands").setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)

OPENAI_API_KEY = secret_manager.get(str, "OPENAI_API_KEY")

RUN_HISTORY_ENABLED = bool(secret_manager.get(bool, RUN_HISTORY_ENV_VAR, True))

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

SESSION_BACKEND = secret_manager.get(str, SESSION_BACKEND_ENV_VAR, "none")
SESSION_S3_BUCKET = secret_manager.get(str, SESSION_S3_BUCKET_ENV_VAR, None)
SESSION_S3_PREFIX = secret_manager.get(str, SESSION_S3_PREFIX_ENV_VAR, "homelab-operator/")
SESSION_S3_REGION = secret_manager.get(str, SESSION_S3_REGION_ENV_VAR, "us-east-1")
SESSION_S3_ENDPOINT_URL = secret_manager.get(str, SESSION_S3_ENDPOINT_URL_ENV_VAR, None)
SESSION_S3_ADDRESSING_STYLE = secret_manager.get(str, SESSION_S3_ADDRESSING_STYLE_ENV_VAR, "path")
SESSION_S3_ACCESS_KEY_ID = secret_manager.get(
    str,
    SESSION_S3_ACCESS_KEY_ID_ENV_VAR,
    secret_manager.get(
        str,
        "MINIO_ROOT_USER",
        secret_manager.get(str, "AWS_ACCESS_KEY_ID", None),
    ),
)
SESSION_S3_SECRET_ACCESS_KEY = secret_manager.get(
    str,
    SESSION_S3_SECRET_ACCESS_KEY_ENV_VAR,
    secret_manager.get(
        str,
        "MINIO_ROOT_PASSWORD",
        secret_manager.get(str, "AWS_SECRET_ACCESS_KEY", None),
    ),
)
SESSION_S3_SESSION_TOKEN = secret_manager.get(
    str,
    SESSION_S3_SESSION_TOKEN_ENV_VAR,
    secret_manager.get(str, "AWS_SESSION_TOKEN", None),
)
