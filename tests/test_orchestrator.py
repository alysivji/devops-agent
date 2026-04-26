from pathlib import Path
from typing import Any

from devops_bot.agents import orchestrator as orchestrator_module
from devops_bot.agents.orchestrator import MAIN_SYSTEM_PROMPT, OrchestratorAgent


class FakeAgent:
    def __init__(self) -> None:
        self.hooks: list[tuple[object, object]] = []

    def add_hook(self, callback: object, event_type: object) -> None:
        self.hooks.append((callback, event_type))


def test_orchestrator_prompt_treats_live_state_mismatch_as_actionable() -> None:
    assert "host state still differs" in MAIN_SYSTEM_PROMPT
    assert "diagnostic/remediation automation" in MAIN_SYSTEM_PROMPT
    assert "active configuration source" in MAIN_SYSTEM_PROMPT
    assert "ansible_create_playbook" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_prefers_goal_state_validation() -> None:
    assert "validating the user's requested end state" in MAIN_SYSTEM_PROMPT
    assert "requested state is already\n  true" in MAIN_SYSTEM_PROMPT
    assert "report success instead of continuing" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_distinguishes_grafana_from_prometheus_scraping() -> None:
    assert "Grafana\n  datasource check only proves Grafana can reach Prometheus" in (
        MAIN_SYSTEM_PROMPT
    )
    assert "does not prove\n  Kubernetes metrics are being scraped" in MAIN_SYSTEM_PROMPT
    assert "Prometheus target discovery shows Kubernetes\n  scrape jobs" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_requires_prometheus_target_validation() -> None:
    assert "/api/v1/targets?state=any" in MAIN_SYSTEM_PROMPT
    assert "/api/v1/targets?state=active" in MAIN_SYSTEM_PROMPT
    assert "Do\n  not treat config text containing `job_name: kubernetes-*` as sufficient" in (
        MAIN_SYSTEM_PROMPT
    )


def test_orchestrator_prompt_repairs_redundant_playbook_approval_gates() -> None:
    assert "`-e *_approve=true`" in MAIN_SYSTEM_PROMPT
    assert "redundant\n  in-playbook approval gate" in MAIN_SYSTEM_PROMPT
    assert "Use `ansible_edit_playbook`" in MAIN_SYSTEM_PROMPT
    assert "retry the playbook" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_updates_env_example_for_runtime_env_vars() -> None:
    assert "`env_example_update`" in MAIN_SYSTEM_PROMPT
    assert "`env_list_loaded_keys`" in MAIN_SYSTEM_PROMPT
    assert "Call `env_example_update` only when the user asks to update env" in (MAIN_SYSTEM_PROMPT)
    assert "after creating or editing a playbook that adds" in MAIN_SYSTEM_PROMPT
    assert "Do not call `env_example_update`\n  merely because a playbook run" in (
        MAIN_SYSTEM_PROMPT
    )
    assert "pass the playbook path as `source_path`" in MAIN_SYSTEM_PROMPT
    assert "Pass\n  `optional_variable_names`" in MAIN_SYSTEM_PROMPT
    assert "pass `section_name`" in MAIN_SYSTEM_PROMPT
    assert "Use\n  explicit `variable_names`" in MAIN_SYSTEM_PROMPT
    assert "`env_example_update` as documentation repair, not a prerequisite or" in (
        MAIN_SYSTEM_PROMPT
    )
    assert "Do not call it before or after a requested playbook" in MAIN_SYSTEM_PROMPT
    assert "use `env_list_loaded_keys` with the\n  playbook path as `source_path`" in (
        MAIN_SYSTEM_PROMPT
    )
    assert "If required keys are present, continue to the requested run" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_uses_service_registry_for_discovery_questions() -> None:
    assert "`service_list_registry`" in MAIN_SYSTEM_PROMPT
    assert '"what is running?"' in MAIN_SYSTEM_PROMPT
    assert '"where\n  does Grafana live?"' in MAIN_SYSTEM_PROMPT
    assert '"which automation owns nginx?"' in MAIN_SYSTEM_PROMPT
    assert "declared repo-owned metadata only" in MAIN_SYSTEM_PROMPT
    assert "not live health, not observed runtime state, and not general agent memory" in (
        MAIN_SYSTEM_PROMPT
    )


