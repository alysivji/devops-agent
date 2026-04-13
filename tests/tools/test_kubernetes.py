import subprocess
from typing import Any

import pytest

from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools import (
    helm_create_chart,
    helm_list_releases,
    helm_status,
    helm_upgrade_install,
    kubectl_get,
    kubectl_rollout_status,
)


class TestHelmCreateChart:
    def test_helm_create_chart_requires_approval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "n")
        run_history = RunHistory(prompt="create an nginx chart")
        token = set_active_run_history(run_history)

        try:
            with pytest.raises(PermissionError, match="Helm chart creation not approved"):
                helm_create_chart("nginx")
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "helm_chart_creation_declined"

    def test_helm_create_chart_runs_helm_create_after_approval(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        recorded: dict[str, object] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="Creating charts/nginx\n",
                stderr="",
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        result = helm_create_chart("nginx")

        assert result == "Creating charts/nginx\n"
        assert recorded["args"] == (["helm", "create", "charts/nginx"],)
        assert (tmp_path / "charts").is_dir()

    @pytest.mark.parametrize("name", ["Nginx", "bad/name", "-nginx", "nginx-"])
    def test_helm_create_chart_rejects_invalid_names(self, name: str) -> None:
        with pytest.raises(ValueError, match="Helm chart name"):
            helm_create_chart(name)

    @pytest.mark.parametrize("directory", ["/tmp/charts", "../charts"])
    def test_helm_create_chart_rejects_external_directories(self, directory: str) -> None:
        with pytest.raises(ValueError, match="relative path"):
            helm_create_chart("nginx", directory=directory)


class TestHelmListReleases:
    def test_helm_list_releases_defaults_to_all_namespaces(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: dict[str, object] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="[]\n", stderr="")

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        result = helm_list_releases()

        assert result == "[]\n"
        assert recorded["args"] == (["helm", "list", "-o", "json", "--all-namespaces"],)

    def test_helm_list_releases_can_target_namespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded: dict[str, object] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="[]\n", stderr="")

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        helm_list_releases(namespace="apps", all_namespaces=False)

        assert recorded["args"] == (["helm", "list", "-o", "json", "--namespace", "apps"],)


class TestHelmStatus:
    def test_helm_status_uses_json_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded: dict[str, object] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout='{"info":{}}\n', stderr=""
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        helm_status("nginx", namespace="apps")

        assert recorded["args"] == (
            ["helm", "status", "nginx", "--namespace", "apps", "-o", "json"],
        )


class TestHelmUpgradeInstall:
    def test_helm_upgrade_install_requires_approval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "n")
        run_history = RunHistory(prompt="set up nginx with helm")
        token = set_active_run_history(run_history)

        try:
            with pytest.raises(PermissionError, match="Helm install/upgrade not approved"):
                helm_upgrade_install(
                    release="nginx",
                    chart="nginx",
                    namespace="apps",
                    repo_url="https://charts.bitnami.com/bitnami",
                )
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "helm_release_mutation_declined"

    def test_helm_upgrade_install_builds_upgrade_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "y")
        recorded: dict[str, object] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="Release upgraded\n",
                stderr="",
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        result = helm_upgrade_install(
            release="nginx",
            chart="nginx",
            namespace="apps",
            repo_url="https://charts.bitnami.com/bitnami",
            version="19.0.0",
            timeout="10m",
        )

        assert result == "Release upgraded\n"
        assert recorded["args"] == (
            [
                "helm",
                "upgrade",
                "--install",
                "nginx",
                "nginx",
                "--namespace",
                "apps",
                "--wait",
                "--timeout",
                "10m",
                "--create-namespace",
                "--repo",
                "https://charts.bitnami.com/bitnami",
                "--version",
                "19.0.0",
            ],
        )

    def test_helm_upgrade_install_surfaces_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "y")

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=args[0],
                output="",
                stderr="cluster unreachable",
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        with pytest.raises(RuntimeError, match="cluster unreachable"):
            helm_upgrade_install(release="nginx", chart="nginx")


class TestKubectlGet:
    def test_kubectl_get_builds_namespace_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded: dict[str, object] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="pods\n", stderr=""
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        kubectl_get("pods", namespace="apps")

        assert recorded["args"] == (
            ["kubectl", "get", "pods", "-o", "wide", "--namespace", "apps"],
        )


class TestKubectlRolloutStatus:
    def test_kubectl_rollout_status_builds_timeout_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: dict[str, object] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="deployment successfully rolled out\n",
                stderr="",
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        kubectl_rollout_status("deployment/nginx", namespace="apps", timeout="300s")

        assert recorded["args"] == (
            [
                "kubectl",
                "rollout",
                "status",
                "deployment/nginx",
                "--namespace",
                "apps",
                "--timeout=300s",
            ],
        )
