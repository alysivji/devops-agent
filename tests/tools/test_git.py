import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from agent.tools import (
    create_git_branch,
    create_git_commit,
    git_push,
    git_status,
    list_git_commits,
)


@contextmanager
def _chdir(path: Path) -> Iterator[None]:
    current_dir = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current_dir)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    with _chdir(repo_path):
        subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            ["git", "config", "user.name", "DevOps Agent Tests"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "config", "user.email", "devops-agent-tests@example.com"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        tracked_file = repo_path / "README.md"
        tracked_file.write_text("# Temp Repo\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "README.md"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    return repo_path


class TestGitStatus:
    @pytest.mark.subprocess_vcr
    def test_git_status(self, git_repo: Path):
        (git_repo / "README.md").write_text("# Temp Repo\nupdated\n", encoding="utf-8")

        with _chdir(git_repo):
            result = git_status()

        assert result == "M README.md"


class TestListGitCommits:
    @pytest.mark.subprocess_vcr
    def test_list_git_commits(self, git_repo: Path):
        with _chdir(git_repo):
            result = list_git_commits(limit=5)

        assert result.endswith(" Initial commit")

    def test_list_git_commits_rejects_invalid_limit(self):
        with pytest.raises(ValueError):
            list_git_commits(limit=0)


class TestCreateGitCommit:
    @pytest.mark.subprocess_vcr
    def test_create_git_commit_with_staging(self, git_repo: Path):
        (git_repo / "playbook.yml").write_text("---\n- hosts: all\n", encoding="utf-8")

        with _chdir(git_repo):
            result = create_git_commit("Add git tools")

        assert result.endswith(" Add git tools")
        assert (git_repo / "playbook.yml").exists()

    @pytest.mark.parametrize("message", ["   ", ""])
    def test_create_git_commit_rejects_empty_message(self, message: str):
        with pytest.raises(ValueError):
            create_git_commit(message)


class TestGitPush:
    @pytest.mark.git_http_integration
    def test_git_push_uses_current_branch_when_branch_not_provided(
        self,
        git_working_repo_with_remote: Path,
        git_http_mock_server,
    ):
        received_refs_log = git_http_mock_server.root / "origin-received-refs.log"
        git_http_mock_server.install_post_receive_hook("origin", received_refs_log)

        with _chdir(git_working_repo_with_remote):
            subprocess.run(
                ["git", "checkout", "-b", "feature/http-push"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            (git_working_repo_with_remote / "README.md").write_text(
                "# Temp Repo\nupdated via http\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "commit", "-am", "Push over HTTP"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            result = git_push()
        received_refs = received_refs_log.read_text(encoding="utf-8").strip()

        assert result == "Pushed feature/http-push to origin"
        assert received_refs.endswith("refs/heads/feature/http-push")

    @pytest.mark.git_http_integration
    def test_git_push_uses_explicit_remote_and_branch(
        self,
        git_working_repo_with_remote: Path,
        git_http_mock_server,
    ):
        received_refs_log = git_http_mock_server.root / "origin-explicit-received-refs.log"
        git_http_mock_server.install_post_receive_hook("origin", received_refs_log)

        with _chdir(git_working_repo_with_remote):
            subprocess.run(
                ["git", "checkout", "-b", "feature/explicit-http"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            new_file = git_working_repo_with_remote / "playbook.yml"
            new_file.write_text("---\n- hosts: all\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "playbook.yml"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Explicit branch push"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            result = git_push(remote="origin", branch="feature/explicit-http")
        received_refs = received_refs_log.read_text(encoding="utf-8").strip()

        assert result == "Pushed feature/explicit-http to origin"
        assert received_refs.endswith("refs/heads/feature/explicit-http")

    @pytest.mark.git_http_integration
    def test_git_push_surfaces_missing_remote_repo_failure(
        self,
        tmp_path: Path,
        git_http_mock_server,
    ):
        repo_path = tmp_path / "working-repo"
        repo_path.mkdir()

        with _chdir(repo_path):
            subprocess.run(
                ["git", "init"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "DevOps Agent Tests"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "devops-agent-tests@example.com"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            (repo_path / "README.md").write_text("# Temp Repo\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "README.md"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["git", "checkout", "-b", "feature/missing-http"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "origin", git_http_mock_server.repo_url("missing-remote")],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            with pytest.raises(RuntimeError, match="not found|repository|404"):
                git_push()

    @pytest.mark.parametrize("remote", ["", "   "])
    def test_git_push_rejects_empty_remote(self, remote: str):
        with pytest.raises(ValueError):
            git_push(remote=remote)

    @pytest.mark.parametrize("branch", ["", "   "])
    def test_git_push_rejects_empty_branch(self, branch: str):
        with pytest.raises(ValueError):
            git_push(branch=branch)


class TestCreateGitBranch:
    @pytest.mark.subprocess_vcr
    def test_create_git_branch_from_local_base_branch(self, git_repo: Path):
        with _chdir(git_repo):
            subprocess.run(
                ["git", "branch", "local-base"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            result = create_git_branch("feature/test", base_ref="local-base")
            current_branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout.strip()

        assert result == "Created and switched to feature/test from local-base"
        assert current_branch == "feature/test"

    @patch("agent.tools.git.subprocess.run")
    def test_create_git_branch_uses_default_base_ref(self, mock_run: Mock):
        mock_run.return_value = Mock(stdout="", stderr="")

        result = create_git_branch("feature/test")

        assert result == "Created and switched to feature/test from origin/main"
        mock_run.assert_called_once_with(
            ["git", "checkout", "-b", "feature/test", "origin/main"],
            check=True,
            stdout=-1,
            stderr=-1,
            text=True,
        )

    @patch("agent.tools.git.subprocess.run")
    def test_create_git_branch_uses_explicit_base_ref(self, mock_run: Mock):
        mock_run.return_value = Mock(stdout="", stderr="")

        result = create_git_branch("feature/test", base_ref="origin/release")

        assert result == "Created and switched to feature/test from origin/release"
        mock_run.assert_called_once_with(
            ["git", "checkout", "-b", "feature/test", "origin/release"],
            check=True,
            stdout=-1,
            stderr=-1,
            text=True,
        )

    @pytest.mark.parametrize("branch_name", ["", "   "])
    def test_create_git_branch_rejects_empty_branch_name(self, branch_name: str):
        with pytest.raises(ValueError):
            create_git_branch(branch_name)

    @pytest.mark.parametrize("base_ref", ["", "   "])
    def test_create_git_branch_rejects_empty_base_ref(self, base_ref: str):
        with pytest.raises(ValueError):
            create_git_branch("feature/test", base_ref=base_ref)