def test_orchestrator_prompt_defaults_deployments_to_kubernetes() -> None:
    assert "You orchestrate DevOps workflow tools" in MAIN_SYSTEM_PROMPT
    assert "Start by routing the request" in MAIN_SYSTEM_PROMPT
    assert "Helm/Kubernetes for schedulable application" in MAIN_SYSTEM_PROMPT
    assert "load the `kubernetes-troubleshooting` skill" in MAIN_SYSTEM_PROMPT
    assert "before handling failures" in MAIN_SYSTEM_PROMPT
    assert "Do not call `ansible_create_playbook`" in MAIN_SYSTEM_PROMPT
    assert "Load and follow `kubernetes-troubleshooting` instead" in MAIN_SYSTEM_PROMPT
    assert "`helm_create_chart` or `helm_edit_chart`" in MAIN_SYSTEM_PROMPT
    assert "update that chart's\n  README" in MAIN_SYSTEM_PROMPT
    assert "service name, namespace, ports" in MAIN_SYSTEM_PROMPT
    assert "For live Kubernetes deployment" in MAIN_SYSTEM_PROMPT
    assert "rollout/status, service, and\n  endpoint or pod readiness checks" in MAIN_SYSTEM_PROMPT
    assert "also check the actual\n  access URL" in MAIN_SYSTEM_PROMPT
    assert "prefer a\n  `NodePort` service over Traefik/Ingress" in MAIN_SYSTEM_PROMPT
    assert "hostnames,\n  path routing, TLS" in MAIN_SYSTEM_PROMPT
    assert "Repo-owned charts live under\n  `helm/charts`" in MAIN_SYSTEM_PROMPT
    assert "deploy the\n  chart path instead of a public chart reference" in MAIN_SYSTEM_PROMPT
    assert "call the tool instead of asking for approval in prose" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_loads_playbook_configuration_skill() -> None:
    assert "load the `playbook-configuration`\n  skill" in MAIN_SYSTEM_PROMPT
    assert "k3s, kubectl, Helm, kubeconfig files" in MAIN_SYSTEM_PROMPT
    assert "registry metadata, or host/cluster inventory targeting" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_prefers_restart_tool_for_local_systemd_services() -> None:
    assert "`systemd_restart_service`" in MAIN_SYSTEM_PROMPT
    assert "explicit local/control-node service restart requests" in MAIN_SYSTEM_PROMPT
    assert "Use Ansible playbooks for remote cluster-node service changes" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_routes_grafana_metrics_to_control_node() -> None:
    assert "foundation services" in MAIN_SYSTEM_PROMPT
    assert "observability\n  sinks" in MAIN_SYSTEM_PROMPT
    assert '"set up Grafana"' in MAIN_SYSTEM_PROMPT
    assert '"send metrics from Kubernetes\n  somewhere"' in MAIN_SYSTEM_PROMPT
    assert "inspect the Ansible playbook registry" in MAIN_SYSTEM_PROMPT
    assert "unless the user explicitly asks to deploy that\n  service inside Kubernetes" in (
        MAIN_SYSTEM_PROMPT
    )


