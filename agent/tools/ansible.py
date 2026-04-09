import configparser
import logging
import os
import pathlib
import re
import subprocess
import unicodedata
from typing import Final

import yaml
from pydantic import BaseModel, ValidationError
from strands import tool

from ..utils import validate_generated_playbook_yaml

logger = logging.getLogger(__name__)

ANSIBLE_TMP_DIR: Final[pathlib.Path] = pathlib.Path(".ansible/tmp")
PLAYBOOKS_DIR: Final[pathlib.Path] = pathlib.Path("ansible/playbooks")
INVENTORY_PATH: Final[pathlib.Path] = pathlib.Path("ansible/inventory.ini")


class AnsiblePlaybookMetadata(BaseModel):
    name: str
    description: str
    target: str
    safe: bool
    tags: list[str] = []


class AnsiblePlaybookRegistryEntry(AnsiblePlaybookMetadata):
    path: str


def _ansible_env() -> dict[str, str]:
    """Create a writable environment for Ansible temp files."""
    ANSIBLE_TMP_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    tmp_dir = str(ANSIBLE_TMP_DIR.resolve())
    env["ANSIBLE_LOCAL_TEMP"] = tmp_dir
    env["ANSIBLE_REMOTE_TEMP"] = tmp_dir
    env["LC_ALL"] = "en_US.UTF-8"
    env["LANG"] = "en_US.UTF-8"
    return env


def _decode_output(output: str | bytes) -> str:
    """Normalize subprocess output across real runs and recorded replays."""
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


def normalize_playbook_name(name: str) -> str:
    """Convert a playbook name to a filesystem-safe slug."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    if not normalized:
        raise ValueError("playbook name must contain at least one alphanumeric character")
    return normalized


def build_playbook_path(name: str, directory: pathlib.Path = PLAYBOOKS_DIR) -> pathlib.Path:
    """Resolve a playbook name to a canonical file path."""
    return directory / f"{normalize_playbook_name(name)}.yaml"


def render_metadata_header(metadata: AnsiblePlaybookMetadata) -> str:
    """Render the commented YAML metadata header used by the playbook registry."""
    dumped = yaml.safe_dump(metadata.model_dump(), sort_keys=False).strip()
    return "\n".join(f"# {line}" for line in dumped.splitlines())


def render_playbook_document(metadata: AnsiblePlaybookMetadata, playbook_yaml: str) -> str:
    """Combine the metadata header and YAML body into the stored playbook format."""
    validate_generated_playbook_yaml(playbook_yaml)
    return f"{render_metadata_header(metadata)}\n\n{playbook_yaml.strip()}"


def write_playbook_file(
    metadata: AnsiblePlaybookMetadata,
    playbook_yaml: str,
    directory: pathlib.Path = PLAYBOOKS_DIR,
) -> pathlib.Path:
    """Write an approved draft to disk, rejecting filename collisions."""
    playbook_path = build_playbook_path(metadata.name, directory)
    if playbook_path.exists():
        raise FileExistsError(f"Playbook already exists: {playbook_path}")

    playbook_path.write_text(
        render_playbook_document(metadata, playbook_yaml) + "\n",
        encoding="utf-8",
    )
    return playbook_path


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
    return registry


@tool
def get_ansible_inventory_groups() -> list[str]:
    """Return the supported top-level inventory groups from ansible/inventory.ini."""
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(INVENTORY_PATH, encoding="utf-8")
    return sorted(section for section in parser.sections() if ":" not in section)


@tool
def run_ansible_playbook(playbook_path: str) -> str:
    """Run an Ansible playbook and return its standard output.

    Args:
        playbook_path: Relative or absolute path to the playbook file.

    Returns:
        The decoded stdout from the Ansible process.

    Raises:
        FileNotFoundError: If the provided playbook path does not exist.
        RuntimeError: If ansible-playbook exits with a non-zero status.
    """
    if not pathlib.Path(playbook_path).exists():
        raise FileNotFoundError(f"Playbook not found: {playbook_path}")

    command = ["ansible-playbook", playbook_path]

    try:
        result = subprocess.run(
            command,
            check=True,
            env=_ansible_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return _decode_output(result.stdout)
    except subprocess.CalledProcessError:
        logger.exception("Ansible playbook execution failed")
        raise RuntimeError("Ansible playbook execution failed")
