import subprocess
from typing import Any, cast

import pytest

from agent.tools import (
    get_ansible_inventory_groups,
    get_ansible_playbook_registry,
    run_ansible_playbook,
)


class TestRunAnsiblePlaybook:
    def test_run_ansible_playbook_not_found(self):
        with pytest.raises(ValueError):
            run_ansible_playbook("playbooks/test_playbook.yml")

    @pytest.mark.subprocess_vcr
    def test_run_ansible_playbook_success(self):
        result = run_ansible_playbook("ansible/playbooks/hello-local-test.yaml")

        assert "PLAY RECAP" in result

    def test_run_ansible_playbook_verbose(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")

        recorded: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            recorded["args"] = args
            recorded["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="PLAY RECAP\n",
                stderr="",
            )

        monkeypatch.setattr("agent.tools.ansible.subprocess.run", fake_run)

        cast(Any, run_ansible_playbook)("ansible/playbooks/hello-control.yaml", True)

        assert recorded["args"] == (
            ["ansible-playbook", "ansible/playbooks/hello-control.yaml", "-vv"],
        )

    def test_run_ansible_playbook_requires_approval(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "n")

        with pytest.raises(PermissionError, match="Execution not approved"):
            run_ansible_playbook("ansible/playbooks/hello-control.yaml")

    def test_run_ansible_playbook_failure_includes_stderr(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=4,
                cmd=args[0],
                output=None,
                stderr="inventory parse failed",
            )

        monkeypatch.setattr("agent.tools.ansible.subprocess.run", fake_run)

        with pytest.raises(RuntimeError, match="inventory parse failed"):
            run_ansible_playbook("ansible/playbooks/hello-control.yaml")

    def test_run_ansible_playbook_failure_includes_stdout(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=4,
                cmd=args[0],
                output="host unreachable",
                stderr="inventory parse failed",
            )

        monkeypatch.setattr("agent.tools.ansible.subprocess.run", fake_run)

        with pytest.raises(RuntimeError, match=r"inventory parse failed\s+host unreachable"):
            run_ansible_playbook("ansible/playbooks/hello-control.yaml")

    def test_run_ansible_playbook_removes_unsupported_locale_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        monkeypatch.setattr(
            "agent.tools.ansible._available_locales",
            lambda: {"C", "POSIX", "en_US.UTF-8"},
        )

        recorded: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            recorded["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="PLAY RECAP\n",
                stderr="",
            )

        monkeypatch.setattr("agent.tools.ansible.subprocess.run", fake_run)
        monkeypatch.setenv("LC_ALL", "C.UTF-8")
        monkeypatch.setenv("LANG", "C.UTF-8")
        monkeypatch.setenv("LC_CTYPE", "C.UTF-8")

        run_ansible_playbook("ansible/playbooks/hello-control.yaml")

        kwargs = cast(dict[str, Any], recorded["kwargs"])
        env = cast(dict[str, str], kwargs["env"])
        assert "LC_ALL" not in env
        assert "LANG" not in env
        assert "LC_CTYPE" not in env


class TestGetAnsiblePlaybookRegistry:
    def test_get_ansible_playbook_registry(self):
        registry = get_ansible_playbook_registry()

        assert isinstance(registry, list)
        assert len(registry) > 0
        assert registry == [
            {
                "description": "Ping the cluster node group.",
                "name": "hello-cluster",
                "path": "ansible/playbooks/hello-cluster.yaml",
                "requires_approval": True,
                "tags": ["connectivity", "cluster"],
                "target": "cluster",
            },
            {
                "description": "Ping the control node group.",
                "name": "hello-control",
                "path": "ansible/playbooks/hello-control.yaml",
                "requires_approval": True,
                "tags": ["connectivity", "control"],
                "target": "control",
            },
            {
                "description": "Ping the local control node without privilege escalation.",
                "name": "hello-local-test",
                "path": "ansible/playbooks/hello-local-test.yaml",
                "requires_approval": False,
                "tags": ["connectivity", "test"],
                "target": "control",
            },
            {
                "description": (
                    "Lists files in the root directory on both control and "
                    "cluster nodes and displays the output."
                ),
                "name": "list_files",
                "path": "ansible/playbooks/list-files.yaml",
                "requires_approval": False,
                "tags": ["file_management", "listing", "debugging"],
                "target": "both",
            },
        ]


class TestGetAnsibleInventoryGroups:
    def test_get_ansible_inventory_groups(self):
        groups = get_ansible_inventory_groups()

        assert groups == ["cluster", "control"]