def test_orchestrator_exposes_kubernetes_workflow_tools(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    fake_agent = FakeAgent()

    def fake_build_agent(**kwargs: Any) -> FakeAgent:
        captured["build_agent"] = kwargs
        return fake_agent

    monkeypatch.setattr(orchestrator_module, "build_model", lambda model_id: object())
    monkeypatch.setattr(orchestrator_module, "build_agent", fake_build_agent)

    orchestrator = OrchestratorAgent()

    tool_names = {tool.tool_name for tool in captured["build_agent"]["tools"]}
    assert orchestrator.agent is fake_agent
    assert {
        "helm_create_chart",
        "helm_edit_chart",
        "helm_list_charts",
        "helm_list_releases",
        "helm_status",
        "helm_upgrade_install",
        "kubernetes_fix_access",
        "kubectl_get",
        "kubectl_rollout_status",
        "systemd_restart_service",
        "env_example_update",
        "env_list_loaded_keys",
        "service_list_registry",
    }.issubset(tool_names)
    plugins = captured["build_agent"]["plugins"]
    assert len(plugins) == 1
    skill_names = {skill.name for skill in plugins[0].get_available_skills()}
    assert {"kubernetes-troubleshooting", "playbook-configuration"}.issubset(skill_names)


def test_kubernetes_troubleshooting_skill_uses_direct_blocker_wording() -> None:
    skill_text = Path("skills/kubernetes-troubleshooting/SKILL.md").read_text(encoding="utf-8")

    assert "Next step: repair cluster access with <playbook>" in skill_text
    assert "Do not end with soft phrasing" in skill_text
    assert "If you want me to proceed" in skill_text
    assert "do not stop with a\n     natural-language next step" in skill_text
    assert "stop at the\n     boundary" not in skill_text


def test_kubernetes_troubleshooting_skill_routes_foundation_services_to_ansible() -> None:
    skill_text = Path("skills/kubernetes-troubleshooting/SKILL.md").read_text(encoding="utf-8")

    assert "Foundation services for this repo" in skill_text
    assert "observability sinks" in skill_text
    assert "Grafana for\n     Kubernetes metrics" in skill_text
    assert "control-node Ansible work" in skill_text


def test_kubernetes_troubleshooting_skill_uses_kubeconfig_repair_tool() -> None:
    skill_text = Path("skills/kubernetes-troubleshooting/SKILL.md").read_text(encoding="utf-8")

    assert "kubernetes_fix_access" in skill_text
    assert "tool owns the explicit approval prompt" in skill_text
    assert "sudo install -D -m\n     600" in skill_text


def test_kubernetes_troubleshooting_skill_prefers_repo_owned_wrapper_charts() -> None:
    skill_text = Path("skills/kubernetes-troubleshooting/SKILL.md").read_text(encoding="utf-8")

    assert "prefer deploying the\n     chart path over a public chart reference" in skill_text
    assert "wrapper charts with `dependencies` in `Chart.yaml`" in skill_text


def test_kubernetes_troubleshooting_skill_reports_service_access_safely() -> None:
    skill_text = Path("skills/kubernetes-troubleshooting/SKILL.md").read_text(encoding="utf-8")

    assert "Do not tell the user to connect to `0.0.0.0`" in skill_text
    assert "recommend a port-forward" in skill_text
    assert "`nodes` resource and report `<node-ip>:<node-port>`" in skill_text


def test_playbook_configuration_skill_describes_k3s_sudo_kubeconfig_pattern() -> None:
    skill_text = Path("skills/playbook-configuration/SKILL.md").read_text(encoding="utf-8")

    assert "k3s keeps its admin kubeconfig at `/etc/rancher/k3s/k3s.yaml`" in skill_text
    assert "use `become: true`" in skill_text
    assert "kubectl --kubeconfig {{ k3s_admin_kubeconfig }}" in skill_text
    assert "helm --kubeconfig {{ k3s_admin_kubeconfig }}" in skill_text
    assert 'KUBECONFIG: "{{ k3s_admin_kubeconfig }}"' in skill_text
    assert "metadata header" in skill_text


def test_orchestrator_builds_session_manager_for_session_id(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    fake_session_manager = object()
    fake_agent = FakeAgent()

    def fake_build_session_manager(*, session_id: str) -> object:
        captured["session_id"] = session_id
        return fake_session_manager

    def fake_build_agent(**kwargs: Any) -> FakeAgent:
        captured["build_agent"] = kwargs
        return fake_agent

    monkeypatch.setattr(orchestrator_module, "build_model", lambda model_id: object())
    monkeypatch.setattr(orchestrator_module, "build_session_manager", fake_build_session_manager)
    monkeypatch.setattr(orchestrator_module, "build_agent", fake_build_agent)

    orchestrator = OrchestratorAgent(session_id="run-123")

    assert orchestrator.agent is fake_agent
    assert captured["session_id"] == "run-123"
    assert captured["build_agent"]["session_manager"] is fake_session_manager
