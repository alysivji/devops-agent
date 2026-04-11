from agent.orchestrator import MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_treats_live_state_mismatch_as_actionable() -> None:
    assert "live host state still differs" in MAIN_SYSTEM_PROMPT
    assert "diagnostic/remediation automation" in MAIN_SYSTEM_PROMPT
    assert "create_ansible_playbook" in MAIN_SYSTEM_PROMPT


def test_orchestrator_prompt_prefers_goal_state_validation() -> None:
    assert "validating the user's requested end state" in MAIN_SYSTEM_PROMPT
    assert "nodes reporting `Ready` from the control-plane API" in MAIN_SYSTEM_PROMPT
    assert "diagnostics only when that end state is not met" in MAIN_SYSTEM_PROMPT
