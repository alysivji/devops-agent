import subprocess
from typing import Any, cast

import pytest

from devops_bot.history import RunHistory, reset_active_run_history, set_active_run_history
from devops_bot.tools import (
    helm_list_releases,
    helm_status,
    helm_upgrade_install,
    kubectl_describe,
    kubectl_get,
    kubectl_logs,
)


def test_kubectl_get_builds_read_only_command(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="pod/a\n", stderr="")

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

    result = kubectl_get("pods", namespace="default")

    assert result == "pod/a"
    assert recorded["args"] == (
        ["kubectl", "get", "pods", "--namespace", "default", "--output", "wide"],
    )


def test_kubectl_get_rejects_namespace_with_all_namespaces() -> None:
    with pytest.raises(ValueError, match="cannot both be set"):
        kubectl_get("pods", namespace="default", all_namespaces=True)


@pytest.mark.parametrize("resource", ["", "   ", "--raw"])
def test_kubectl_get_rejects_unsafe_resource(resource: str) -> None:
    with pytest.raises(ValueError):
        kubectl_get(resource)


def test_kubectl_get_rejects_unknown_output() -> None:
    with pytest.raises(ValueError, match="output must be one of"):
        cast(Any, kubectl_get)("pods", output="name")


def test_kubectl_describe_builds_command(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="Name: app\n",
            stderr="",
        )

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

    result = kubectl_describe("deployment", "app", namespace="apps")

    assert result == "Name: app"
    assert recorded["args"] == (
        ["kubectl", "describe", "deployment", "app", "--namespace", "apps"],
    )


def test_kubectl_logs_builds_command(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ready\n", stderr="")

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

    result = kubectl_logs("app-pod", namespace="apps", container="api", tail_lines=50)

    assert result == "ready"
    assert recorded["args"] == (
        [
            "kubectl",
            "logs",
            "app-pod",
            "--tail",
            "50",
            "--namespace",
            "apps",
            "--container",
            "api",
        ],
    )


def test_kubectl_logs_rejects_invalid_tail_lines() -> None:
    with pytest.raises(ValueError, match="tail_lines"):
        kubectl_logs("app-pod", tail_lines=0)


def test_kubectl_failure_surfaces_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args[0],
            output="",
            stderr="pod not found",
        )

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="pod not found"):
        kubectl_describe("pod", "missing")


def test_kubectl_get_records_run_history(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="pod/a\n", stderr="")

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)
    run_history = RunHistory(prompt="inspect pods")
    token = set_active_run_history(run_history)

    try:
        kubectl_get("pods")
    finally:
        reset_active_run_history(token)

    event_kinds = [event.kind for event in run_history.session.events]
    assert "kubectl_get_started" in event_kinds
    assert "kubectl_get_completed" in event_kinds


def test_helm_list_releases_builds_read_only_command(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="NAME\napp\n",
            stderr="",
        )

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

    result = helm_list_releases(namespace="apps", output="json")

    assert result == "NAME\napp"
    assert recorded["args"] == (["helm", "list", "--output", "json", "--namespace", "apps"],)


def test_helm_list_releases_rejects_namespace_with_all_namespaces() -> None:
    with pytest.raises(ValueError, match="cannot both be set"):
        helm_list_releases(namespace="apps", all_namespaces=True)


def test_helm_status_builds_read_only_command(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="deployed\n",
            stderr="",
        )

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

    result = helm_status("app", namespace="apps")

    assert result == "deployed"
    assert recorded["args"] == (
        ["helm", "status", "app", "--output", "table", "--namespace", "apps"],
    )


def test_helm_upgrade_install_requires_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "n")

    with pytest.raises(PermissionError, match="not approved"):
        helm_upgrade_install("app", "oci://registry.example/app", namespace="apps")


def test_helm_upgrade_install_builds_approved_command(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr("builtins.input", lambda _: "y")

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="Release app upgraded\n",
            stderr="",
        )

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)

    result = helm_upgrade_install(
        "app",
        "oci://registry.example/app",
        namespace="apps",
        values_file="deploy/values.yaml",
        set_values=["image.tag=1.2.3"],
        create_namespace=True,
    )

    assert result == "Release app upgraded"
    assert recorded["args"] == (
        [
            "helm",
            "upgrade",
            "--install",
            "app",
            "oci://registry.example/app",
            "--namespace",
            "apps",
            "--values",
            "deploy/values.yaml",
            "--set",
            "image.tag=1.2.3",
            "--create-namespace",
            "--wait",
        ],
    )


def test_helm_upgrade_install_records_run_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "y")

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="done\n", stderr="")

    monkeypatch.setattr("devops_bot.tools.kubernetes.subprocess.run", fake_run)
    run_history = RunHistory(prompt="deploy app")
    token = set_active_run_history(run_history)

    try:
        helm_upgrade_install("app", "oci://registry.example/app", wait=False)
    finally:
        reset_active_run_history(token)

    event_kinds = [event.kind for event in run_history.session.events]
    assert "helm_upgrade_install_requested" in event_kinds
    assert "helm_upgrade_install_started" in event_kinds
    assert "helm_upgrade_install_completed" in event_kinds
