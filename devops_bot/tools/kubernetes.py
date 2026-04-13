import re
import subprocess
import time
from pathlib import Path
from typing import Final

from strands import tool

from ..history import record_event

KUBERNETES_OUTPUT_TAIL_LINES: Final[int] = 80
HELM_CHARTS_DIR: Final[Path] = Path("charts")


def _confirm_kubernetes_mutation(summary: str) -> bool:
    response = input(f"{summary} Proceed? [y/N]: ").strip().lower()
    return response in {"y", "yes"}


def _run_command(command: list[str], *, event_kind: str, what: str, why: str) -> str:
    started_at = time.monotonic()
    record_event(
        kind=f"{event_kind}_started",
        status="started",
        what=what,
        why=why,
        details={"command": command},
    )
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        elapsed_seconds = round(time.monotonic() - started_at, 3)
        stdout = (exc.stdout or "").strip()
        stderr = (exc.stderr or "").strip()
        record_event(
            kind=f"{event_kind}_failed",
            status="failed",
            what=f"{what} failed.",
            why=(
                "Capture the command, output tails, and return code for "
                "Kubernetes workflow troubleshooting."
            ),
            details={
                "command": command,
                "elapsed_seconds": elapsed_seconds,
                "return_code": exc.returncode,
                "stdout_tail": _tail_lines(stdout, KUBERNETES_OUTPUT_TAIL_LINES),
                "stderr_tail": _tail_lines(stderr, KUBERNETES_OUTPUT_TAIL_LINES),
            },
        )
        details = "\n".join(part for part in (stderr, stdout) if part)
        if details:
            raise RuntimeError(f"Kubernetes workflow command failed:\n{details}") from exc
        raise RuntimeError("Kubernetes workflow command failed") from exc

    elapsed_seconds = round(time.monotonic() - started_at, 3)
    stdout = result.stdout or ""
    record_event(
        kind=f"{event_kind}_succeeded",
        status="completed",
        what=f"{what} completed.",
        why=(
            "Capture a compact command summary after the Kubernetes workflow command exits cleanly."
        ),
        details={
            "command": command,
            "elapsed_seconds": elapsed_seconds,
            "stdout_summary": _tail_lines(stdout, 20),
        },
    )
    return stdout


def _tail_lines(output: str, line_count: int) -> str:
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return "\n".join(lines[-line_count:])


def _build_chart_path(name: str, directory: str) -> Path:
    if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", name):
        raise ValueError(
            "Helm chart name must use lowercase letters, numbers, and hyphens, "
            "and must start and end with an alphanumeric character."
        )

    chart_dir = Path(directory)
    if chart_dir.is_absolute() or ".." in chart_dir.parts:
        raise ValueError("Helm chart directory must be a relative path inside the repository.")

    return chart_dir / name


@tool
def helm_create_chart(name: str, directory: str = str(HELM_CHARTS_DIR)) -> str:
    """Create a new Helm chart scaffold under a repository directory.

    Args:
        name: Helm chart name using lowercase letters, numbers, and hyphens.
        directory: Relative repository directory that will contain the chart.
    """
    chart_path = _build_chart_path(name, directory)
    if chart_path.exists():
        raise ValueError(f"Helm chart already exists: {chart_path}")

    summary = f"Create Helm chart scaffold at '{chart_path}'."
    record_event(
        kind="helm_chart_creation_requested",
        status="started",
        what=summary,
        why=(
            "Create repo-owned Kubernetes application desired state instead of "
            "a generated Ansible wrapper."
        ),
        details={"name": name, "directory": directory, "path": str(chart_path)},
    )
    if not _confirm_kubernetes_mutation(summary):
        record_event(
            kind="helm_chart_creation_declined",
            status="declined",
            what=summary,
            why="The tool requires explicit confirmation before writing a new chart scaffold.",
            details={
                "name": name,
                "directory": directory,
                "path": str(chart_path),
                "approved": False,
            },
        )
        raise PermissionError(f"Helm chart creation not approved: {chart_path}")

    record_event(
        kind="helm_chart_creation_approved",
        status="approved",
        what=summary,
        why="The Helm chart scaffold write was explicitly approved.",
        details={
            "name": name,
            "directory": directory,
            "path": str(chart_path),
            "approved": True,
        },
    )
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    output = _run_command(
        ["helm", "create", str(chart_path)],
        event_kind="helm_create_chart",
        what=summary,
        why="Create a repo-owned Helm chart scaffold for Kubernetes application desired state.",
    )
    if output.strip():
        return output
    return f"Created Helm chart at {chart_path}"


