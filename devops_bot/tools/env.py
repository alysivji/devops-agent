import os
import re
from pathlib import Path
from typing import Protocol, TypedDict

from dotenv import dotenv_values
from strands import tool

from ..agents.env_example_editor import EditedEnvExample, EnvExampleUpdateAgent

ENV_EXAMPLE_PATH = Path(".env.example")
ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")
ENV_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*#?\s*(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=",
    re.MULTILINE,
)
ANSIBLE_ENV_LOOKUP_PATTERN = re.compile(
    r"lookup\(\s*['\"](?:ansible\.builtin\.)?env['\"]\s*,\s*['\"](?P<name>[A-Z_][A-Z0-9_]*)['\"]",
)


class EnvExampleUpdateResult(TypedDict):
    path: str
    variables: list[str]
    required_variables: list[str]
    optional_variables: list[str]
    added: list[str]
    already_present: list[str]


class EnvLoadedKeysResult(TypedDict):
    dotenv_path: str
    loaded_keys: list[str]
    required_variables: list[str]
    optional_variables: list[str]
    present_required: list[str]
    missing_required: list[str]
    present_optional: list[str]
    missing_optional: list[str]


class EnvExampleEditor(Protocol):
    def run(
        self,
        *,
        env_example_content: str,
        required_variable_names: list[str],
        optional_variable_names: list[str],
        source_path: str,
        section_name: str,
        placeholder_value: str,
    ) -> EditedEnvExample: ...


@tool
def env_list_loaded_keys(
    variable_names: str = "",
    optional_variable_names: str = "",
    source_path: str = "",
) -> EnvLoadedKeysResult:
    """
    List environment variable keys with values available from process env or .env.

    Args:
        variable_names: Comma, newline, or space separated required variable names to check.
        optional_variable_names: Comma, newline, or space separated optional
            variable names to check.
        source_path: Optional relative file path to scan for literal Ansible env lookups. Lookups
            with non-empty defaults are treated as optional.

    Returns:
        A dictionary of key names only. Secret values are never returned.
    """
    required_variables, optional_variables = _collect_env_var_names(
        variable_names=variable_names,
        optional_variable_names=optional_variable_names,
        source_path=source_path,
    )
    loaded_keys = _loaded_env_keys(dotenv_path=Path(".env"))
    loaded_key_set = set(loaded_keys)

    return {
        "dotenv_path": ".env",
        "loaded_keys": _filter_loaded_keys(
            loaded_keys=loaded_keys,
            variable_names=[*required_variables, *optional_variables],
        ),
        "required_variables": required_variables,
        "optional_variables": optional_variables,
        "present_required": [name for name in required_variables if name in loaded_key_set],
        "missing_required": [name for name in required_variables if name not in loaded_key_set],
        "present_optional": [name for name in optional_variables if name in loaded_key_set],
        "missing_optional": [name for name in optional_variables if name not in loaded_key_set],
    }


@tool
def env_example_update(
    variable_names: str = "",
    optional_variable_names: str = "",
    source_path: str = "",
    section_name: str = "",
    placeholder_value: str = "change-me",
) -> EnvExampleUpdateResult:
    """
    Add missing environment variable placeholders to the local .env.example file.

    Args:
        variable_names: Comma, newline, or space separated required variable names.
        optional_variable_names: Comma, newline, or space separated optional variable names.
        source_path: Optional relative file path to scan for literal Ansible env lookups. Lookups
            with non-empty defaults are treated as optional.
        section_name: Optional section title to use for placement. When omitted, the tool
            infers a section from source_path and the existing .env.example sections.
        placeholder_value: Non-secret placeholder value to use for newly added variables.

    Returns:
        A dictionary describing which variables were added or already documented.
    """
    required_variables, optional_variables = _collect_env_var_names(
        variable_names=variable_names,
        optional_variable_names=optional_variable_names,
        source_path=source_path,
    )
    variables = sorted({*required_variables, *optional_variables})
    if not variables:
        raise ValueError("provide variable_names or a source_path containing env lookups")

    return _update_env_example(
        env_example_path=ENV_EXAMPLE_PATH,
        required_variable_names=required_variables,
        optional_variable_names=optional_variables,
        source_path=source_path,
        section_name=section_name,
        placeholder_value=placeholder_value,
    )


def _collect_env_var_names(
    *,
    variable_names: str,
    optional_variable_names: str,
    source_path: str,
) -> tuple[list[str], list[str]]:
    required_names = set(_parse_env_var_names(variable_names))
    optional_names = set(_parse_env_var_names(optional_variable_names))
    if source_path.strip():
        source_required, source_optional = _extract_ansible_env_lookup_names(
            _read_relative_file(source_path)
        )
        required_names.update(source_required)
        optional_names.update(source_optional)

    required_names.difference_update(optional_names)
    return sorted(required_names), sorted(optional_names)


def _parse_env_var_names(value: str) -> list[str]:
    names = [name for name in re.split(r"[\s,]+", value.strip()) if name]
    invalid = [name for name in names if not ENV_VAR_NAME_PATTERN.fullmatch(name)]
    if invalid:
        raise ValueError(f"invalid environment variable names: {', '.join(sorted(invalid))}")
    return names


