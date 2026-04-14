import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools import (
    ansible_list_inventory_groups,
    ansible_list_playbooks,
    ansible_run_playbook,
    systemd_restart_service,
)


class TestRunAnsiblePlaybook:
    def test_ansible_run_playbook_not_found(self):
        with pytest.raises(ValueError):
            ansible_run_playbook("playbooks/test_playbook.yml")

    @pytest.mark.subprocess_vcr
    def test_run_ansible_playbook_success(self):
        result = ansible_run_playbook("ansible/playbooks/hello-local-test.yaml")

        assert "PLAY RECAP" in result

    def test_ansible_run_playbook_uses_default_output(self, monkeypatch: pytest.MonkeyPatch):
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

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        cast(Any, ansible_run_playbook)("ansible/playbooks/hello-control.yaml")

        assert recorded["args"] == (["ansible-playbook", "ansible/playbooks/hello-control.yaml"],)

    def test_ansible_run_playbook_requires_approval(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "n")
        run_history = RunHistory(prompt="run hello-control")
        token = set_active_run_history(run_history)

        try:
            with pytest.raises(PermissionError, match="Execution not approved"):
                ansible_run_playbook("ansible/playbooks/hello-control.yaml")
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "playbook_execution_declined"

    def test_ansible_run_playbook_failure_includes_stderr(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=4,
                cmd=args[0],
                output=None,
                stderr="inventory parse failed",
            )

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        with pytest.raises(RuntimeError, match="inventory parse failed"):
            ansible_run_playbook("ansible/playbooks/hello-control.yaml")

    def test_ansible_run_playbook_failure_includes_stdout(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=4,
                cmd=args[0],
                output="host unreachable",
                stderr="inventory parse failed",
            )

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        with pytest.raises(
            RuntimeError,
            match=r"inventory parse failed[\s\S]+host unreachable",
        ):
            ansible_run_playbook("ansible/playbooks/hello-control.yaml")

    def test_ansible_run_playbook_failure_includes_ansible_diagnosis(
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

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        with pytest.raises(RuntimeError) as exc_info:
            ansible_run_playbook("ansible/playbooks/hello-control.yaml")

        message = str(exc_info.value)
        assert "Failed task: Validate k3s server service and API health" in message
        assert "Failed host: control" in message
        assert "dict method" in message
        assert "stdout tail:" in message

    def test_ansible_run_playbook_removes_unsupported_locale_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        monkeypatch.setattr(
            "devops_bot.tools.ansible._available_locales",
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

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)
        monkeypatch.setenv("LC_ALL", "C.UTF-8")
        monkeypatch.setenv("LANG", "C.UTF-8")
        monkeypatch.setenv("LC_CTYPE", "C.UTF-8")

        ansible_run_playbook("ansible/playbooks/hello-control.yaml")

        kwargs = cast(dict[str, Any], recorded["kwargs"])
        env = cast(dict[str, str], kwargs["env"])
        assert "LC_ALL" not in env
        assert "LANG" not in env
        assert "LC_CTYPE" not in env

    def test_ansible_run_playbook_loads_dotenv_into_subprocess_environment(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        playbooks_dir = tmp_path / "ansible" / "playbooks"
        playbooks_dir.mkdir(parents=True)
        playbook_path = playbooks_dir / "hello-control.yaml"
        playbook_path.write_text(
            "# name: hello-control\n"
            "# description: Ping the control node group.\n"
            "# target: control\n"
            "# requires_approval: true\n"
            "# tags:\n"
            "#   - connectivity\n"
            "\n"
            "---\n"
            "- name: Hello control\n"
            "  hosts: control\n"
            "  tasks:\n"
            "    - name: Ping control\n"
            "      ansible.builtin.ping:\n",
            encoding="utf-8",
        )
        (tmp_path / ".env").write_text(
            'MINIO_ROOT_USER="dotenv user"\nexport MINIO_ROOT_PASSWORD=dotenv-password\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("devops_bot.tools.ansible.PLAYBOOKS_DIR", Path("ansible/playbooks"))
        monkeypatch.setattr("builtins.input", lambda _: "y")
        monkeypatch.delenv("MINIO_ROOT_USER", raising=False)
        monkeypatch.setenv("MINIO_ROOT_PASSWORD", "os-password")

        recorded: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            recorded["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="PLAY RECAP\n",
                stderr="",
            )

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        ansible_run_playbook("ansible/playbooks/hello-control.yaml")

        kwargs = cast(dict[str, Any], recorded["kwargs"])
        env = cast(dict[str, str], kwargs["env"])
        assert env["MINIO_ROOT_USER"] == "dotenv user"
        assert env["MINIO_ROOT_PASSWORD"] == "os-password"

    def test_ansible_run_playbook_success_records_run_history(
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

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        try:
            ansible_run_playbook("ansible/playbooks/hello-control.yaml")
        finally:
            reset_active_run_history(token)

        event_kinds = [event.kind for event in run_history.session.events]
        assert "playbook_execution_succeeded" in event_kinds

    def test_ansible_run_playbook_failure_records_run_history(
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

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        try:
            with pytest.raises(
                RuntimeError,
                match=r"inventory parse failed[\s\S]+host unreachable",
            ):
                ansible_run_playbook("ansible/playbooks/hello-control.yaml")
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "playbook_execution_failed"
        diagnosis = run_history.session.events[-1].details["failure_diagnosis"]
        assert isinstance(diagnosis, dict)
        assert diagnosis["return_code"] == 4
        assert diagnosis["stderr_tail"] == "inventory parse failed"
        assert diagnosis["stdout_tail"] == "host unreachable"


class TestGetAnsiblePlaybookRegistry:
    def test_ansible_list_playbooks(self):
        registry = ansible_list_playbooks()

        assert isinstance(registry, list)
        assert len(registry) > 0
        registry_by_path = {entry["path"]: entry for entry in registry}
        expected_paths = {
            "ansible/playbooks/display-current-time.yaml",
            "ansible/playbooks/hello-cluster.yaml",
            "ansible/playbooks/hello-control.yaml",
            "ansible/playbooks/hello-local-test.yaml",
            "ansible/playbooks/list-files.yaml",
        }
        assert expected_paths.issubset(registry_by_path)
        assert registry_by_path["ansible/playbooks/hello-cluster.yaml"]["name"] == "hello-cluster"
        assert registry_by_path["ansible/playbooks/hello-cluster.yaml"]["target"] == "cluster"

    def test_ansible_list_playbooks_records_run_history(self) -> None:
        run_history = RunHistory(prompt="inspect registry")
        token = set_active_run_history(run_history)

        try:
            ansible_list_playbooks()
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "playbook_registry_read"


class TestGetAnsibleInventoryGroups:
    def test_ansible_list_inventory_groups(self):
        groups = ansible_list_inventory_groups()

        assert groups == ["cluster", "control"]


class TestSystemdRestartService:
    def test_systemd_restart_service_rejects_non_allowlisted_service(self):
        with pytest.raises(ValueError, match="not allowlisted"):
            systemd_restart_service("ssh")

    def test_systemd_restart_service_requires_approval(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "n")
        run_history = RunHistory(prompt="restart prometheus")
        token = set_active_run_history(run_history)

        try:
            with pytest.raises(PermissionError, match="restart not approved"):
                systemd_restart_service("prometheus")
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "systemd_service_restart_declined"

    def test_systemd_restart_service_runs_systemctl_and_returns_status(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        commands: list[list[str]] = []

        def fake_run(command, *args, **kwargs):
            commands.append(command)
            if command == ["systemctl", "is-active", "prometheus"]:
                stdout = "active\n"
            elif command == ["systemctl", "is-enabled", "prometheus"]:
                stdout = "enabled\n"
            elif command == ["systemctl", "status", "prometheus", "--no-pager", "--lines=20"]:
                stdout = "prometheus.service - Prometheus\n   Active: active (running)\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=stdout, stderr="")

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        result = systemd_restart_service("prometheus")

        assert commands[0] == ["sudo", "-n", "systemctl", "restart", "prometheus"]
        assert result == {
            "service_name": "prometheus",
            "restarted": True,
            "active_state": "active",
            "enabled_state": "enabled",
            "status_summary": "prometheus.service - Prometheus\n   Active: active (running)",
        }

    def test_systemd_restart_service_failure_includes_systemctl_output(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("builtins.input", lambda _: "y")

        def fake_run(command, *args, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=command,
                output="",
                stderr="sudo: a password is required",
            )

        monkeypatch.setattr("devops_bot.tools.ansible.subprocess.run", fake_run)

        with pytest.raises(RuntimeError, match="sudo: a password is required"):
            systemd_restart_service("prometheus")
