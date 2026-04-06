import os
from pathlib import Path
from typing import overload


class NoValue:
    pass


type SecretValue = str | bool | list[str] | None
type SecretDefault = str | bool | list[str] | None | NoValue


class SecretNotFound(Exception):
    def __init__(self, name: str):
        super().__init__(f"Secret not found: {name}")
        self.name = name


class Backend:
    env_vars: dict[str, str]

    def get(self, name: str) -> str:
        if name not in self.env_vars:
            raise SecretNotFound(name)
        return self.env_vars[name]


class DotEnvBackend(Backend):
    def __init__(self, env_file: str | os.PathLike[str] | None):
        self.env_vars = {}

        if env_file is None:
            return

        path = Path(env_file)
        if not path.exists():
            return

        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            self.env_vars[key.strip()] = value.strip().strip("\"'")


class OSEnvVarBackend(Backend):
    def get(self, name: str) -> str:
        fetched_env_var = os.getenv(name)
        if fetched_env_var is not None:
            return fetched_env_var
        raise SecretNotFound(name)


class SecretsManager:
    NOTSET = NoValue()

    def __init__(
        self,
        *,
        path: str | os.PathLike[str] | None = None,
    ):
        self.backends: list[Backend] = [OSEnvVarBackend()]
        if path is not None:
            self.backends.append(DotEnvBackend(path))

    @overload
    def get(self, secret_type: type[str], name: str, default: NoValue = NOTSET) -> str: ...

    @overload
    def get(self, secret_type: type[str], name: str, default: str | None) -> str | None: ...

    @overload
    def get(self, secret_type: type[bool], name: str, default: NoValue = NOTSET) -> bool: ...

    @overload
    def get(self, secret_type: type[bool], name: str, default: bool | None) -> bool | None: ...

    @overload
    def get(self, secret_type: type[list], name: str, default: NoValue = NOTSET) -> list[str]: ...

    @overload
    def get(
        self, secret_type: type[list], name: str, default: list[str] | None
    ) -> list[str] | None: ...

    def get(
        self,
        secret_type: type[str] | type[bool] | type[list],
        name: str,
        default: SecretDefault = NOTSET,
    ) -> SecretValue:
        result: SecretValue
        try:
            result = self._get_from_all_backends(name)
        except SecretNotFound as exc:
            if isinstance(default, NoValue):
                raise exc
            if default is None:
                return None
            result = default

        if secret_type is bool:
            if isinstance(result, bool):
                return result

            normalized = str(result).strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            raise ValueError(f"Cannot coerce {name}={result!r} to bool")

        if secret_type is list:
            if isinstance(result, list):
                return [str(item).strip() for item in result if str(item).strip()]
            return [item.strip() for item in str(result).split(",") if item.strip()]

        return str(result)

    def _get_from_all_backends(self, name: str) -> str:
        for backend in self.backends:
            try:
                return backend.get(name)
            except SecretNotFound:
                continue

        raise SecretNotFound(name)
