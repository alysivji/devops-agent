import shutil
from contextlib import chdir
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from devops_bot.agents.playbook_generator import (
    SYSTEM_PROMPT,
    GeneratedPlaybookYaml,
    GeneratePlaybookAgent,
)


class TestGeneratedPlaybookYaml:
    @pytest.mark.skipif(
        shutil.which("ansible-playbook") is None,
        reason="ansible-playbook is required for generated playbook validation",
    )
    def test_accepts_ansible_valid_yaml(self, tmp_path: Path) -> None:
        yaml_text = (
            "- hosts: localhost\n"
            "  gather_facts: false\n"
            "  tasks:\n"
            "    - name: Confirm generated playbook syntax\n"
            "      ansible.builtin.debug:\n"
            "        msg: ok\n"
        )

        with chdir(tmp_path):
            result = GeneratedPlaybookYaml(yaml=yaml_text)

        assert result.yaml == yaml_text

    @pytest.mark.skipif(
        shutil.which("ansible-playbook") is None,
        reason="ansible-playbook is required for generated playbook validation",
    )
    def test_rejects_ansible_invalid_yaml(self, tmp_path: Path) -> None:
        expected_error = (
            r"(?s)generated playbook failed ansible syntax-check:"
            r".*conflicting action statements: ansible\.builtin\.set_fact, cacheable"
            r".*Reproduce generated set_fact cacheable conflict"
        )

        with chdir(tmp_path):
            with pytest.raises(ValidationError, match=expected_error):
                GeneratedPlaybookYaml(
                    yaml=(
                        "- hosts: localhost\n"
                        "  tasks:\n"
                        "    - name: Reproduce generated set_fact cacheable conflict\n"
                        "      ansible.builtin.set_fact:\n"
                        "        generated_fact: ok\n"
                        "      cacheable: true\n"
                    )
                )

    def test_rejects_empty_yaml_list(self) -> None:
        with pytest.raises(ValidationError, match="generated playbook YAML"):
            GeneratedPlaybookYaml(yaml="[]")


def test_generator_prompt_requires_remote_reboot_wait_verification() -> None:
    assert "remote hosts" in SYSTEM_PROMPT
    assert "wait_for_connection" in SYSTEM_PROMPT
    assert "/proc/sys/kernel/random/boot_id" in SYSTEM_PROMPT
    assert "reboot_timeout` of at least 1200 seconds" in SYSTEM_PROMPT


def test_generator_prompt_requires_bounded_remote_service_operations() -> None:
    assert "long-running remote service operations" in SYSTEM_PROMPT
    assert "Avoid using" in SYSTEM_PROMPT
    assert "`async`/`poll`" in SYSTEM_PROMPT
    assert "no_block: true" in SYSTEM_PROMPT
    assert "desired service or application state" in SYSTEM_PROMPT


def test_generator_prompt_requires_goal_oriented_validation() -> None:
    assert "requested end state" in SYSTEM_PROMPT
    assert "cluster/API-level health" in SYSTEM_PROMPT
    assert "diagnostics only" in SYSTEM_PROMPT


def test_generator_prompt_requires_prometheus_target_discovery_validation() -> None:
    assert "For Prometheus Kubernetes scraping" in SYSTEM_PROMPT
    assert "/api/v1/targets?state=any" in SYSTEM_PROMPT
    assert "/api/v1/targets?state=active" in SYSTEM_PROMPT
    assert "Do not validate this end state only by checking" in SYSTEM_PROMPT
    assert "`job_name: kubernetes-*`" in SYSTEM_PROMPT


def test_generator_prompt_avoids_in_cluster_prometheus_auth_for_host_service() -> None:
    assert "For host-level Prometheus scraping a Kubernetes cluster" in SYSTEM_PROMPT
    assert "/var/run/secrets/kubernetes.io/serviceaccount/token" in SYSTEM_PROMPT
    assert "readable by the Prometheus service\n  user" in SYSTEM_PROMPT
    assert "validate that service discovery can use them" in SYSTEM_PROMPT


def test_generator_prompt_avoids_internal_approval_gates() -> None:
    assert "Do not add approval gates" in SYSTEM_PROMPT
    assert "`*_approve`" in SYSTEM_PROMPT
    assert "`ansible_run_playbook` tool prompt" in SYSTEM_PROMPT


def test_generator_prompt_requires_env_backed_sensitive_values() -> None:
    assert "sensitive value" in SYSTEM_PROMPT
    assert "lookup('ansible.builtin.env', 'NAME', default='')" in SYSTEM_PROMPT
    assert "Do not hardcode real" in SYSTEM_PROMPT
    assert "literal environment variable names" in SYSTEM_PROMPT
    assert "`.env.example`" in SYSTEM_PROMPT
    assert "ansible.builtin.assert" in SYSTEM_PROMPT
    assert "untracked `.env` file" in SYSTEM_PROMPT


def test_generator_prompt_requires_restart_or_reload_after_service_config_changes() -> None:
    assert "systemd service unit, environment file, or service" in SYSTEM_PROMPT
    assert "`reloaded` or" in SYSTEM_PROMPT
    assert "`restarted` service state" in SYSTEM_PROMPT
    assert "registered file-change results" in SYSTEM_PROMPT
    assert "Use `started` only as the steady" in SYSTEM_PROMPT


def test_generator_prompt_defaults_deployments_to_kubernetes() -> None:
    assert "application/service deployment requests" in SYSTEM_PROMPT
    assert 'For prompts such as "set up nginx"' in SYSTEM_PROMPT
    assert "deploy to the cluster with Helm" in SYSTEM_PROMPT
    assert "Do not install application packages" in SYSTEM_PROMPT
    assert "helm upgrade --install" in SYSTEM_PROMPT


def test_generator_prompt_loads_playbook_configuration_for_k3s_commands() -> None:
    assert "load and follow the `playbook-configuration` skill" in SYSTEM_PROMPT
    assert "k3s, kubectl, Helm, kubeconfig files, or sudo/become" in SYSTEM_PROMPT
    assert "kubectl --kubeconfig {{ k3s_admin_kubeconfig }}" in SYSTEM_PROMPT
    assert "helm --kubeconfig {{ k3s_admin_kubeconfig }}" in SYSTEM_PROMPT
    assert "Use\n  `become: true`" in SYSTEM_PROMPT


def test_generator_prompt_requires_official_docs_research() -> None:
    assert "Before generating install or configuration automation" in SYSTEM_PROMPT
    assert "use `search_web` to find current\n  official documentation" in SYSTEM_PROMPT
    assert "use `http_get` to read the relevant page" in SYSTEM_PROMPT
    assert "CLI flags" in SYSTEM_PROMPT
    assert "Prefer official upstream/vendor documentation" in SYSTEM_PROMPT


def test_generator_prompt_routes_grafana_metrics_to_control_node() -> None:
    assert "foundation services for this repo" in SYSTEM_PROMPT
    assert "observability sinks" in SYSTEM_PROMPT
    assert "Grafana" in SYSTEM_PROMPT
    assert "Kubernetes metrics to go" in SYSTEM_PROMPT
    assert "Only deploy those services into Kubernetes" in SYSTEM_PROMPT


def test_generator_agent_exposes_playbook_configuration_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_build_agent(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("devops_bot.agents.playbook_generator.build_model", lambda **_: object())
    monkeypatch.setattr("devops_bot.agents.playbook_generator.build_agent", fake_build_agent)

    GeneratePlaybookAgent()

    skill_names = {skill.name for skill in captured["plugins"][0].get_available_skills()}
    assert "playbook-configuration" in skill_names
