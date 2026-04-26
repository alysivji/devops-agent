# Helm

Repo contains Helm configuration.

Repo-owned application charts live under `helm/charts/`. The agent discovers charts in that directory through the Helm chart registry and edits existing charts with the chart-aware editor before running `helm lint`.

For public charts, prefer a repo-owned wrapper chart instead of deploying the public chart reference directly. The wrapper chart records the upstream chart in `Chart.yaml` under `dependencies` and keeps local cluster overrides in `values.yaml`. This gives the agent a registry entry to find and a local desired state file to edit before a live deployment.

Example:

```yaml
dependencies:
  - name: nginx
    alias: upstream
    version: ">=0.0.0"
    repository: oci://registry-1.docker.io/bitnamicharts
```

Build dependencies before installing a wrapper chart:

```bash
helm dependency build helm/charts/nginx
```

Then deploy from the repo-owned chart path:

```bash
helm upgrade --install nginx helm/charts/nginx --namespace default --wait --timeout 5m
```
