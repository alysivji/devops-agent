import logging
import os
import pathlib
import subprocess
from typing import Final

from strands import tool

logger = logging.getLogger(__name__)

ANSIBLE_TMP_DIR: Final[pathlib.Path] = pathlib.Path(".ansible/tmp")


def _ansible_env() -> dict[str, str]:
    """Create a writable environment for Ansible temp files."""
    ANSIBLE_TMP_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    tmp_dir = str(ANSIBLE_TMP_DIR.resolve())
    env["ANSIBLE_LOCAL_TEMP"] = tmp_dir
    env["ANSIBLE_REMOTE_TEMP"] = tmp_dir
    return env


def _decode_output(output: str | bytes) -> str:
    """Normalize subprocess output across real runs and recorded replays."""
    if isinstance(output, bytes):
        return output.decode("utf-8")
    return output


@tool
def list_ansible_playbooks() -> list[str]:
    """List all Ansible playbooks in the current directory.

    Returns:
        A list of playbook paths relative to the current working directory.
    """
    playbooks_dir = pathlib.Path("ansible/playbooks")
    playbooks = [
        str(file)
        for file in sorted(playbooks_dir.iterdir())
        if file.is_file() and file.suffix in [".yaml", ".yml"]
    ]
    return playbooks


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
