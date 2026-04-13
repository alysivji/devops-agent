import subprocess
from typing import Literal

from strands import tool

from ..history import record_event

KubectlOutput = Literal["wide", "yaml", "json"]


def _validate_kubectl_arg(value: str, *, name: str) -> str:
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


@tool
def kubectl_get(
    resource: str,
    name: str | None = None,
    namespace: str | None = None,
    all_namespaces: bool = False,
    output: KubectlOutput = "wide",
) -> str:
    """Run read-only kubectl get against the current local kubeconfig context."""
    normalized_resource = _validate_kubectl_arg(resource, name="resource")
    if output not in {"wide", "yaml", "json"}:
        raise ValueError("output must be one of: wide, yaml, json")
    if namespace is not None and all_namespaces:
        raise ValueError("namespace and all_namespaces cannot both be set")

    command = ["kubectl", "get", normalized_resource]
    if name is not None:
        command.append(_validate_kubectl_arg(name, name="name"))
    if namespace is not None:
        command.extend(["--namespace", _validate_kubectl_arg(namespace, name="namespace")])
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
    normalized_resource = _validate_kubectl_arg(resource, name="resource")
    normalized_name = _validate_kubectl_arg(name, name="name")
    command = ["kubectl", "describe", normalized_resource, normalized_name]
    if namespace is not None:
        command.extend(["--namespace", _validate_kubectl_arg(namespace, name="namespace")])

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

    normalized_pod = _validate_kubectl_arg(pod, name="pod")
    command = ["kubectl", "logs", normalized_pod, "--tail", str(tail_lines)]
    if namespace is not None:
        command.extend(["--namespace", _validate_kubectl_arg(namespace, name="namespace")])
    if container is not None:
        command.extend(["--container", _validate_kubectl_arg(container, name="container")])

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
