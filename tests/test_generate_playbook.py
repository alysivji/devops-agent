import shutil
from contextlib import chdir
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.generate_playbook import SYSTEM_PROMPT, GeneratedPlaybookYaml


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


def test_generator_prompt_requires_raspberry_pi_reboot_wait_verification() -> None:
    assert "Raspberry Pi" in SYSTEM_PROMPT
    assert "wait_for_connection" in SYSTEM_PROMPT
    assert "/proc/sys/kernel/random/boot_id" in SYSTEM_PROMPT
    assert "reboot_timeout` of at least 1200 seconds" in SYSTEM_PROMPT


def test_generator_prompt_requires_bounded_cluster_service_operations() -> None:
    assert "service operations on Raspberry Pi" in SYSTEM_PROMPT
    assert "avoid using `async`/`poll`" in SYSTEM_PROMPT
    assert "no_block: true" in SYSTEM_PROMPT
    assert "service_facts" in SYSTEM_PROMPT


def test_generator_prompt_requires_goal_oriented_validation() -> None:
    assert "requested end state" in SYSTEM_PROMPT
    assert "all expected nodes as `Ready`" in SYSTEM_PROMPT
    assert "diagnostics only" in SYSTEM_PROMPT
