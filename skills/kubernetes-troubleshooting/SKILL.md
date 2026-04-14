---
name: kubernetes-troubleshooting
description: Diagnose Kubernetes and Helm failures in this devops-agent repo. Use when kubectl, Helm, chart registry, chart edit, deploy, rollout, kubeconfig, k3s API access, localhost:8080 fallback, permission denied on /etc/rancher/k3s/k3s.yaml, or cluster prerequisite problems block a Kubernetes workflow.
---

# Kubernetes Troubleshooting

Use this skill to diagnose Kubernetes/Helm failures without automatically
turning an application deploy into host repair.

## Workflow

1. Classify the request.
   - App workload deploy/status/rollout/chart work: stay on Helm/Kubernetes tools.
   - Host/substrate setup or explicit repair request: use Ansible registry/playbooks.
   - Foundation services for this repo, including control panels,
     observability sinks, and management services such as Grafana for
     Kubernetes metrics, are control-node Ansible work unless the user
     explicitly asks to deploy them inside Kubernetes.
   - Ambiguous stateful service: ask whether lifecycle/storage is host-managed or cluster-managed.

2. Start with read-only cluster checks.
   - Use `helm_list_releases`, `helm_status`, `kubectl_get`, or `kubectl_rollout_status`
     to reproduce the user-visible failure.
   - For repo-owned desired state, use `helm_list_charts` before creating or editing charts.
   - If a repo-owned chart exists for the requested app, prefer deploying the
     chart path over a public chart reference. Public charts should usually be
     captured as wrapper chart dependencies under `helm/charts/`.
   - Do not run `ansible_run_playbook` just because a Helm/Kubernetes check failed.

3. Interpret common access failures.
   - `http://localhost:8080/version` usually means no usable kubeconfig/current
     context was loaded by the current process.
   - `permission denied` for `/etc/rancher/k3s/k3s.yaml` usually means the
     current user cannot read the k3s admin kubeconfig.
   - Prefer making a user-readable kubeconfig available to the agent user over
     running Helm as root.
   - For the k3s kubeconfig case, call the `kubernetes_fix_access` tool. The
     tool owns the explicit approval prompt before it writes anything. It copies
     `/etc/rancher/k3s/k3s.yaml` to `~/.kube/config` with `sudo install -D -m
     600 -o <current-user> -g <current-group>`, then verifies `kubectl
     cluster-info` and `helm list --all-namespaces` with that kubeconfig.

4. Report blockers clearly.
   - Name the failing command/tool and the exact error.
   - If the known k3s kubeconfig access repair applies, do not stop with a
     natural-language next step. Call `kubernetes_fix_access`, then return to
     the original Helm/Kubernetes task if the repair succeeds.
   - If a broader registry playbook is the only available repair path, identify
     it with direct wording:
     `Next step: repair cluster access with <playbook>, then retry <original task>.`
   - Do not end with soft phrasing like `If you want me to proceed...`.

5. Repair only when requested.
   - If the user explicitly asks to repair kubeconfig, Helm installation, k3s,
     node prerequisites, or cluster substrate, inspect `ansible_list_playbooks`
     and run the matching approved-gated playbook.
   - When the blocker is only that the current user cannot read
     `/etc/rancher/k3s/k3s.yaml`, prefer `kubernetes_fix_access` over a
     broader Ansible repair playbook.
   - After a successful repair, return to the original Helm/Kubernetes
     validation or deployment.

6. Report service access accurately.
   - Do not tell the user to connect to `0.0.0.0`; it is a bind address, not a
     usable client destination.
   - For simple local machine/LAN exposure, prefer a `NodePort` service over
     adding Traefik/Ingress unless the user asks for hostnames, path routing,
     TLS, or shared HTTP routing across multiple services.
   - Treat Traefik as an ingress-controller path: use it when the desired
     access model is an `Ingress`, not just when a single service needs to be
     reachable from the node.
   - For `LoadBalancer` services with external IP `<pending>` on local k3s,
     recommend a port-forward such as `kubectl port-forward svc/<name>
     8080:80`.
   - If reporting NodePort access, first inspect nodes with `kubectl_get` using
     the `nodes` resource and report `<node-ip>:<node-port>`, not
     `0.0.0.0:<node-port>`.

## Repo Conventions

- Repo-owned Helm charts live under `helm/charts`.
- Public upstream charts can be represented by wrapper charts with
  `dependencies` in `Chart.yaml` and local overrides in `values.yaml`.
- Use `helm_create_chart` for new chart scaffolds and `helm_edit_chart` for
  coordinated edits across values, templates, helpers, and related files.
- Use `helm_upgrade_install` only for live cluster install/upgrade requests.
- Use Ansible for k3s, kubeconfig, Helm/kubectl installation, node boot/cgroup
  prerequisites, and host-managed durable services.
