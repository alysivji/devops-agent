import subprocess

from strands import tool


def _run_git_command(args: list[str]) -> str:
    """Run a git command and normalize failures into RuntimeError."""
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "Git command failed"
        raise RuntimeError(message) from exc

    return result.stdout.strip()


@tool
def git_status() -> str:
    """Return the current repository status in porcelain format."""
    return _run_git_command(["status", "--short"])


@tool
def list_git_commits(limit: int = 10) -> str:
    """Return the most recent commits as one line each."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    return _run_git_command(
        [
            "log",
            f"--max-count={limit}",
            "--pretty=format:%H %s",
        ]
    )


@tool
def create_git_commit(message: str) -> str:
    """Stage all changes, create a git commit, and return the new commit summary."""
    if not message.strip():
        raise ValueError("message must not be empty")

    _run_git_command(["add", "-A"])
    _run_git_command(["commit", "-m", message])
    return _run_git_command(["log", "-1", "--pretty=format:%H %s"])
