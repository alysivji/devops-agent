import pytest

from agent.tools import get_ansible_playbook_registry, run_ansible_playbook


class TestRunAnsiblePlaybook:
    def test_run_ansible_playbook_not_found(self):
        with pytest.raises(FileNotFoundError):
            run_ansible_playbook("playbooks/test_playbook.yml")

    @pytest.mark.subprocess_vcr
    def test_run_ansible_playbook_success(self):
        result = run_ansible_playbook("ansible/playbooks/hello-control.yaml")
        assert "PLAY RECAP" in result


class TestGetAnsiblePlaybookRegistry:
    def test_get_ansible_playbook_registry(self):
        registry = get_ansible_playbook_registry()

        assert isinstance(registry, list)
        assert len(registry) > 0
        assert registry == [
            {
                "description": "Ping the control node group.",
                "name": "hello-control",
                "path": "ansible/playbooks/hello-control.yaml",
                "tags": ["connectivity", "control"],
                "target": "control",
            },
            {
                "description": "Ping the worker node group.",
                "name": "hello-workers",
                "path": "ansible/playbooks/hello-workers.yaml",
                "tags": ["connectivity", "workers"],
                "target": "workers",
            },
        ]
