import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from subprocess_vcr.filters import BaseFilter

REPO_ROOT = Path(__file__).resolve().parent.parent


class DropSubprocessEnvFilter(BaseFilter):
    def before_record(self, interaction: dict[str, object]) -> dict[str, object]:
        kwargs = interaction.get("kwargs")
        if isinstance(kwargs, dict):
            kwargs.pop("env", None)
        return interaction

    def before_playback(self, interaction: dict[str, object]) -> dict[str, object]:
        kwargs = interaction.get("kwargs")
        if isinstance(kwargs, dict):
            kwargs.pop("env", None)
        return interaction


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_remote(url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: subprocess.CalledProcessError | None = None

    while time.monotonic() < deadline:
        try:
            subprocess.run(
                ["git", "ls-remote", url],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            time.sleep(0.1)

    if last_error is None:
        raise RuntimeError(f"Timed out waiting for git remote {url}")

    error_output = last_error.stderr.strip() or last_error.stdout.strip()
    raise RuntimeError(f"Timed out waiting for git remote {url}: {error_output}")


@contextmanager
def _chdir(path: Path) -> Iterator[None]:
    current_dir = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current_dir)


@dataclass(frozen=True)
class GitHttpMockServer:
    root: Path
    port: int

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def repo_url(self, repo_name: str) -> str:
        return f"{self.base_url}/{repo_name}.git"

    def create_bare_repo(self, repo_name: str) -> Path:
        repo_path = self.root / f"{repo_name}.git"
        subprocess.run(
            ["git", "init", "--bare", repo_path.name],
            check=True,
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        subprocess.run(
            ["git", "config", "http.receivepack", "true"],
            check=True,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return repo_path

    def install_post_receive_hook(self, repo_name: str, log_path: Path) -> None:
        hook_path = self.root / f"{repo_name}.git" / "hooks" / "post-receive"
        hook_path.write_text(
            f"#!/bin/sh\ncat >> {log_path}\n",
            encoding="utf-8",
        )
        hook_path.chmod(0o755)


@pytest.fixture
def git_http_mock_server(tmp_path: Path) -> Iterator[GitHttpMockServer]:
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("node is required for git_http_integration tests")

    server_binary = REPO_ROOT / "node_modules" / ".bin" / "git-http-mock-server"
    if not server_binary.exists():
        pytest.skip("npm install must be run before git_http_integration tests")

    server_root = tmp_path / "git-http-remotes"
    server_root.mkdir()
    port = _find_free_port()
    env = os.environ.copy()
    env.update(
        {
            "GIT_HTTP_MOCK_SERVER_PORT": str(port),
            "GIT_HTTP_MOCK_SERVER_ROOT": str(server_root),
        }
    )

    process = subprocess.Popen(
        [str(server_binary)],
        cwd=server_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    server = GitHttpMockServer(root=server_root, port=port)

    try:
        seed_repo = server.create_bare_repo("healthcheck")
        _wait_for_remote(server.repo_url(seed_repo.stem.removesuffix(".git")))
        yield server
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


@pytest.fixture
def git_working_repo_with_remote(
    tmp_path: Path,
    git_http_mock_server: GitHttpMockServer,
) -> Path:
    repo_path = tmp_path / "working-repo"
    repo_path.mkdir()

    with _chdir(repo_path):
        _run_git(["init"], cwd=repo_path)
        _run_git(["config", "user.name", "DevOps Agent Tests"], cwd=repo_path)
        _run_git(["config", "user.email", "devops-agent-tests@example.com"], cwd=repo_path)

        tracked_file = repo_path / "README.md"
        tracked_file.write_text("# Temp Repo\n", encoding="utf-8")
        _run_git(["add", "README.md"], cwd=repo_path)
        _run_git(["commit", "-m", "Initial commit"], cwd=repo_path)

        remote_name = "origin"
        remote_repo_name = "origin"
        git_http_mock_server.create_bare_repo(remote_repo_name)
        _run_git(
            ["remote", "add", remote_name, git_http_mock_server.repo_url(remote_repo_name)],
            cwd=repo_path,
        )

    return repo_path


@pytest.fixture(scope="session")
def subprocess_vcr_config() -> dict[str, list[BaseFilter]]:
    return {"filters": [DropSubprocessEnvFilter()]}


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return {
        "record_mode": "once",
        "filter_headers": ["authorization", "cookie", "set-cookie"],
    }


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return str(Path(str(request.path)).with_name("_http_cassettes"))
