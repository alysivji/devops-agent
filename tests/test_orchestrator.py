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


def test_orchestrator_prompt_includes_kubectl_inspection_tools() -> None:
    assert "kubectl_get" in MAIN_SYSTEM_PROMPT
    assert "kubectl_describe" in MAIN_SYSTEM_PROMPT
    assert "kubectl_logs" in MAIN_SYSTEM_PROMPT
    assert "must not be used for mutating cluster state" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_includes_helm_deployment_tools() -> None:
    assert "helm_list_releases" in MAIN_SYSTEM_PROMPT
    assert "helm_status" in MAIN_SYSTEM_PROMPT
    assert "helm_upgrade_install" in MAIN_SYSTEM_PROMPT
    assert "prefer Helm when a chart exists" in MAIN_SYSTEM_PROMPT


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
    tool_names = {tool.__name__ for tool in captured["build_agent"]["tools"]}
    assert {"kubectl_get", "kubectl_describe", "kubectl_logs"}.issubset(tool_names)
    assert {"helm_list_releases", "helm_status", "helm_upgrade_install"}.issubset(tool_names)
