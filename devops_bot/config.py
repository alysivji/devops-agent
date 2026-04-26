import logging

from langfuse import get_client

from .secrets import SecretsManager

secret_manager = SecretsManager(path=".env")

# https://strandsagents.com/docs/user-guide/observability-evaluation/logs/
logging.getLogger("strands").setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)

OPENAI_API_KEY = secret_manager.get(str, "OPENAI_API_KEY")

RUN_HISTORY_ENABLED = secret_manager.get(bool, "DEVOPS_AGENT_RUN_HISTORY_ENABLED", True)

LANGFUSE_ENABLED = secret_manager.get(bool, "LANGFUSE_ENABLED", False)
langfuse = get_client() if LANGFUSE_ENABLED else None

SESSION_BACKEND = secret_manager.get(str, "DEVOPS_AGENT_SESSION_BACKEND", "none")
SESSION_S3_BUCKET = secret_manager.get(str, "DEVOPS_AGENT_SESSION_S3_BUCKET", None)
SESSION_S3_PREFIX = secret_manager.get(str, "DEVOPS_AGENT_SESSION_S3_PREFIX", "devops-agent/")
SESSION_S3_REGION = secret_manager.get(str, "DEVOPS_AGENT_SESSION_S3_REGION", "us-east-1")
SESSION_S3_ENDPOINT_URL = secret_manager.get(str, "DEVOPS_AGENT_SESSION_S3_ENDPOINT_URL", None)
SESSION_S3_ADDRESSING_STYLE = secret_manager.get(
    str, "DEVOPS_AGENT_SESSION_S3_ADDRESSING_STYLE", "path"
)
SESSION_S3_ACCESS_KEY_ID = secret_manager.get(
    str,
    "DEVOPS_AGENT_SESSION_S3_ACCESS_KEY_ID",
    secret_manager.get(
        str,
        "MINIO_ROOT_USER",
        secret_manager.get(str, "AWS_ACCESS_KEY_ID", None),
    ),
)
SESSION_S3_SECRET_ACCESS_KEY = secret_manager.get(
    str,
    "DEVOPS_AGENT_SESSION_S3_SECRET_ACCESS_KEY",
    secret_manager.get(
        str,
        "MINIO_ROOT_PASSWORD",
        secret_manager.get(str, "AWS_SECRET_ACCESS_KEY", None),
    ),
)
SESSION_S3_SESSION_TOKEN = secret_manager.get(
    str,
    "DEVOPS_AGENT_SESSION_S3_SESSION_TOKEN",
    secret_manager.get(str, "AWS_SESSION_TOKEN", None),
)
