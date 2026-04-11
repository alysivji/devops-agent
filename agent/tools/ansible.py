import configparser
import logging
import os
import pathlib
import re
import subprocess
import tempfile
import time
import unicodedata
from functools import lru_cache
from typing import Final, Literal, NotRequired, TypedDict

import yaml
from pydantic import BaseModel, ValidationError
from strands import tool

from ..run_history import record_event

logger = logging.getLogger(__name__)

ANSIBLE_TMP_DIR: Final[pathlib.Path] = pathlib.Path(".ansible/tmp")
PLAYBOOKS_DIR: Final[pathlib.Path] = pathlib.Path("ansible/playbooks")
INVENTORY_PATH: Final[pathlib.Path] = pathlib.Path("ansible/inventory.ini")
ANSIBLE_OUTPUT_TAIL_LINES: Final[int] = 80
ANSIBLE_TASK_PATTERN: Final[re.Pattern[str]] = re.compile(r"^TASK \[(?P<task>.+?)]\s+\*+")
ANSIBLE_FATAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^fatal: \[(?P<host>[^]]+)]: FAILED! =>(?P<details>.*)"
)


class AnsiblePlaybookMetadata(BaseModel):
    name: str
    description: str
    target: Literal["control", "cluster", "both"]
    requires_approval: bool
    tags: list[str] = []


class AnsiblePlaybookRegistryEntry(AnsiblePlaybookMetadata):
    path: str


class AnsiblePlaybookRegistryEntryDict(TypedDict):
    name: str
    description: str
    target: Literal["control", "cluster", "both"]
    requires_approval: bool
    tags: list[str]
    path: str


class AnsibleFailureDiagnosis(TypedDict):
    return_code: int
    failed_task: NotRequired[str]
    failed_host: NotRequired[str]
    failure_message: NotRequired[str]
    likely_causes: list[str]
    stderr_tail: str
    stdout_tail: str


def _serialize_registry_entry(
    entry: AnsiblePlaybookRegistryEntry,
) -> AnsiblePlaybookRegistryEntryDict:
    return {
        "name": entry.name,
        "description": entry.description,
        "target": entry.target,
        "requires_approval": entry.requires_approval,
        "tags": entry.tags,
        "path": entry.path,
    }


def _confirm_playbook_execution(entry: AnsiblePlaybookRegistryEntry) -> bool:
    response = input(f"Run playbook '{entry.name}' at {entry.path}? [y/N]: ").strip().lower()
    return response in {"y", "yes"}


def _ansible_env() -> dict[str, str]:
    """Create a writable environment for Ansible temp files."""
    ANSIBLE_TMP_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["ANSIBLE_LOCAL_TEMP"] = str(ANSIBLE_TMP_DIR.resolve())
    _remove_unsupported_locale_vars(env)
    return env


