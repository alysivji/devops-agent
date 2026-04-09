from .secret_manager import SecretsManager

secret_manager = SecretsManager(path=".env")

OPENAI_API_KEY = secret_manager.get(str, "OPENAI_API_KEY")
