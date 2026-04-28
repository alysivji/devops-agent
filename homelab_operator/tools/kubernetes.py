import os
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final, NotRequired, Protocol, TypedDict

import yaml
from strands import tool

from ..agents.helm_chart_editor import EditedHelmChart, EditHelmChartAgent
from ..approval import get_approval
from ..history import record_event
from ..workflow import emit_preview

KUBERNETES_OUTPUT_TAIL_LINES: Final[int] = 80
HELM_CHARTS_DIR: Final[Path] = Path("helm/charts")
DEFAULT_KUBECONFIG: Final[Path] = Path("~/.kube/config")


class HelmChartRegistryEntry(TypedDict):
    name: str
    version: str
    path: str
    description: NotRequired[str]
    app_version: NotRequired[str]
    chart_type: NotRequired[str]


class EditHelmChartResult(TypedDict):
    path: str
    summary: str
    files: list[str]
    written: bool
    lint_passed: bool
    requires_cluster_validation: bool


class KubernetesAccessFixResult(TypedDict):
    source: str
    destination: str
    applied: bool
    verified: bool
    kubectl_cluster_info: str
    helm_list_releases: str


class HelmChartEditor(Protocol):
    def run(
        self,
        *,
        chart_path: Path,
        current_files: dict[str, str],
        requested_change: str,
    ) -> EditedHelmChart: ...


def _confirm_kubernetes_mutation(summary: str) -> bool:
    return get_approval(f"{summary} Proceed? [y/N]: ")


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
            env=_kubernetes_command_env(),
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


def _kubernetes_command_env() -> dict[str, str]:
    env = os.environ.copy()
    kubeconfig = DEFAULT_KUBECONFIG.expanduser()
    if kubeconfig.is_file():
        env["KUBECONFIG"] = str(kubeconfig)
    return env


def _configured_kubeconfig() -> str | None:
    kubeconfig = DEFAULT_KUBECONFIG.expanduser()
    if kubeconfig.is_file():
        return str(kubeconfig)
    return os.environ.get("KUBECONFIG") or None


def _kubectl_command(*args: str) -> list[str]:
    command = ["kubectl"]
    kubeconfig = _configured_kubeconfig()
    if kubeconfig:
        command.extend(["--kubeconfig", kubeconfig])
    command.extend(args)
    return command


def _helm_cluster_command(*args: str) -> list[str]:
    command = ["helm"]
    kubeconfig = _configured_kubeconfig()
    if kubeconfig:
        command.extend(["--kubeconfig", kubeconfig])
    command.extend(args)
    return command


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


