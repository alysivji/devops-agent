import pathlib
import subprocess


def run_ansible_playbook(playbook_path):
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
