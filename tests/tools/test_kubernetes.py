import subprocess
from pathlib import Path
from typing import Any

import pytest

from devops_bot.agents.helm_chart_editor import EditedHelmChart, HelmChartFileEdit
from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools import (
    helm_create_chart,
    helm_edit_chart,
    helm_list_charts,
    helm_list_releases,
    helm_status,
    helm_upgrade_install,
    kubectl_get,
    kubectl_rollout_status,
    kubernetes_fix_access,
)
from devops_bot.tools.kubernetes import EditHelmChart


class StubChartEditor:
    def __init__(self, edited: EditedHelmChart) -> None:
        self.edited = edited
        self.requests: list[tuple[Path, dict[str, str], str]] = []

    def run(
        self,
        *,
        chart_path: Path,
        current_files: dict[str, str],
        requested_change: str,
    ) -> EditedHelmChart:
        self.requests.append((chart_path, current_files, requested_change))
        return self.edited


def _write_minimal_chart(chart_path: Path) -> None:
    chart_path.mkdir(parents=True)
    (chart_path / "Chart.yaml").write_text(
        "apiVersion: v2\nname: nginx\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    (chart_path / "values.yaml").write_text(
        "replicaCount: 1\n",
        encoding="utf-8",
    )


class TestHelmCreateChart:
    def test_helm_create_chart_requires_approval(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
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
        recorded: dict[str, Any] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="Creating helm/charts/nginx\n",
                stderr="",
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        result = helm_create_chart("nginx")

        assert result == "Creating helm/charts/nginx\n"
        assert recorded["args"] == (["helm", "create", "helm/charts/nginx"],)
        assert (tmp_path / "helm" / "charts").is_dir()

    @pytest.mark.parametrize("name", ["Nginx", "bad/name", "-nginx", "nginx-"])
    def test_helm_create_chart_rejects_invalid_names(self, name: str) -> None:
        with pytest.raises(ValueError, match="Helm chart name"):
            helm_create_chart(name)

    @pytest.mark.parametrize("directory", ["/tmp/charts", "../charts"])
    def test_helm_create_chart_rejects_external_directories(self, directory: str) -> None:
        with pytest.raises(ValueError, match="relative path"):
            helm_create_chart("nginx", directory=directory)


class TestHelmEditChart:
    def test_helm_edit_chart_records_approved_write(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        chart_path = tmp_path / "charts" / "nginx"
        _write_minimal_chart(chart_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        linted: list[Path] = []

        editor = StubChartEditor(
            EditedHelmChart(
                files=[
                    HelmChartFileEdit(path="values.yaml", content="replicaCount: 2\n"),
                ],
                summary="Raised nginx replica count.",
                requires_cluster_validation=True,
            )
        )
        tool = EditHelmChart(editor=editor, lint_runner=linted.append)
        run_history = RunHistory(prompt="scale nginx chart")
        token = set_active_run_history(run_history)

        try:
            result = tool.run(
                chart_path="charts/nginx",
                requested_change="Set replica count to 2.",
            )
        finally:
            reset_active_run_history(token)

        assert result == {
            "path": "charts/nginx",
            "summary": "Raised nginx replica count.",
            "files": ["values.yaml"],
            "written": True,
            "lint_passed": True,
            "requires_cluster_validation": True,
        }
        assert (chart_path / "values.yaml").read_text(encoding="utf-8") == "replicaCount: 2\n"
        assert linted == [Path("charts/nginx")]
        assert editor.requests[0][1]["values.yaml"] == "replicaCount: 1\n"
        event_kinds = [event.kind for event in run_history.session.events]
        assert "helm_chart_edit_preview_presented" in event_kinds
        assert "helm_chart_edit_written" in event_kinds

    def test_helm_edit_chart_skips_binary_chart_dependencies(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        chart_path = tmp_path / "charts" / "nginx"
        _write_minimal_chart(chart_path)
        dependency_path = chart_path / "charts" / "nginx-22.6.12.tgz"
        dependency_path.parent.mkdir()
        dependency_path.write_bytes(b"\x1f\x8b\x08\x00binary helm dependency")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("builtins.input", lambda _: "n")

        editor = StubChartEditor(
            EditedHelmChart(
                files=[
                    HelmChartFileEdit(path="values.yaml", content="replicaCount: 2\n"),
                ],
                summary="Raised nginx replica count.",
                requires_cluster_validation=True,
            )
        )
        tool = EditHelmChart(editor=editor, lint_runner=lambda _: None)

        result = tool.run(
            chart_path="charts/nginx",
            requested_change="Set replica count to 2.",
        )

        assert result["written"] is False
        current_files = editor.requests[0][1]
        assert current_files["Chart.yaml"] == "apiVersion: v2\nname: nginx\nversion: 0.1.0\n"
        assert current_files["values.yaml"] == "replicaCount: 1\n"
        assert "charts/nginx-22.6.12.tgz" not in current_files

    def test_helm_edit_chart_records_declined_write(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        chart_path = tmp_path / "charts" / "nginx"
        _write_minimal_chart(chart_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("builtins.input", lambda _: "n")

        tool = EditHelmChart(
            editor=StubChartEditor(
                EditedHelmChart(
                    files=[HelmChartFileEdit(path="values.yaml", content="replicaCount: 2\n")],
                    summary="Raised nginx replica count.",
                    requires_cluster_validation=True,
                )
            ),
            lint_runner=lambda _: None,
        )

        result = tool.run(
            chart_path="charts/nginx",
            requested_change="Set replica count to 2.",
        )

        assert result["written"] is False
        assert result["lint_passed"] is False
        assert (chart_path / "values.yaml").read_text(encoding="utf-8") == "replicaCount: 1\n"

    def test_helm_edit_chart_rejects_file_escape(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        chart_path = tmp_path / "charts" / "nginx"
        _write_minimal_chart(chart_path)
        monkeypatch.chdir(tmp_path)

        tool = EditHelmChart(
            editor=StubChartEditor(
                EditedHelmChart(
                    files=[HelmChartFileEdit(path="../escape.yaml", content="bad\n")],
                    summary="Attempted escape.",
                    requires_cluster_validation=False,
                )
            ),
            lint_runner=lambda _: None,
        )

        with pytest.raises(ValueError, match="inside the chart"):
            tool.run(
                chart_path="charts/nginx",
                requested_change="Write outside the chart.",
            )

    def test_helm_edit_chart_tool_returns_plain_dict(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        chart_path = tmp_path / "charts" / "nginx"
        _write_minimal_chart(chart_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        monkeypatch.setattr(
            "devops_bot.tools.kubernetes.EditHelmChartAgent",
            lambda: StubChartEditor(
                EditedHelmChart(
                    files=[HelmChartFileEdit(path="values.yaml", content="replicaCount: 2\n")],
                    summary="Raised nginx replica count.",
                    requires_cluster_validation=True,
                )
            ),
        )
        monkeypatch.setattr("devops_bot.tools.kubernetes._helm_lint", lambda _: None)

        result = helm_edit_chart("charts/nginx", "Set replica count to 2.")

        assert result["files"] == ["values.yaml"]
        assert result["written"] is True
        assert result["lint_passed"] is True


class TestHelmListCharts:
    def test_helm_list_charts_reads_chart_yaml_metadata(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        chart_path = tmp_path / "helm" / "charts" / "nginx"
        chart_path.mkdir(parents=True)
        (chart_path / "Chart.yaml").write_text(
            "apiVersion: v2\n"
            "name: nginx\n"
            "description: Test nginx chart.\n"
            "type: application\n"
            "version: 0.1.0\n"
            "appVersion: 1.27.0\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        registry = helm_list_charts()

        assert registry == [
            {
                "name": "nginx",
                "version": "0.1.0",
                "path": "helm/charts/nginx",
                "description": "Test nginx chart.",
                "app_version": "1.27.0",
                "chart_type": "application",
            }
        ]

    def test_helm_list_charts_ignores_directories_without_chart_metadata(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "helm" / "charts" / "README.d").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        assert helm_list_charts() == []


class TestHelmListReleases:
    def test_helm_list_releases_defaults_to_all_namespaces(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: dict[str, Any] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="[]\n", stderr="")

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        result = helm_list_releases()

        assert result == "[]\n"
        assert recorded["args"] == (["helm", "list", "-o", "json", "--all-namespaces"],)

    def test_helm_list_releases_can_target_namespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded: dict[str, Any] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["args"] = args
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="[]\n", stderr="")

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        helm_list_releases(namespace="apps", all_namespaces=False)

        assert recorded["args"] == (["helm", "list", "-o", "json", "--namespace", "apps"],)

    def test_helm_list_releases_prefers_repaired_user_kubeconfig(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        kubeconfig = tmp_path / "config"
        kubeconfig.write_text("apiVersion: v1\n", encoding="utf-8")
        monkeypatch.setattr("devops_bot.tools.kubernetes.DEFAULT_KUBECONFIG", kubeconfig)
        monkeypatch.setenv("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")
        recorded: dict[str, Any] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["env"] = kwargs["env"]
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="[]\n", stderr="")

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        helm_list_releases()

        assert recorded["env"]["KUBECONFIG"] == str(kubeconfig)


class TestKubernetesFixAccess:
    def test_kubernetes_fix_access_requires_approval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "n")
        run_history = RunHistory(prompt="fix kubernetes access")
        token = set_active_run_history(run_history)

        try:
            result = kubernetes_fix_access()
        finally:
            reset_active_run_history(token)

        assert result == {
            "source": "/etc/rancher/k3s/k3s.yaml",
            "destination": str(Path("~/.kube/config").expanduser()),
            "applied": False,
            "verified": False,
            "kubectl_cluster_info": "",
            "helm_list_releases": "",
        }
        assert run_history.session.events[-1].kind == "kubernetes_access_repair_declined"

    def test_kubernetes_fix_access_copies_and_verifies_after_approval(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "y")
        commands: list[list[str]] = []

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            command = args[0]
            commands.append(command)
            if command == ["id", "-un"]:
                stdout = "ansible\n"
            elif command == ["id", "-gn"]:
                stdout = "ansible\n"
            elif command[0:2] == ["kubectl", "--kubeconfig"]:
                stdout = "Kubernetes control plane is running\n"
            elif command[0:2] == ["helm", "--kubeconfig"]:
                stdout = "NAME NAMESPACE REVISION\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=stdout, stderr="")

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        result = kubernetes_fix_access()

        assert commands == [
            ["id", "-un"],
            ["id", "-gn"],
            [
                "sudo",
                "install",
                "-D",
                "-m",
                "600",
                "-o",
                "ansible",
                "-g",
                "ansible",
                "/etc/rancher/k3s/k3s.yaml",
                str(Path("~/.kube/config").expanduser()),
            ],
            [
                "kubectl",
                "--kubeconfig",
                str(Path("~/.kube/config").expanduser()),
                "cluster-info",
            ],
            [
                "helm",
                "--kubeconfig",
                str(Path("~/.kube/config").expanduser()),
                "list",
                "--all-namespaces",
            ],
        ]
        assert result["applied"] is True
        assert result["verified"] is True
        assert result["kubectl_cluster_info"] == "Kubernetes control plane is running\n"

    def test_kubernetes_fix_access_rejects_non_k3s_source(self) -> None:
        with pytest.raises(ValueError, match="k3s admin kubeconfig"):
            kubernetes_fix_access(source="/tmp/config")


class TestHelmStatus:
    def test_helm_status_uses_json_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded: dict[str, Any] = {}

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

    def test_helm_upgrade_install_builds_dependencies_for_local_chart(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        chart_path = tmp_path / "helm" / "charts" / "nginx"
        chart_path.mkdir(parents=True)
        (chart_path / "Chart.yaml").write_text(
            "apiVersion: v2\n"
            "name: nginx\n"
            "version: 0.1.0\n"
            "dependencies:\n"
            "  - name: nginx\n"
            "    alias: upstream\n"
            "    version: '>=0.0.0'\n"
            "    repository: oci://registry-1.docker.io/bitnamicharts\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("builtins.input", lambda _: "y")
        commands: list[list[str]] = []

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            commands.append(args[0])
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="ok\n",
                stderr="",
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        helm_upgrade_install(release="nginx", chart=str(chart_path))

        assert commands == [
            ["helm", "dependency", "build", str(chart_path)],
            [
                "helm",
                "upgrade",
                "--install",
                "nginx",
                str(chart_path),
                "--namespace",
                "default",
                "--wait",
                "--timeout",
                "5m",
                "--create-namespace",
            ],
        ]


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

    def test_kubectl_get_prefers_repaired_user_kubeconfig(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        kubeconfig = tmp_path / "config"
        kubeconfig.write_text("apiVersion: v1\n", encoding="utf-8")
        monkeypatch.setattr("devops_bot.tools.kubernetes.DEFAULT_KUBECONFIG", kubeconfig)
        monkeypatch.setenv("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")
        recorded: dict[str, Any] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded["env"] = kwargs["env"]
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="pods\n", stderr=""
            )

        monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

        kubectl_get("pods")

        assert recorded["env"]["KUBECONFIG"] == str(kubeconfig)


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
