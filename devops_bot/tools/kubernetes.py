import subprocess
from typing import Literal

from strands import tool

from ..history import record_event

KubectlOutput = Literal["wide", "yaml", "json"]
HelmOutput = Literal["table", "yaml", "json"]


def _validate_cli_arg(value: str, *, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if normalized.startswith("-"):
        raise ValueError(f"{name} must not start with '-'")
    return normalized


def _run_kubectl(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "kubectl command failed"
        raise RuntimeError(message) from exc
    except OSError as exc:
        raise RuntimeError(f"unable to run kubectl: {exc}") from exc

    return result.stdout.strip()


def _run_helm(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "helm command failed"
        raise RuntimeError(message) from exc
    except OSError as exc:
        raise RuntimeError(f"unable to run helm: {exc}") from exc

    return result.stdout.strip()


@tool
def kubectl_get(
    resource: str,
    name: str | None = None,
    namespace: str | None = None,
    all_namespaces: bool = False,
    output: KubectlOutput = "wide",
) -> str:
    """Run read-only kubectl get against the current local kubeconfig context."""
    normalized_resource = _validate_cli_arg(resource, name="resource")
    if output not in {"wide", "yaml", "json"}:
        raise ValueError("output must be one of: wide, yaml, json")
    if namespace is not None and all_namespaces:
        raise ValueError("namespace and all_namespaces cannot both be set")

    command = ["kubectl", "get", normalized_resource]
    if name is not None:
        command.append(_validate_cli_arg(name, name="name"))
    if namespace is not None:
        command.extend(["--namespace", _validate_cli_arg(namespace, name="namespace")])
    if all_namespaces:
        command.append("--all-namespaces")
    command.extend(["--output", output])

    record_event(
        kind="kubectl_get_started",
        status="started",
        what=f"Started kubectl get for `{normalized_resource}`.",
        why="Inspect Kubernetes state through the local kubeconfig context.",
        details={"command": command, "resource": normalized_resource},
    )
    result = _run_kubectl(command)
    record_event(
        kind="kubectl_get_completed",
        status="completed",
        what=f"Completed kubectl get for `{normalized_resource}`.",
        why="Return Kubernetes state for orchestration decisions.",
        details={"command": command, "output_preview": result},
    )
    return result


@tool
def kubectl_describe(resource: str, name: str, namespace: str | None = None) -> str:
    """Run read-only kubectl describe against the current local kubeconfig context."""
    normalized_resource = _validate_cli_arg(resource, name="resource")
    normalized_name = _validate_cli_arg(name, name="name")
    command = ["kubectl", "describe", normalized_resource, normalized_name]
    if namespace is not None:
        command.extend(["--namespace", _validate_cli_arg(namespace, name="namespace")])

    record_event(
        kind="kubectl_describe_started",
        status="started",
        what=f"Started kubectl describe for `{normalized_resource}/{normalized_name}`.",
        why="Inspect Kubernetes object details through the local kubeconfig context.",
        details={"command": command, "resource": normalized_resource, "name": normalized_name},
    )
    result = _run_kubectl(command)
    record_event(
        kind="kubectl_describe_completed",
        status="completed",
        what=f"Completed kubectl describe for `{normalized_resource}/{normalized_name}`.",
        why="Return Kubernetes object details for orchestration decisions.",
        details={"command": command, "output_preview": result},
    )
    return result


@tool
def kubectl_logs(
    pod: str,
    namespace: str | None = None,
    container: str | None = None,
    tail_lines: int = 200,
) -> str:
    """Read pod logs from the current local kubeconfig context."""
    if tail_lines < 1:
        raise ValueError("tail_lines must be at least 1")

    normalized_pod = _validate_cli_arg(pod, name="pod")
    command = ["kubectl", "logs", normalized_pod, "--tail", str(tail_lines)]
    if namespace is not None:
        command.extend(["--namespace", _validate_cli_arg(namespace, name="namespace")])
    if container is not None:
        command.extend(["--container", _validate_cli_arg(container, name="container")])

    record_event(
        kind="kubectl_logs_started",
        status="started",
        what=f"Started kubectl logs for pod `{normalized_pod}`.",
        why="Inspect Kubernetes pod logs through the local kubeconfig context.",
        details={"command": command, "pod": normalized_pod, "tail_lines": tail_lines},
    )
    result = _run_kubectl(command)
    record_event(
        kind="kubectl_logs_completed",
        status="completed",
        what=f"Completed kubectl logs for pod `{normalized_pod}`.",
        why="Return pod logs for orchestration decisions.",
        details={"command": command, "output_preview": result},
    )
    return result


@tool
def helm_list_releases(
    namespace: str | None = None,
    all_namespaces: bool = False,
    output: HelmOutput = "table",
) -> str:
    """Run read-only helm list against the current local kubeconfig context."""
    if output not in {"table", "yaml", "json"}:
        raise ValueError("output must be one of: table, yaml, json")
    if namespace is not None and all_namespaces:
        raise ValueError("namespace and all_namespaces cannot both be set")

    command = ["helm", "list", "--output", output]
    if namespace is not None:
        command.extend(["--namespace", _validate_cli_arg(namespace, name="namespace")])
    if all_namespaces:
        command.append("--all-namespaces")

    record_event(
        kind="helm_list_releases_started",
        status="started",
        what="Started helm list.",
        why="Inspect Helm releases through the local kubeconfig context.",
        details={"command": command},
    )
    result = _run_helm(command)
    record_event(
        kind="helm_list_releases_completed",
        status="completed",
        what="Completed helm list.",
        why="Return Helm release state for orchestration decisions.",
        details={"command": command, "output_preview": result},
    )
    return result


@tool
def helm_status(release: str, namespace: str | None = None, output: HelmOutput = "table") -> str:
    """Run read-only helm status against the current local kubeconfig context."""
    normalized_release = _validate_cli_arg(release, name="release")
    if output not in {"table", "yaml", "json"}:
        raise ValueError("output must be one of: table, yaml, json")

    command = ["helm", "status", normalized_release, "--output", output]
    if namespace is not None:
        command.extend(["--namespace", _validate_cli_arg(namespace, name="namespace")])

    record_event(
        kind="helm_status_started",
        status="started",
        what=f"Started helm status for release `{normalized_release}`.",
        why="Inspect Helm release details through the local kubeconfig context.",
        details={"command": command, "release": normalized_release},
    )
    result = _run_helm(command)
    record_event(
        kind="helm_status_completed",
        status="completed",
        what=f"Completed helm status for release `{normalized_release}`.",
        why="Return Helm release details for orchestration decisions.",
        details={"command": command, "output_preview": result},
    )
    return result


@tool
def helm_upgrade_install(
    release: str,
    chart: str,
    namespace: str | None = None,
    values_file: str | None = None,
    set_values: list[str] | None = None,
    create_namespace: bool = False,
    wait: bool = True,
) -> str:
    """Run helm upgrade --install after explicit approval."""
    normalized_release = _validate_cli_arg(release, name="release")
    normalized_chart = _validate_cli_arg(chart, name="chart")
    command = ["helm", "upgrade", "--install", normalized_release, normalized_chart]
    if namespace is not None:
        command.extend(["--namespace", _validate_cli_arg(namespace, name="namespace")])
    if values_file is not None:
        command.extend(["--values", _validate_cli_arg(values_file, name="values_file")])
    for set_value in set_values or []:
        command.extend(["--set", _validate_cli_arg(set_value, name="set_values item")])
    if create_namespace:
        command.append("--create-namespace")
    if wait:
        command.append("--wait")

    record_event(
        kind="helm_upgrade_install_requested",
        status="started",
        what=f"Requested helm upgrade --install for release `{normalized_release}`.",
        why="Deploy or update an application through Helm using the local kubeconfig context.",
        details={"command": command, "release": normalized_release, "chart": normalized_chart},
    )
    response = input(f"Run {' '.join(command)}? [y/N]: ").strip().lower()
    if response not in {"y", "yes"}:
        record_event(
            kind="helm_upgrade_install_declined",
            status="declined",
            what=f"Declined helm upgrade --install for release `{normalized_release}`.",
            why="Helm deployment mutates Kubernetes cluster state and requires approval.",
            details={"command": command, "approved": False},
        )
        raise PermissionError(f"Helm deployment not approved for release: {normalized_release}")

    record_event(
        kind="helm_upgrade_install_started",
        status="approved",
        what=f"Started helm upgrade --install for release `{normalized_release}`.",
        why="Approval was granted for the Helm deployment.",
        details={"command": command, "approved": True},
    )
    result = _run_helm(command)
    record_event(
        kind="helm_upgrade_install_completed",
        status="completed",
        what=f"Completed helm upgrade --install for release `{normalized_release}`.",
        why="The Helm deployment command exited successfully.",
        details={"command": command, "output_preview": result},
    )
    return result
