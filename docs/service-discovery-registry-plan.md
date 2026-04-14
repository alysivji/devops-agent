# Service Discovery Registry Plan

## Goal

Add a small repo-owned service discovery registry for the DevOps agent. The
registry should answer practical questions like "what is running?", "where does
Grafana live?", and "which automation owns nginx?" without requiring a live
Kubernetes or Ansible connection.

## First Pass

Use `services/registry.yaml` as static source of truth for known services and
their access paths. This is intentionally separate from live state:

- Ansible playbooks describe host and substrate automation.
- Helm charts describe Kubernetes desired state.
- The service registry describes human-facing service identity and endpoints.
- Live tools such as Helm, kubectl, and Ansible still validate whether a service
  is actually healthy right now.

The first tool should be read-only and return plain JSON-serializable
dictionaries. It should not call the cluster, SSH to hosts, run Ansible, or infer
health from stale state.

## Suggested Entry Shape

```yaml
services:
  - name: grafana
    description: Host-level Grafana service on the control node.
    runtime: systemd
    location: control
    status: expected
    managed_by: ansible/playbooks/install-grafana.yaml
    endpoints:
      - name: health
        url: http://127.0.0.1:3000/api/health
        scope: control-node-local
    tags:
      - monitoring
      - grafana
```

Required fields for v1 should be `name`, `description`, `runtime`, `location`,
`status`, `managed_by`, `endpoints`, and `tags`. Each endpoint should include a
`name` and either a `url` or a `host`/`port` pair. Extra endpoint fields such as
`protocol`, `scope`, and `notes` can stay optional.

## Seed Entries

Start with services already documented by checked-in automation:

- `minio`: control-node systemd service managed by
  `ansible/playbooks/deploy-and-validate-minio.yaml`, with API access on
  `http://127.0.0.1:9000` and console access on `http://127.0.0.1:9001`.
- `grafana`: control-node systemd service managed by
  `ansible/playbooks/install-grafana.yaml`, with health checks at
  `http://127.0.0.1:3000/api/health`.
- `prometheus`: control-node systemd service managed by
  `ansible/playbooks/install-prometheus.yaml`, with readiness checks at
  `http://127.0.0.1:9090/-/ready`.
- `nginx`: Kubernetes service from the repo-owned chart at `helm/charts/nginx`,
  expected as service `nginx-upstream` in the `default` namespace with NodePorts
  `30080` for HTTP and `30443` for HTTPS.

## Future Tool

Expose a `service_list_registry` tool from the agent. It should:

- Read `services/registry.yaml`.
- Validate the minimal shape.
- Return a list of plain dictionaries.
- Record a run-history event with the number of services and their names.
- Return an empty list when the registry file does not exist.

Tests should cover valid entries, missing files, invalid YAML shape, endpoint
validation, and the orchestrator exposing the tool.