@lru_cache(maxsize=1)
def _available_locales() -> set[str]:
    """Return locales available on this host for subprocess validation."""
    try:
        result = subprocess.run(
            ["locale", "-a"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return set()

    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _remove_unsupported_locale_vars(env: dict[str, str]) -> None:
    """Drop locale env vars whose values are not available on this host."""
    available = _available_locales()
    if not available:
        return

    for key in ("LC_ALL", "LANG", "LC_CTYPE"):
        value = env.get(key)
        if value and value not in available:
            env.pop(key, None)


def _decode_output(output: str | bytes) -> str:
    """Normalize subprocess output across real runs and recorded replays."""
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8")
    return output


def _parse_playbook_metadata(playbook_path: pathlib.Path) -> AnsiblePlaybookRegistryEntry:
    metadata_lines: list[str] = []

    with playbook_path.open(encoding="utf-8") as playbook_file:
        for line in playbook_file:
            if line.startswith("#"):
                metadata_lines.append(line.removeprefix("#"))
                continue
            if metadata_lines:
                break

    if not metadata_lines:
        raise ValueError(f"Playbook is missing metadata header: {playbook_path}")

    metadata = yaml.safe_load("".join(metadata_lines))
    if not isinstance(metadata, dict):
        raise ValueError(f"Playbook metadata must be a mapping: {playbook_path}")

    try:
        validated = AnsiblePlaybookMetadata.model_validate(metadata)
    except ValidationError as exc:
        raise ValueError(f"Invalid playbook metadata for {playbook_path}: {exc}") from exc

    return AnsiblePlaybookRegistryEntry(path=str(playbook_path), **validated.model_dump())


def _get_registry_entry_by_path(playbook_path: str) -> AnsiblePlaybookRegistryEntry:
    for entry in get_ansible_playbook_registry():
        path = entry["path"]
        if path == playbook_path:
            return AnsiblePlaybookRegistryEntry.model_validate(entry)
    raise ValueError(f"Playbook path is not in the registry: {playbook_path}")


def check_ansible_playbook_syntax(playbook_yaml: str) -> None:
    """Validate rendered playbook YAML with ansible-playbook --syntax-check."""
    ANSIBLE_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=ANSIBLE_TMP_DIR,
        encoding="utf-8",
        suffix=".yaml",
    ) as playbook_file:
        playbook_file.write(playbook_yaml)
        playbook_path = pathlib.Path(playbook_file.name)

    command = ["ansible-playbook", "--syntax-check", str(playbook_path)]
    try:
        subprocess.run(
            command,
            check=True,
            env=_ansible_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stdout = _decode_output(exc.stdout).strip()
        stderr = _decode_output(exc.stderr).strip()
        details = "\n".join(part for part in (stderr, stdout) if part)
        if details:
            raise ValueError(f"generated playbook failed ansible syntax-check:\n{details}") from exc
        raise ValueError("generated playbook failed ansible syntax-check") from exc
    except OSError as exc:
        raise ValueError(f"unable to run ansible-playbook syntax-check: {exc}") from exc
    finally:
        playbook_path.unlink(missing_ok=True)


def normalize_playbook_name(name: str) -> str:
    """Convert a playbook name to a filesystem-safe slug."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    if not normalized:
        raise ValueError("playbook name must contain at least one alphanumeric character")
    return normalized


@tool
def get_ansible_inventory_groups() -> list[str]:
    """Return the supported top-level inventory groups from ansible/inventory.ini."""
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(INVENTORY_PATH, encoding="utf-8")
    groups = sorted(section for section in parser.sections() if ":" not in section)
    record_event(
        kind="inventory_groups_read",
        status="completed",
        what="Read supported inventory groups.",
        why="Playbook generation uses the inventory groups to target control, cluster, or both.",
        details={"groups": groups},
    )
    return groups


@tool
def get_ansible_playbook_registry() -> list[AnsiblePlaybookRegistryEntryDict]:
    """Return the Ansible playbook registry with validated metadata.

    Returns:
        A list of playbook metadata dictionaries, including the playbook path.
    """
    registry = [
        _serialize_registry_entry(_parse_playbook_metadata(file))
        for file in sorted(PLAYBOOKS_DIR.iterdir())
        if file.is_file() and file.suffix in [".yaml", ".yml"]
    ]
    record_event(
        kind="playbook_registry_read",
        status="completed",
        what="Read the playbook registry.",
        why="Inspect existing automation before creating or executing a playbook.",
        details={"count": len(registry), "paths": [str(entry["path"]) for entry in registry]},
    )
    return registry


@tool
def run_ansible_playbook(playbook_path: str) -> str:
    """Run a validated Ansible playbook and return its standard output.

    Args:
        playbook_path: Relative path to a playbook file in the validated registry.

    Returns:
        The decoded stdout from the Ansible process.

    Raises:
        ValueError: If the provided playbook path is not in the validated registry.
        PermissionError: If execution was not approved for a gated playbook.
        RuntimeError: If ansible-playbook exits with a non-zero status.
    """
    entry = _get_registry_entry_by_path(playbook_path)
    record_event(
        kind="playbook_execution_requested",
        status="started",
        what=f"Requested execution for playbook `{playbook_path}`.",
        why="The orchestrator selected this existing playbook from the validated registry.",
        details={"playbook_path": playbook_path, "requires_approval": entry.requires_approval},
    )

    if entry.requires_approval and not _confirm_playbook_execution(entry):
        record_event(
            kind="playbook_execution_declined",
            status="declined",
            what=f"Declined execution for playbook `{playbook_path}`.",
            why="This playbook requires explicit human approval before execution.",
            details={"playbook_path": playbook_path, "approved": False},
        )
        raise PermissionError(f"Execution not approved for playbook: {playbook_path}")

    record_event(
        kind="playbook_execution_approved",
        status="approved",
        what=f"Approved execution for playbook `{playbook_path}`.",
        why=(
            "Execution can proceed once the registry entry is approved or "
            "does not require approval."
        ),
        details={"playbook_path": playbook_path, "approved": True},
    )
    command = ["ansible-playbook", playbook_path]
    record_event(
        kind="playbook_execution_started",
        status="started",
        what=f"Started playbook execution for `{playbook_path}`.",
        why="Run the selected playbook through ansible-playbook.",
        details={"playbook_path": playbook_path, "command": command},
    )
    started_at = time.monotonic()

    try:
        result = subprocess.run(
            command,
            check=True,
            env=_ansible_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout = _decode_output(result.stdout)
        elapsed_seconds = round(time.monotonic() - started_at, 3)
        record_event(
            kind="playbook_execution_succeeded",
            status="completed",
            what=f"Playbook `{playbook_path}` completed successfully.",
            why="Capture a compact execution summary after ansible-playbook exits cleanly.",
            details={
                "playbook_path": playbook_path,
                "command": command,
                "elapsed_seconds": elapsed_seconds,
                "stdout_summary": _summarize_ansible_output(stdout),
            },
        )
        return stdout
    except subprocess.CalledProcessError as exc:
        logger.exception("Ansible playbook execution failed")
        stdout = _decode_output(exc.stdout).strip()
        stderr = _decode_output(exc.stderr).strip()
        diagnosis = _diagnose_ansible_failure(exc, stdout=stdout, stderr=stderr)
        elapsed_seconds = round(time.monotonic() - started_at, 3)
        record_event(
            kind="playbook_execution_failed",
            status="failed",
            what=f"Playbook `{playbook_path}` failed.",
            why=_summarize_ansible_failure(diagnosis),
            details={
                "playbook_path": playbook_path,
                "command": command,
                "elapsed_seconds": elapsed_seconds,
                "stdout_summary": _summarize_ansible_output(stdout),
                "stderr_summary": _summarize_ansible_output(stderr),
                "failure_diagnosis": diagnosis,
            },
        )
        details = _format_ansible_failure(diagnosis)
        if details:
            raise RuntimeError(f"Ansible playbook execution failed:\n{details}") from exc
        raise RuntimeError("Ansible playbook execution failed") from exc


def _summarize_ansible_output(output: str) -> str:
    normalized = output.strip()
    if not normalized:
        return ""

    play_recap_index = normalized.rfind("PLAY RECAP")
    if play_recap_index != -1:
        return normalized[play_recap_index:]

    lines = [line for line in normalized.splitlines() if line.strip()]
    return "\n".join(lines[-10:])


def _diagnose_ansible_failure(
    exc: subprocess.CalledProcessError,
    *,
    stdout: str,
    stderr: str,
) -> AnsibleFailureDiagnosis:
    combined_output = "\n".join(part for part in (stdout, stderr) if part)
    diagnosis: AnsibleFailureDiagnosis = {
        "return_code": exc.returncode,
        "likely_causes": _detect_likely_ansible_causes(combined_output),
        "stderr_tail": _tail_lines(stderr, ANSIBLE_OUTPUT_TAIL_LINES),
        "stdout_tail": _tail_lines(stdout, ANSIBLE_OUTPUT_TAIL_LINES),
    }

    failed_task = _extract_failed_task(stdout)
    if failed_task is not None:
        diagnosis["failed_task"] = failed_task

    failed_host = _extract_failed_host(stdout)
    if failed_host is not None:
        diagnosis["failed_host"] = failed_host

    failure_message = _extract_failure_message(combined_output)
    if failure_message is not None:
        diagnosis["failure_message"] = failure_message

    return diagnosis


def _extract_failed_task(output: str) -> str | None:
    current_task: str | None = None
    failed_task: str | None = None

    for line in output.splitlines():
        task_match = ANSIBLE_TASK_PATTERN.match(line)
        if task_match is not None:
            current_task = task_match.group("task").strip()
            continue

        if ANSIBLE_FATAL_PATTERN.match(line):
            failed_task = current_task

    return failed_task


def _extract_failed_host(output: str) -> str | None:
    failed_host: str | None = None
    for line in output.splitlines():
        fatal_match = ANSIBLE_FATAL_PATTERN.match(line)
        if fatal_match is not None:
            failed_host = fatal_match.group("host").strip()
    return failed_host


def _extract_failure_message(output: str) -> str | None:
    for pattern in (
        r'"msg":\s*"(?P<message>(?:[^"\\]|\\.)*)"',
        r"msg:\s*(?P<message>.+)",
        r"ERROR!\s*(?P<message>.+)",
    ):
        match = re.search(pattern, output)
        if match is not None:
            return match.group("message").strip()

    for line in output.splitlines():
        if "FAILED!" in line:
            return line.strip()

    return None


def _detect_likely_ansible_causes(output: str) -> list[str]:
    normalized = output.lower()
    causes: list[str] = []

    if ".items" in output and "from_json" in output:
        causes.append(
            "A Jinja expression appears to use dot lookup for a JSON key named `items`; "
            "use bracket lookup such as `parsed_json['items']` to avoid the dict method."
        )

    if "builtin_function_or_method" in normalized and "length" in normalized:
        causes.append(
            "A Jinja `length` filter may be running against a Python method instead of a list "
            "or dictionary value."
        )

    if "ansibleundefinedvariable" in normalized or " is undefined" in normalized:
        causes.append(
            "A Jinja expression references an undefined variable or nested key; default the "
            "parent value before indexing into it."
        )

    if "template error while templating string" in normalized:
        causes.append(
            "Ansible failed while rendering a template expression, so a rescue/debug task may "
            "be masking the original failure."
        )

    return causes


def _format_ansible_failure(diagnosis: AnsibleFailureDiagnosis) -> str:
    sections: list[str] = [f"Return code: {diagnosis['return_code']}"]

    failed_task = diagnosis.get("failed_task")
    if failed_task:
        sections.append(f"Failed task: {failed_task}")

    failed_host = diagnosis.get("failed_host")
    if failed_host:
        sections.append(f"Failed host: {failed_host}")

    failure_message = diagnosis.get("failure_message")
    if failure_message:
        sections.append(f"Failure message: {failure_message}")

    likely_causes = diagnosis["likely_causes"]
    if likely_causes:
        sections.append(
            "Likely cause hints:\n" + "\n".join(f"- {cause}" for cause in likely_causes)
        )

    stderr_tail = diagnosis["stderr_tail"]
    if stderr_tail:
        sections.append(f"stderr tail:\n{stderr_tail}")

    stdout_tail = diagnosis["stdout_tail"]
    if stdout_tail:
        sections.append(f"stdout tail:\n{stdout_tail}")

    return "\n\n".join(sections)


def _summarize_ansible_failure(diagnosis: AnsibleFailureDiagnosis) -> str:
    failed_task = diagnosis.get("failed_task")
    failed_host = diagnosis.get("failed_host")
    if failed_task and failed_host:
        return f"Ansible failed on host `{failed_host}` while running task `{failed_task}`."
    if failed_task:
        return f"Ansible failed while running task `{failed_task}`."
    return "Capture the failing command, Ansible output tails, and deterministic failure hints."


def _tail_lines(output: str, line_count: int) -> str:
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return "\n".join(lines[-line_count:])
