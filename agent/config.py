from .secret_manager import SecretsManager

secret_manager = SecretsManager(path=".env")

OPENAI_API_KEY = secret_manager.get(str, "OPENAI_API_KEY")
RUN_HISTORY_ENABLED = secret_manager.get(bool, "DEVOPS_AGENT_RUN_HISTORY_ENABLED", True)
