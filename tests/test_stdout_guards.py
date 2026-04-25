from pathlib import Path


def test_shared_modules_do_not_print_directly() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    disallowed_paths = [
        repo_root / "devops_bot" / "approval.py",
        repo_root / "devops_bot" / "workflow.py",
        repo_root / "devops_bot" / "tools" / "ansible.py",
        repo_root / "devops_bot" / "tools" / "kubernetes.py",
        repo_root / "devops_bot" / "tools" / "playbooks.py",
    ]

    for path in disallowed_paths:
        assert "print(" not in path.read_text(encoding="utf-8"), str(path)
