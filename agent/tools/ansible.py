import configparser
import logging
import os
import pathlib
import re
import subprocess
import time
import unicodedata
from functools import lru_cache
from typing import Final

import yaml
from pydantic import BaseModel, ValidationError
from strands import tool

from ..run_history import record_event

logger = logging.getLogger(__name__)

ANSIBLE_TMP_DIR: Final[pathlib.Path] = pathlib.Path(".ansible/tmp")
PLAYBOOKS_DIR: Final[pathlib.Path] = pathlib.Path("ansible/playbooks")
INVENTORY_PATH: Final[pathlib.Path] = pathlib.Path("ansible/inventory.ini")


class AnsiblePlaybookMetadata(BaseModel):
    name: str
    description: str
    target: str
    requires_approval: bool
    tags: list[str] = []


class AnsiblePlaybookRegistryEntry(AnsiblePlaybookMetadata):
    path: str


def _confirm_playbook_execution(entry: AnsiblePlaybookRegistryEntry) -> bool:
    response = input(f"Run playbook '{entry.name}' at {entry.path}? [y/N]: ").strip().lower()
    return response in {"y", "yes"}


def _ansible_env() -> dict[str, str]:
    """Create a writable environment for Ansible temp files."""
    ANSIBLE_TMP_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["ANSIBLE_LOCAL_TEMP"] = str(ANSIBLE_TMP_DIR.resolve())
    _remove_unsupported_locale_vars(env)
    return env