def _validate_chart_path(chart_path: str) -> Path:
    path = Path(chart_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Helm chart path must be a relative path inside the repository.")
    if not path.is_dir():
        raise ValueError(f"Helm chart path does not exist: {chart_path}")
    if not (path / "Chart.yaml").is_file():
        raise ValueError(f"Helm chart is missing Chart.yaml: {chart_path}")
    return path


def _read_chart_files(chart_path: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for file_path in sorted(path for path in chart_path.rglob("*") if path.is_file()):
        relative_path = file_path.relative_to(chart_path).as_posix()
        try:
            files[relative_path] = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return files


def _chart_has_dependencies(chart: str) -> bool:
    chart_path = Path(chart)
    chart_yaml_path = chart_path / "Chart.yaml"
    if not chart_yaml_path.is_file():
        return False

    metadata = yaml.safe_load(chart_yaml_path.read_text(encoding="utf-8"))
    return isinstance(metadata, dict) and bool(metadata.get("dependencies"))


@tool
def helm_list_charts() -> list[HelmChartRegistryEntry]:
    """Return repo-owned Helm charts under helm/charts with Chart.yaml metadata."""
    if not HELM_CHARTS_DIR.exists():
        registry: list[HelmChartRegistryEntry] = []
    else:
        registry = [
            _parse_chart_metadata(chart_path)
            for chart_path in sorted(path for path in HELM_CHARTS_DIR.iterdir() if path.is_dir())
            if (chart_path / "Chart.yaml").is_file()
        ]

    record_event(
        kind="helm_chart_registry_read",
        status="completed",
        what="Read the Helm chart registry.",
        why=(
            "Inspect repo-owned Kubernetes application desired state before "
            "creating or editing charts."
        ),
        details={"count": len(registry), "paths": [entry["path"] for entry in registry]},
    )
    return registry


def _parse_chart_metadata(chart_path: Path) -> HelmChartRegistryEntry:
    metadata = yaml.safe_load((chart_path / "Chart.yaml").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"Helm chart metadata must be a mapping: {chart_path / 'Chart.yaml'}")

    name = metadata.get("name")
    version = metadata.get("version")
    if not isinstance(name, str) or not name:
        raise ValueError(f"Helm chart is missing a string name: {chart_path / 'Chart.yaml'}")
    if not isinstance(version, str) or not version:
        raise ValueError(f"Helm chart is missing a string version: {chart_path / 'Chart.yaml'}")

    entry: HelmChartRegistryEntry = {
        "name": name,
        "version": version,
        "path": str(chart_path),
    }
    description = metadata.get("description")
    if isinstance(description, str) and description:
        entry["description"] = description
    app_version = metadata.get("appVersion")
    if isinstance(app_version, str) and app_version:
        entry["app_version"] = app_version
    chart_type = metadata.get("type")
    if isinstance(chart_type, str) and chart_type:
        entry["chart_type"] = chart_type
    return entry


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
def helm_edit_chart(chart_path: str, requested_change: str) -> EditHelmChartResult:
    """Edit files inside an existing Helm chart, then run `helm lint`.

    Args:
        chart_path: Relative path to an existing Helm chart directory.
        requested_change: Natural-language description of the chart edit to make.
    """
    return EditHelmChart().run(chart_path=chart_path, requested_change=requested_change)


class EditHelmChart:
    def __init__(
        self,
        *,
        editor: HelmChartEditor | None = None,
        lint_runner: Callable[[Path], None] | None = None,
    ) -> None:
        self.editor = editor or EditHelmChartAgent()
        self.lint_runner = lint_runner or _helm_lint

    def run(self, *, chart_path: str, requested_change: str) -> EditHelmChartResult:
        target_path = _validate_chart_path(chart_path)
        current_files = _read_chart_files(target_path)
        record_event(
            kind="helm_chart_edit_started",
            status="started",
            what=f"Started local edit for Helm chart `{chart_path}`.",
            why="Edit repo-owned Kubernetes application desired state inside the chart.",
            details={"path": chart_path, "requested_change": requested_change},
        )

        edited = self.editor.run(
            chart_path=target_path,
            current_files=current_files,
            requested_change=requested_change,
        )
        edited_paths = _validate_chart_file_edits(target_path, edited)
        emit_chart_edit_preview(chart_path=target_path, edited=edited)
        record_event(
            kind="helm_chart_edit_preview_presented",
            status="completed",
            what="Presented the Helm chart edit preview.",
            why=(
                "Show the local chart edit summary and changed files before "
                "asking for write approval."
            ),
            details={
                "path": str(target_path),
                "summary": edited.summary,
                "files": [path.as_posix() for path in edited_paths],
                "requires_cluster_validation": edited.requires_cluster_validation,
            },
        )

        if not _confirm_kubernetes_mutation(
            f"Write edited Helm chart files under '{target_path}'."
        ):
            record_event(
                kind="helm_chart_edit_declined",
                status="declined",
                what=f"Declined local edit for Helm chart `{chart_path}`.",
                why="The tool requires explicit confirmation before editing chart files.",
                details={"path": str(target_path), "approved": False},
            )
            return {
                "path": str(target_path),
                "summary": edited.summary,
                "files": [path.as_posix() for path in edited_paths],
                "written": False,
                "lint_passed": False,
                "requires_cluster_validation": edited.requires_cluster_validation,
            }

        for relative_path, file_edit in zip(edited_paths, edited.files, strict=True):
            destination = target_path / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(_normalize_file_content(file_edit.content), encoding="utf-8")

        self.lint_runner(target_path)
        record_event(
            kind="helm_chart_edit_written",
            status="completed",
            what=f"Wrote local edit for Helm chart `{chart_path}`.",
            why="Persist the lint-checked chart edit under the repo-owned chart directory.",
            details={
                "path": str(target_path),
                "approved": True,
                "summary": edited.summary,
                "files": [path.as_posix() for path in edited_paths],
                "lint_passed": True,
                "requires_cluster_validation": edited.requires_cluster_validation,
            },
        )
        return {
            "path": str(target_path),
            "summary": edited.summary,
            "files": [path.as_posix() for path in edited_paths],
            "written": True,
            "lint_passed": True,
            "requires_cluster_validation": edited.requires_cluster_validation,
        }


def _validate_chart_file_edits(chart_path: Path, edited: EditedHelmChart) -> list[Path]:
    relative_paths: list[Path] = []
    resolved_chart_path = chart_path.resolve()
    for file_edit in edited.files:
        relative_path = Path(file_edit.path)
        destination = (chart_path / relative_path).resolve()
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"edited chart file path must stay inside the chart: {file_edit.path}")
        if resolved_chart_path not in destination.parents:
            raise ValueError(f"edited chart file path must stay inside the chart: {file_edit.path}")
        relative_paths.append(relative_path)
    if not relative_paths:
        raise ValueError("edited chart must include at least one file")
    return relative_paths


def _helm_lint(chart_path: Path) -> None:
    _run_command(
        ["helm", "lint", str(chart_path)],
        event_kind="helm_lint_chart",
        what=f"Linted Helm chart `{chart_path}`.",
        why="Validate the edited chart before reporting the local edit as complete.",
    )


def emit_chart_edit_preview(*, chart_path: Path, edited: EditedHelmChart) -> None:
    files = "\n".join(f"  - {file_edit.path}" for file_edit in edited.files)
    body = "\n".join(
        [
            f"Chart: {chart_path}",
            f"Summary: {edited.summary}",
            f"Requires cluster validation: {str(edited.requires_cluster_validation).lower()}",
            "Files:",
            files,
        ]
    )
    emit_preview(
        preview_type="helm_chart_edit",
        title=f"Helm chart edit preview for {chart_path}",
        body=body,
        metadata={
            "path": str(chart_path),
            "files": [file_edit.path for file_edit in edited.files],
            "requires_cluster_validation": edited.requires_cluster_validation,
        },
    )


def _normalize_file_content(content: str) -> str:
    return f"{content.rstrip()}\n"


@tool
def kubernetes_fix_access(
    source: str = "/etc/rancher/k3s/k3s.yaml",
    destination: str = "~/.kube/config",
) -> KubernetesAccessFixResult:
    """Repair local Kubernetes client access by installing a readable k3s kubeconfig.

    Args:
        source: Source k3s kubeconfig path to copy from.
        destination: Destination kubeconfig path for the current user.
    """
    source_path = Path(source)
    if source_path != Path("/etc/rancher/k3s/k3s.yaml"):
        raise ValueError("kubernetes_fix_access only supports the k3s admin kubeconfig source.")

    destination_path = Path(destination).expanduser()
    if not destination_path.is_absolute() or ".." in destination_path.parts:
        raise ValueError("destination must resolve to an absolute path without parent traversal.")

    user_id = subprocess.run(
        ["id", "-un"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    group_id = subprocess.run(
        ["id", "-gn"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()

    summary = f"Install readable kubeconfig at '{destination_path}' from '{source_path}'."
    record_event(
        kind="kubernetes_access_repair_requested",
        status="started",
        what=summary,
        why="Repair local kubeconfig access before retrying Helm/Kubernetes workflow tools.",
        details={"source": str(source_path), "destination": str(destination_path)},
    )
    if not _confirm_kubernetes_mutation(summary):
        record_event(
            kind="kubernetes_access_repair_declined",
            status="declined",
            what=summary,
            why="The tool requires explicit confirmation before writing kubeconfig.",
            details={
                "source": str(source_path),
                "destination": str(destination_path),
                "approved": False,
            },
        )
        return {
            "source": str(source_path),
            "destination": str(destination_path),
            "applied": False,
            "verified": False,
            "kubectl_cluster_info": "",
            "helm_list_releases": "",
        }

    _run_command(
        [
            "sudo",
            "install",
            "-D",
            "-m",
            "600",
            "-o",
            user_id,
            "-g",
            group_id,
            str(source_path),
            str(destination_path),
        ],
        event_kind="kubernetes_access_repair",
        what=summary,
        why="Copy the k3s admin kubeconfig to a user-readable kubeconfig for local tools.",
    )
    kubectl_output = _run_command(
        ["kubectl", "--kubeconfig", str(destination_path), "cluster-info"],
        event_kind="kubernetes_access_repair_verify_kubectl",
        what="Verified Kubernetes API access with kubectl.",
        why="Confirm the repaired kubeconfig can reach the cluster API.",
    )
    helm_output = _run_command(
        ["helm", "--kubeconfig", str(destination_path), "list", "--all-namespaces"],
        event_kind="kubernetes_access_repair_verify_helm",
        what="Verified Helm API access.",
        why="Confirm Helm can reach the cluster API with the repaired kubeconfig.",
    )

    return {
        "source": str(source_path),
        "destination": str(destination_path),
        "applied": True,
        "verified": True,
        "kubectl_cluster_info": kubectl_output,
        "helm_list_releases": helm_output,
    }


@tool
def helm_list_releases(namespace: str | None = None, all_namespaces: bool = True) -> str:
    """List Helm releases from the configured Kubernetes cluster."""
    command = _helm_cluster_command("list", "-o", "json")
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
    command = _helm_cluster_command("status", release, "--namespace", namespace, "-o", "json")
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
    command = _helm_cluster_command(
        "upgrade",
        "--install",
        release,
        chart,
        "--namespace",
        namespace,
        "--wait",
        "--timeout",
        timeout,
    )
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
    if _chart_has_dependencies(chart):
        _run_command(
            ["helm", "dependency", "build", chart],
            event_kind="helm_dependency_build",
            what=f"Built Helm chart dependencies for `{chart}`.",
            why="Populate local chart dependencies before installing a repo-owned wrapper chart.",
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
    command = _kubectl_command("get", resource, "-o", "wide")
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
    command = _kubectl_command(
        "rollout",
        "status",
        resource,
        "--namespace",
        namespace,
        f"--timeout={timeout}",
    )
    return _run_command(
        command,
        event_kind="kubectl_rollout_status",
        what=f"Checked rollout status for `{resource}`.",
        why="Validate application workload readiness through the Kubernetes API.",
    )
