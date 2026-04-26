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


def _load_service_registry(path: Path = SERVICE_REGISTRY_PATH) -> list[ServiceRegistryEntryDict]:
    if not path.exists():
        return []

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Service registry must be a mapping: {path}")

    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError(f"Service registry must contain a `services` list: {path}")

    try:
        validated = [ServiceRegistryEntry.model_validate(service) for service in services]
    except ValidationError as exc:
        raise ValueError(f"Invalid service registry entry in {path}: {exc}") from exc

    return [_serialize_service(entry) for entry in validated]


@tool
def service_list_registry() -> list[ServiceRegistryEntryDict]:
    """Return the repo-owned static service discovery registry."""
    registry = _load_service_registry()
    record_event(
        kind="service_registry_read",
        status="completed",
        what="Read the service discovery registry.",
        why=(
            "Inspect declared service identity, ownership, and access paths without "
            "touching live infrastructure."
        ),
        details={"count": len(registry), "names": [entry["name"] for entry in registry]},
    )
    return registry
