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
    assert "requested capability works" in MAIN_SYSTEM_PROMPT
    assert "cluster/API health" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_defaults_deployments_to_kubernetes() -> None:
    assert "You orchestrate DevOps workflow tools" in MAIN_SYSTEM_PROMPT
    assert "Start by routing the request" in MAIN_SYSTEM_PROMPT
    assert "application/service deployment requests" in MAIN_SYSTEM_PROMPT
    assert 'For prompts such as "set up nginx"' in MAIN_SYSTEM_PROMPT
    assert "prefer Helm or Kubernetes" in MAIN_SYSTEM_PROMPT
    assert "over installing packages" in MAIN_SYSTEM_PROMPT
    assert "needed Ansible host/substrate" in MAIN_SYSTEM_PROMPT
    assert "Route requests before choosing tools" in MAIN_SYSTEM_PROMPT
    assert "Do not call `ansible_create_playbook`" in MAIN_SYSTEM_PROMPT
    assert "stateful ambiguous requests such as postgres" in MAIN_SYSTEM_PROMPT
    assert "If a Helm/Kubernetes workflow fails" in MAIN_SYSTEM_PROMPT
    assert "use `helm_create_chart`" in MAIN_SYSTEM_PROMPT
    assert "Use `helm_upgrade_install` for live cluster" in MAIN_SYSTEM_PROMPT
    assert "use `helm_edit_chart`" in MAIN_SYSTEM_PROMPT
    assert "values, templates, helpers" in MAIN_SYSTEM_PROMPT
    assert "Inspect `helm_list_charts`" in MAIN_SYSTEM_PROMPT
    assert "Repo-owned charts live under `helm/charts`" in MAIN_SYSTEM_PROMPT


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
        "kubectl_get",
        "kubectl_rollout_status",
    }.issubset(tool_names)


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
