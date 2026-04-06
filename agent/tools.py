import pathlib
import subprocess

from strands import tool

@tool
def list_ansible_playbooks() -> list[str]:
    """List all Ansible playbooks in the current directory.

    Returns:
        A list of playbook paths relative to the current working directory.
    """
    playbooks_dir = pathlib.Path("ansible/playbooks")
    playbooks = []
    for file in playbooks_dir.iterdir():
        if file.is_file() and file.suffix in [".yaml", ".yml"]:
            playbooks.append(str(file))
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

    command = [
        "ansible-playbook",
        playbook_path
    ]

    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode('utf-8')
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Ansible playbook execution failed: {e.stderr.decode('utf-8')}")
