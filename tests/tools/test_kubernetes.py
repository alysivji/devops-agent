import subprocess
from pathlib import Path
from typing import Any

import pytest

from devops_bot.agents.helm_chart_editor import EditedHelmChart, HelmChartFileEdit
from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools import (
    helm_create_chart,
    helm_edit_chart,
    helm_list_releases,
    helm_status,
    helm_upgrade_install,
    kubectl_get,
    kubectl_rollout_status,
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