@lru_cache(maxsize=1)
def _available_locales() -> set[str]:
    """Return locales available on this host for subprocess validation."""
    try:
        result = subprocess.run(
            ["locale", "-a"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return set()

    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _remove_unsupported_locale_vars(env: dict[str, str]) -> None:
    """Drop locale env vars whose values are not available on this host."""
    available = _available_locales()
    if not available:
        return

    for key in ("LC_ALL", "LANG", "LC_CTYPE"):
        value = env.get(key)
        if value and value not in available:
            env.pop(key, None)


def _decode_output(output: str | bytes) -> str:
    """Normalize subprocess output across real runs and recorded replays."""
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8")
    return output


def _parse_playbook_metadata(playbook_path: pathlib.Path) -> AnsiblePlaybookRegistryEntry:
    metadata_lines: list[str] = []

    with playbook_path.open(encoding="utf-8") as playbook_file:
        for line in playbook_file:
            if line.startswith("#"):
                metadata_lines.append(line.removeprefix("#"))
                continue
            if metadata_lines:
                break

    if not metadata_lines:
        raise ValueError(f"Playbook is missing metadata header: {playbook_path}")

    metadata = yaml.safe_load("".join(metadata_lines))
    if not isinstance(metadata, dict):
        raise ValueError(f"Playbook metadata must be a mapping: {playbook_path}")

    try:
        validated = AnsiblePlaybookMetadata.model_validate(metadata)
    except ValidationError as exc:
        raise ValueError(f"Invalid playbook metadata for {playbook_path}: {exc}") from exc

    return AnsiblePlaybookRegistryEntry(path=str(playbook_path), **validated.model_dump())


def _get_registry_entry_by_path(playbook_path: str) -> AnsiblePlaybookRegistryEntry:
    for entry in get_ansible_playbook_registry():
        path = entry.get("path")
        if path == playbook_path:
            return AnsiblePlaybookRegistryEntry.model_validate(entry)
    raise ValueError(f"Playbook path is not in the registry: {playbook_path}")


def normalize_playbook_name(name: str) -> str:
    """Convert a playbook name to a filesystem-safe slug."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    if not normalized:
        raise ValueError("playbook name must contain at least one alphanumeric character")
    return normalized


@tool
def get_ansible_inventory_groups() -> list[str]:
    """Return the supported top-level inventory groups from ansible/inventory.ini."""
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(INVENTORY_PATH, encoding="utf-8")
    groups = sorted(section for section in parser.sections() if ":" not in section)
    record_event(
        kind="inventory_groups_read",
        status="completed",
        what="Read supported inventory groups.",
        why="Playbook generation uses the inventory groups to target control, cluster, or both.",
        details={"groups": groups},
    )
    return groups


@tool
def get_ansible_playbook_registry() -> list[dict[str, str | bool | list[str]]]:
    """Return the Ansible playbook registry with validated metadata.

    Returns:
        A list of playbook metadata dictionaries, including the playbook path.
    """
    registry = [
        _parse_playbook_metadata(file).model_dump()
        for file in sorted(PLAYBOOKS_DIR.iterdir())
        if file.is_file() and file.suffix in [".yaml", ".yml"]
    ]
    record_event(
        kind="playbook_registry_read",
        status="completed",
        what="Read the playbook registry.",
        why="Inspect existing automation before creating or executing a playbook.",
        details={"count": len(registry), "paths": [str(entry["path"]) for entry in registry]},
    )
    return registry


@tool
def run_ansible_playbook(playbook_path: str) -> str:
    """Run a validated Ansible playbook and return its standard output.

    Args:
        playbook_path: Relative path to a playbook file in the validated registry.

    Returns:
        The decoded stdout from the Ansible process.

    Raises:
        ValueError: If the provided playbook path is not in the validated registry.
        PermissionError: If execution was not approved for a gated playbook.
        RuntimeError: If ansible-playbook exits with a non-zero status.
    """
    entry = _get_registry_entry_by_path(playbook_path)
    record_event(
        kind="playbook_execution_requested",
        status="started",
        what=f"Requested execution for playbook `{playbook_path}`.",
        why="The orchestrator selected this existing playbook from the validated registry.",
        details={"playbook_path": playbook_path, "requires_approval": entry.requires_approval},
    )

    if entry.requires_approval and not _confirm_playbook_execution(entry):
        record_event(
            kind="playbook_execution_declined",
            status="declined",
            what=f"Declined execution for playbook `{playbook_path}`.",
            why="This playbook requires explicit human approval before execution.",
            details={"playbook_path": playbook_path, "approved": False},
        )
        raise PermissionError(f"Execution not approved for playbook: {playbook_path}")

    record_event(
        kind="playbook_execution_approved",
        status="approved",
        what=f"Approved execution for playbook `{playbook_path}`.",
        why=(
            "Execution can proceed once the registry entry is approved or "
            "does not require approval."
        ),
        details={"playbook_path": playbook_path, "approved": True},
    )
    command = ["ansible-playbook", playbook_path, "-vv"]
    record_event(
        kind="playbook_execution_started",
        status="started",
        what=f"Started playbook execution for `{playbook_path}`.",
        why="Run the selected playbook through ansible-playbook with verbose output.",
        details={"playbook_path": playbook_path, "command": command},
    )
    started_at = time.monotonic()

    try:
        result = subprocess.run(
            command,
            check=True,
            env=_ansible_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout = _decode_output(result.stdout)
        elapsed_seconds = round(time.monotonic() - started_at, 3)
        record_event(
            kind="playbook_execution_succeeded",
            status="completed",
            what=f"Playbook `{playbook_path}` completed successfully.",
            why="Capture a compact execution summary after ansible-playbook exits cleanly.",
            details={
                "playbook_path": playbook_path,
                "command": command,
                "elapsed_seconds": elapsed_seconds,
                "stdout_summary": _summarize_ansible_output(stdout),
            },
        )
        return stdout
    except subprocess.CalledProcessError as exc:
        logger.exception("Ansible playbook execution failed")
        stdout = _decode_output(exc.stdout).strip()
        stderr = _decode_output(exc.stderr).strip()
        elapsed_seconds = round(time.monotonic() - started_at, 3)
        record_event(
            kind="playbook_execution_failed",
            status="failed",
            what=f"Playbook `{playbook_path}` failed.",
            why="Capture the failing command and compact stderr/stdout details for review.",
            details={
                "playbook_path": playbook_path,
                "command": command,
                "elapsed_seconds": elapsed_seconds,
                "stdout_summary": _summarize_ansible_output(stdout),
                "stderr_summary": _summarize_ansible_output(stderr),
            },
        )
        details = "\n".join(part for part in (stderr, stdout) if part)
        if details:
            raise RuntimeError(f"Ansible playbook execution failed:\n{details}") from exc
        raise RuntimeError("Ansible playbook execution failed") from exc


def _summarize_ansible_output(output: str) -> str:
    normalized = output.strip()
    if not normalized:
        return ""

    play_recap_index = normalized.rfind("PLAY RECAP")
    if play_recap_index != -1:
        return normalized[play_recap_index:]

    lines = [line for line in normalized.splitlines() if line.strip()]
    return "\n".join(lines[-10:])
