# Services

This directory holds the repo-owned declared service registry at `registry.yaml`.

The registry is for static service identity, ownership, and access paths. It is not live health, observed runtime state, workflow history, or agent memory.

Keep entries aligned with repo-owned automation such as checked-in Ansible playbooks and Helm charts.

The agent exposes this file through offline `service_list`, `service_get`, and `service_upsert` tools.