@tool
def helm_list_releases(namespace: str | None = None, all_namespaces: bool = True) -> str:
    """List Helm releases from the configured Kubernetes cluster."""
    command = ["helm", "list", "-o", "json"]
    if all_namespaces:
        command.append("--all-namespaces")
    elif namespace:
        command.extend(["--namespace", namespace])

    return _run_command(
        command,
        event_kind="helm_list_releases",
        what="Listed Helm releases.",
        why=(
            "Inspect current Kubernetes application workload state before "
            "choosing a deployment action."
        ),
    )


@tool
def helm_status(release: str, namespace: str = "default") -> str:
    """Return Helm status for a release in the configured Kubernetes cluster."""
    command = ["helm", "status", release, "--namespace", namespace, "-o", "json"]
    return _run_command(
        command,
        event_kind="helm_status",
        what=f"Checked Helm status for release `{release}`.",
        why="Validate the release-level state through Helm before or after a deployment action.",
    )


@tool
def helm_upgrade_install(
    release: str,
    chart: str,
    namespace: str = "default",
    repo_url: str | None = None,
    version: str | None = None,
    timeout: str = "5m",
    create_namespace: bool = True,
) -> str:
    """Install or upgrade a Helm release, then wait for Helm to validate it.

    Args:
        release: Helm release name.
        chart: Chart name or reference, such as `nginx` or `bitnami/nginx`.
        namespace: Kubernetes namespace for the release.
        repo_url: Optional chart repository URL passed via `helm --repo`.
        version: Optional chart version constraint.
        timeout: Helm wait timeout, such as `5m`.
        create_namespace: Whether Helm should create the namespace if needed.
    """
    command = [
        "helm",
        "upgrade",
        "--install",
        release,
        chart,
        "--namespace",
        namespace,
        "--wait",
        "--timeout",
        timeout,
    ]
    if create_namespace:
        command.append("--create-namespace")
    if repo_url:
        command.extend(["--repo", repo_url])
    if version:
        command.extend(["--version", version])

    summary = f"Install or upgrade Helm release '{release}' in namespace '{namespace}'."
    record_event(
        kind="helm_release_mutation_requested",
        status="started",
        what=summary,
        why="Helm install/upgrade changes Kubernetes cluster workload state and requires approval.",
        details={"release": release, "chart": chart, "namespace": namespace, "command": command},
    )
    if not _confirm_kubernetes_mutation(summary):
        record_event(
            kind="helm_release_mutation_declined",
            status="declined",
            what=summary,
            why=(
                "The tool requires explicit confirmation before changing Kubernetes workload state."
            ),
            details={
                "release": release,
                "chart": chart,
                "namespace": namespace,
                "approved": False,
            },
        )
        raise PermissionError(f"Helm install/upgrade not approved for release: {release}")

    record_event(
        kind="helm_release_mutation_approved",
        status="approved",
        what=summary,
        why="The Helm install/upgrade was explicitly approved.",
        details={"release": release, "chart": chart, "namespace": namespace, "approved": True},
    )
    return _run_command(
        command,
        event_kind="helm_upgrade_install",
        what=summary,
        why="Apply the requested application workload through Helm instead of host-level Ansible.",
    )


@tool
def kubectl_get(resource: str, namespace: str | None = None) -> str:
    """Get Kubernetes resources from the configured cluster."""
    command = ["kubectl", "get", resource, "-o", "wide"]
    if namespace:
        command.extend(["--namespace", namespace])

    return _run_command(
        command,
        event_kind="kubectl_get",
        what=f"Got Kubernetes resource `{resource}`.",
        why="Inspect Kubernetes workload state through the cluster API.",
    )


@tool
def kubectl_rollout_status(
    resource: str,
    namespace: str = "default",
    timeout: str = "120s",
) -> str:
    """Validate rollout status for a Kubernetes workload resource."""
    command = [
        "kubectl",
        "rollout",
        "status",
        resource,
        "--namespace",
        namespace,
        f"--timeout={timeout}",
    ]
    return _run_command(
        command,
        event_kind="kubectl_rollout_status",
        what=f"Checked rollout status for `{resource}`.",
        why="Validate application workload readiness through the Kubernetes API.",
    )
