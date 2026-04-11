import subprocess
from typing import Any, cast

import pytest

from agent.run_history import RunHistory, reset_active_run_history, set_active_run_history
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

    def test_run_ansible_playbook_uses_verbose_output(self, monkeypatch: pytest.MonkeyPatch):
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

        cast(Any, run_ansible_playbook)("ansible/playbooks/hello-control.yaml")

        assert recorded["args"] == (
            ["ansible-playbook", "ansible/playbooks/hello-control.yaml", "-vv"],
        )

    def test_run_ansible_playbook_requires_approval(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "n")
        run_history = RunHistory(prompt="run hello-control")
        token = set_active_run_history(run_history)

        try:
            with pytest.raises(PermissionError, match="Execution not approved"):
                run_ansible_playbook("ansible/playbooks/hello-control.yaml")
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "playbook_execution_declined"

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

        with pytest.raises(
            RuntimeError,
            match=r"inventory parse failed[\s\S]+host unreachable",
        ):
            run_ansible_playbook("ansible/playbooks/hello-control.yaml")

    def test_run_ansible_playbook_failure_includes_ansible_diagnosis(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "y")

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=2,
                cmd=args[0],
                output=(
                    "TASK [Validate k3s server service and API health] ********\n"
                    "fatal: [control]: FAILED! => {\n"
                    '    "msg": "The conditional check '
                    "`(k3s_server_nodes_json.stdout | from_json).items | length >= 1` "
                    'failed. object of type builtin_function_or_method has no len()"\n'
                    "}\n"
                    "PLAY RECAP\n"
                    "control : ok=8 changed=0 unreachable=0 failed=1\n"
                ),
                stderr="",
            )

        monkeypatch.setattr("agent.tools.ansible.subprocess.run", fake_run)

        with pytest.raises(RuntimeError) as exc_info:
            run_ansible_playbook("ansible/playbooks/hello-control.yaml")

        message = str(exc_info.value)
        assert "Failed task: Validate k3s server service and API health" in message
        assert "Failed host: control" in message
        assert "dict method" in message
        assert "stdout tail:" in message

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

    def test_run_ansible_playbook_success_records_run_history(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "y")
        run_history = RunHistory(prompt="run hello-control")
        token = set_active_run_history(run_history)

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="PLAY RECAP\ncontrol : ok=1 changed=0 failed=0\n",
                stderr="",
            )

        monkeypatch.setattr("agent.tools.ansible.subprocess.run", fake_run)

        try:
            run_ansible_playbook("ansible/playbooks/hello-control.yaml")
        finally:
            reset_active_run_history(token)

        event_kinds = [event.kind for event in run_history.session.events]
        assert "playbook_execution_succeeded" in event_kinds

    def test_run_ansible_playbook_failure_records_run_history(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "y")
        run_history = RunHistory(prompt="run hello-control")
        token = set_active_run_history(run_history)

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=4,
                cmd=args[0],
                output="host unreachable",
                stderr="inventory parse failed",
            )

        monkeypatch.setattr("agent.tools.ansible.subprocess.run", fake_run)

        try:
            with pytest.raises(
                RuntimeError,
                match=r"inventory parse failed[\s\S]+host unreachable",
            ):
                run_ansible_playbook("ansible/playbooks/hello-control.yaml")
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "playbook_execution_failed"
        diagnosis = run_history.session.events[-1].details["failure_diagnosis"]
        assert isinstance(diagnosis, dict)
        assert diagnosis["return_code"] == 4
        assert diagnosis["stderr_tail"] == "inventory parse failed"
        assert diagnosis["stdout_tail"] == "host unreachable"


class TestGetAnsiblePlaybookRegistry:
    def test_get_ansible_playbook_registry(self):
        registry = get_ansible_playbook_registry()

        assert isinstance(registry, list)
        assert len(registry) > 0
        assert registry == [
            {
                "description": "Retrieve and display the current time on all servers",
                "name": "display_current_time",
                "path": "ansible/playbooks/display-current-time.yaml",
                "requires_approval": False,
                "tags": ["time", "debug", "info"],
                "target": "both",
            },
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

    def test_get_ansible_playbook_registry_records_run_history(self) -> None:
        run_history = RunHistory(prompt="inspect registry")
        token = set_active_run_history(run_history)

        try:
            get_ansible_playbook_registry()
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "playbook_registry_read"


class TestGetAnsibleInventoryGroups:
    def test_get_ansible_inventory_groups(self):
        groups = get_ansible_inventory_groups()

        assert groups == ["cluster", "control"]
