import subprocess
from pathlib import Path

import pytest

from agent.tools import create_git_commit, git_status, list_git_commits


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    monkeypatch.chdir(repo_path)

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

        result = git_status()

        assert result == "M README.md"


class TestListGitCommits:
    @pytest.mark.subprocess_vcr
    def test_list_git_commits(self, git_repo: Path):
        _ = git_repo

        result = list_git_commits(limit=5)

        assert result.endswith(" Initial commit")

    def test_list_git_commits_rejects_invalid_limit(self):
        with pytest.raises(ValueError):
            list_git_commits(limit=0)


class TestCreateGitCommit:
    @pytest.mark.subprocess_vcr
    def test_create_git_commit_with_staging(self, git_repo: Path):
        (git_repo / "playbook.yml").write_text("---\n- hosts: all\n", encoding="utf-8")

        result = create_git_commit("Add git tools")

        assert result.endswith(" Add git tools")
        assert (git_repo / "playbook.yml").exists()

    @pytest.mark.parametrize("message", ["   ", ""])
    def test_create_git_commit_rejects_empty_message(self, message: str):
        with pytest.raises(ValueError):
            create_git_commit(message)
