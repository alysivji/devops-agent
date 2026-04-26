from pathlib import Path
from typing import NotRequired, TypedDict

import yaml
from pydantic import BaseModel, ValidationError, model_validator
from strands import tool

from ..history import record_event

SERVICE_REGISTRY_PATH = Path("services/registry.yaml")


class ServiceRegistryEndpointDict(TypedDict):
    name: str
    url: NotRequired[str]
    host: NotRequired[str]
    port: NotRequired[int]
    protocol: NotRequired[str]
    scope: NotRequired[str]
    notes: NotRequired[str]


class ServiceRegistryEntryDict(TypedDict):
    name: str
    description: str
    runtime: str
    location: str
    status: str
    managed_by: str
    endpoints: list[ServiceRegistryEndpointDict]
    tags: list[str]


class ServiceListItemDict(TypedDict):
    name: str
    description: str
    runtime: str
    location: str
    status: str
    managed_by: str
    tags: list[str]


class ServiceUpsertResultDict(TypedDict):
    path: str
    action: str
    service: ServiceRegistryEntryDict


class ServiceRegistryEndpoint(BaseModel):
    name: str
    url: str | None = None
    host: str | None = None
    port: int | None = None
    protocol: str | None = None
    scope: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_address(self) -> "ServiceRegistryEndpoint":
        has_url = bool(self.url)
        has_host_port = bool(self.host) and self.port is not None
        if has_url or has_host_port:
            return self
        raise ValueError("endpoint must include either `url` or both `host` and `port`")


class ServiceRegistryEntry(BaseModel):
    name: str
    description: str
    runtime: str
    location: str
    status: str
    managed_by: str
    endpoints: list[ServiceRegistryEndpoint]
    tags: list[str]


def _serialize_endpoint(endpoint: ServiceRegistryEndpoint) -> ServiceRegistryEndpointDict:
    data: ServiceRegistryEndpointDict = {"name": endpoint.name}
    if endpoint.url is not None:
        data["url"] = endpoint.url
    if endpoint.host is not None:
        data["host"] = endpoint.host
    if endpoint.port is not None:
        data["port"] = endpoint.port
    if endpoint.protocol is not None:
        data["protocol"] = endpoint.protocol
    if endpoint.scope is not None:
        data["scope"] = endpoint.scope
    if endpoint.notes is not None:
        data["notes"] = endpoint.notes
    return data


def _serialize_service(entry: ServiceRegistryEntry) -> ServiceRegistryEntryDict:
    return {
        "name": entry.name,
        "description": entry.description,
        "runtime": entry.runtime,
        "location": entry.location,
        "status": entry.status,
        "managed_by": entry.managed_by,
        "endpoints": [_serialize_endpoint(endpoint) for endpoint in entry.endpoints],
        "tags": entry.tags,
    }


def _serialize_service_list_item(entry: ServiceRegistryEntryDict) -> ServiceListItemDict:
    return {
        "name": entry["name"],
        "description": entry["description"],
        "runtime": entry["runtime"],
        "location": entry["location"],
        "status": entry["status"],
        "managed_by": entry["managed_by"],
        "tags": entry["tags"],
    }


def _load_service_registry(path: Path = SERVICE_REGISTRY_PATH) -> list[ServiceRegistryEntryDict]:
    if not path.exists():
        return []

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Service registry must be a list: {path}")

    try:
        validated = [ServiceRegistryEntry.model_validate(service) for service in payload]
    except ValidationError as exc:
        raise ValueError(f"Invalid service registry entry in {path}: {exc}") from exc

    return [_serialize_service(entry) for entry in validated]


def _write_service_registry(
    registry: list[ServiceRegistryEntryDict], path: Path = SERVICE_REGISTRY_PATH
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            registry,
            sort_keys=False,
            allow_unicode=False,
        ),
        encoding="utf-8",
    )


@tool
def service_list() -> list[ServiceListItemDict]:
    """Return compact declared service inventory from the repo-owned registry."""
    registry = _load_service_registry()
    record_event(
        kind="service_list_read",
        status="completed",
        what="Read the declared service inventory.",
        why=(
            "Inspect concise declared service identity, ownership, and placement "
            "without touching live infrastructure."
        ),
        details={"count": len(registry), "names": [entry["name"] for entry in registry]},
    )
    return [_serialize_service_list_item(entry) for entry in registry]


@tool
def service_get(name: str) -> ServiceRegistryEntryDict:
    """Return the full declared registry entry for one named service."""
    registry = _load_service_registry()
    for entry in registry:
        if entry["name"] == name:
            record_event(
                kind="service_detail_read",
                status="completed",
                what=f"Read the declared service entry for `{name}`.",
                why=(
                    "Inspect one service's declared ownership and access paths without "
                    "touching live infrastructure."
                ),
                details={"name": name, "managed_by": entry["managed_by"]},
            )
            return entry

    raise ValueError(f"Service is not in the registry: {name}")


@tool
def service_upsert(
    name: str,
    description: str,
    runtime: str,
    location: str,
    status: str,
    managed_by: str,
    endpoints: list[ServiceRegistryEndpointDict],
    tags: list[str],
) -> ServiceUpsertResultDict:
    """Create or update one declared service entry in the repo-owned registry."""
    try:
        candidate = ServiceRegistryEntry.model_validate(
            {
                "name": name,
                "description": description,
                "runtime": runtime,
                "location": location,
                "status": status,
                "managed_by": managed_by,
                "endpoints": endpoints,
                "tags": tags,
            }
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid service registry entry: {exc}") from exc
    serialized = _serialize_service(candidate)
    registry = _load_service_registry()

    action = "created"
    for index, entry in enumerate(registry):
        if entry["name"] == name:
            registry[index] = serialized
            action = "updated"
            break
    else:
        registry.append(serialized)
        registry.sort(key=lambda entry: entry["name"])

    _write_service_registry(registry)
    record_event(
        kind="service_registry_write",
        status="completed",
        what=f"{action.title()} declared service entry `{name}`.",
        why=(
            "Keep the repo-owned service registry current when local automation "
            "or chart changes add or revise a declared service."
        ),
        details={
            "path": str(SERVICE_REGISTRY_PATH),
            "name": name,
            "action": action,
            "managed_by": managed_by,
        },
    )
    return {
        "path": str(SERVICE_REGISTRY_PATH),
        "action": action,
        "service": serialized,
    }
