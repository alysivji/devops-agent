from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from devops_bot.secrets import SecretsManager

BASE_DIR = Path(__file__).resolve().parents[3]
SECRET_MANAGER = SecretsManager(path=BASE_DIR / ".env")


def _config(
    name: str,
    default: str | bool | list[str] | None = None,
) -> str | bool | list[str] | None:
    if isinstance(default, bool):
        return SECRET_MANAGER.get(bool, name, default)
    if isinstance(default, list):
        return SECRET_MANAGER.get(list, name, default)
    return SECRET_MANAGER.get(str, name, default)


def _list_config(name: str, default: list[str]) -> list[str]:
    value = _config(name, default)
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    return default


def _redis_database_url(url: str, database: int) -> str:
    parsed = urlsplit(url)
    path = f"/{database}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


SECRET_KEY = str(_config("DJANGO_SECRET_KEY", "devops-agent-local-secret-key"))
DEBUG = bool(_config("DJANGO_DEBUG", True))
ALLOWED_HOSTS = _list_config("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.api.conversations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "apps.api.project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "apps.api.project.wsgi.application"
ASGI_APPLICATION = "apps.api.project.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "apps" / "api" / "db.sqlite3"),
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Chicago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = str(_config("REDIS_URL", "redis://127.0.0.1:6379/0"))
CELERY_BROKER_URL = _redis_database_url(REDIS_URL, 0)
CELERY_RESULT_BACKEND = _redis_database_url(REDIS_URL, 1)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(str(_config("CELERY_TASK_TIME_LIMIT", "1800")))
CELERY_RESULT_EXPIRES = int(str(_config("CELERY_RESULT_EXPIRES", "86400")))
CELERY_TASK_ALWAYS_EAGER = bool(_config("CELERY_TASK_ALWAYS_EAGER", False))
CELERY_TASK_EAGER_PROPAGATES = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _redis_database_url(REDIS_URL, 2),
    }
}
