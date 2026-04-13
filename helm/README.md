# Helm

Repo contains Helm configuration.

Repo-owned application charts live under `helm/charts/`. The agent discovers
charts in that directory through the Helm chart registry and edits existing
charts with the chart-aware editor before running `helm lint`.
