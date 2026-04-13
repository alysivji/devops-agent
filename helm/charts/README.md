# Helm Charts

Repo-owned application charts live here. Each chart directory should include a
`Chart.yaml` so the agent can include it in the Helm chart registry.

Charts may wrap public upstream charts with Helm dependencies. Put the upstream
chart in `Chart.yaml` under `dependencies`, use an `alias` such as `upstream`,
and keep local overrides in `values.yaml` under that alias. This makes the
desired state visible to the agent instead of hiding it in an ad hoc live Helm
install command.