def _extract_ansible_env_lookup_names(content: str) -> tuple[list[str], list[str]]:
    required_names: set[str] = set()
    optional_names: set[str] = set()
    for line in content.splitlines():
        for match in ANSIBLE_ENV_LOOKUP_PATTERN.finditer(line):
            call_suffix = line[match.end() :]
            name = match.group("name")
            if "default=" in call_suffix and not _has_empty_default(call_suffix):
                optional_names.add(name)
            else:
                required_names.add(name)

    required_names.difference_update(optional_names)
    return sorted(required_names), sorted(optional_names)


def _has_empty_default(call_suffix: str) -> bool:
    return "default=''" in call_suffix or 'default=""' in call_suffix


def _read_relative_file(source_path: str) -> str:
    path = Path(source_path)
    if path.is_absolute():
        raise ValueError("source_path must be relative")

    resolved_path = path.resolve()
    resolved_cwd = Path.cwd().resolve()
    if resolved_path != resolved_cwd and resolved_cwd not in resolved_path.parents:
        raise ValueError("source_path must stay inside the current workspace")

    return path.read_text(encoding="utf-8")


def _loaded_env_keys(*, dotenv_path: Path) -> list[str]:
    dotenv_keys = {
        key
        for key, value in dotenv_values(dotenv_path).items()
        if value is not None and value != ""
    }
    process_keys = {key for key, value in os.environ.items() if value}
    return sorted(dotenv_keys.union(process_keys))


def _filter_loaded_keys(*, loaded_keys: list[str], variable_names: list[str]) -> list[str]:
    if not variable_names:
        dotenv_keys = {
            key for key, value in dotenv_values(".env").items() if value is not None and value != ""
        }
        return [key for key in loaded_keys if key in dotenv_keys]

    requested_names = set(variable_names)
    return [key for key in loaded_keys if key in requested_names]


def _update_env_example(
    *,
    env_example_path: Path,
    required_variable_names: list[str],
    optional_variable_names: list[str],
    source_path: str,
    section_name: str,
    placeholder_value: str,
    editor: EnvExampleEditor | None = None,
) -> EnvExampleUpdateResult:
    content = env_example_path.read_text(encoding="utf-8") if env_example_path.exists() else ""
    existing = set(_extract_documented_env_var_names(content))
    variable_names = sorted({*required_variable_names, *optional_variable_names})
    added = [name for name in variable_names if name not in existing]
    already_present = [name for name in variable_names if name in existing]

    if added:
        added_required = [name for name in required_variable_names if name in added]
        added_optional = [name for name in optional_variable_names if name in added]
        edited = (editor or EnvExampleUpdateAgent()).run(
            env_example_content=content,
            required_variable_names=added_required,
            optional_variable_names=added_optional,
            source_path=source_path,
            section_name=section_name,
            placeholder_value=placeholder_value,
        )
        _validate_updated_env_example(
            original_content=content,
            updated_content=edited.content,
            required_variable_names=required_variable_names,
            optional_variable_names=optional_variable_names,
        )
        env_example_path.write_text(_normalize_file_content(edited.content), encoding="utf-8")

    return {
        "path": str(env_example_path),
        "variables": variable_names,
        "required_variables": required_variable_names,
        "optional_variables": optional_variable_names,
        "added": added,
        "already_present": already_present,
    }


def _extract_documented_env_var_names(content: str) -> list[str]:
    return [match.group("name") for match in ENV_ASSIGNMENT_PATTERN.finditer(content)]


def _validate_updated_env_example(
    *,
    original_content: str,
    updated_content: str,
    required_variable_names: list[str],
    optional_variable_names: list[str],
) -> None:
    original_names = set(_extract_documented_env_var_names(original_content))
    updated_names = set(_extract_documented_env_var_names(updated_content))
    removed_names = sorted(original_names.difference(updated_names))
    if removed_names:
        raise ValueError(
            f"updated .env.example removed existing variables: {', '.join(removed_names)}"
        )

    missing_required = [
        name
        for name in required_variable_names
        if not _has_active_assignment(updated_content, name)
    ]
    if missing_required:
        raise ValueError(
            "updated .env.example is missing required active assignments: "
            + ", ".join(missing_required)
        )

    missing_optional = [
        name
        for name in optional_variable_names
        if not _has_commented_assignment(updated_content, name)
    ]
    if missing_optional:
        raise ValueError(
            "updated .env.example is missing optional commented assignments: "
            + ", ".join(missing_optional)
        )


def _has_active_assignment(content: str, variable_name: str) -> bool:
    return _active_assignment_pattern(variable_name).search(content) is not None


def _has_commented_assignment(content: str, variable_name: str) -> bool:
    return _commented_assignment_pattern(variable_name).search(content) is not None


def _active_assignment_pattern(variable_name: str) -> re.Pattern[str]:
    return re.compile(
        rf"^\s*(?:export\s+)?{re.escape(variable_name)}\s*=",
        re.MULTILINE,
    )


def _commented_assignment_pattern(variable_name: str) -> re.Pattern[str]:
    return re.compile(
        rf"^\s*#\s*(?:export\s+)?{re.escape(variable_name)}\s*=",
        re.MULTILINE,
    )


def _normalize_file_content(content: str) -> str:
    return f"{content.rstrip()}\n"
