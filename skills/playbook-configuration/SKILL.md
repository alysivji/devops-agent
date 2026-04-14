---
name: playbook-configuration
description: Configure Ansible playbooks for this devops-agent repo. Use when creating, editing, reviewing, or explaining playbooks under ansible/playbooks, especially when the playbook uses kubectl, Helm, k3s, sudo/become, kubeconfig files, registry metadata headers, inventory groups, or remote-impacting host/cluster automation.
---

# Playbook Configuration

Use this skill to keep generated and edited playbooks aligned with the repo's
registry, inventory, and k3s access model.

## Required Shape

- Keep the metadata header at the top of every checked-in playbook:
  `name`, `description`, `target`, `requires_approval`, and `tags`.
- Use `target: control` for control-node-only work, `target: cluster` for
  worker-node-only work, and `target: both` when a playbook touches both groups.
- Set `requires_approval: true` for any playbook that uses `become`, changes
  host or cluster state, installs packages, restarts services, writes files, or
  depends on external credentials.
- Keep play YAML top-down: first inspect or validate the current goal state,
  then remediate only when needed, then validate the final state.
- Do not add internal approval variables or assertions such as
  `*_approve`; the registry metadata and `ansible_run_playbook` own execution
  approval.

## Inventory Targets

- The `control` group is the local control node and uses
  `ansible_connection=local`.
- The `cluster` group is Raspberry Pi worker nodes reached over SSH as `pi`.
- Prefer control-node plays for `kubectl`, Helm, k3s server validation,
  kubeconfig repair, observability control-plane services, and cluster API
  checks.
- Use cluster plays only when the requested state belongs on the worker hosts,
  such as node prerequisites, boot/cgroup configuration, or k3s agent state.

## k3s, kubectl, and Helm

- k3s keeps its admin kubeconfig at `/etc/rancher/k3s/k3s.yaml`, which is
  normally root-readable. Do not assume the Ansible user or the agent process
  can read it directly.
- For playbooks that call `kubectl` or `helm` against the k3s cluster from the
  control node, use `become: true` for the play or the specific task and set an
  explicit kubeconfig:

```yaml
vars:
  k3s_admin_kubeconfig: /etc/rancher/k3s/k3s.yaml
tasks:
  - name: Validate Kubernetes nodes through the k3s admin kubeconfig
    ansible.builtin.command: kubectl --kubeconfig {{ k3s_admin_kubeconfig }} get nodes -o json
    register: kubectl_nodes
    changed_when: false
```

- For Helm commands, either pass `--kubeconfig` directly or set `KUBECONFIG`
  in the task environment:

```yaml
  - name: Validate Helm releases through the k3s admin kubeconfig
    ansible.builtin.command: helm --kubeconfig {{ k3s_admin_kubeconfig }} list --all-namespaces --output json
    register: helm_releases
    changed_when: false

  - name: Validate Helm releases through the k3s admin kubeconfig
    ansible.builtin.command: helm list --all-namespaces --output json
    environment:
      KUBECONFIG: "{{ k3s_admin_kubeconfig }}"
    register: helm_releases
    changed_when: false
```

- Prefer `ansible.builtin.command` with explicit arguments for `kubectl` and
  Helm. Use shell only when shell behavior is required.
- Validate JSON command output with `from_json` and use bracket lookup for keys
  that can collide with Python method names, such as `parsed_json['items']`.
- If a playbook's goal is to make non-root kubeconfig access work for the agent
  user, prefer repairing or copying kubeconfig intentionally with clear file
  ownership and mode instead of running all future client commands as root.

## Validation

- Validate the requested end state, not just package or file presence.
- For Kubernetes access, prefer `kubectl ... get ... -o json`, `kubectl
  cluster-info`, `helm list --all-namespaces`, or Prometheus/Grafana API checks
  that prove the user-visible goal.
- Include actionable assertion failure messages and structured debug output for
  important validation failures.
