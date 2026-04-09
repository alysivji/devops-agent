import pytest

from agent.tools import (
    get_ansible_inventory_groups,
    get_ansible_playbook_registry,
    run_ansible_playbook,
)


class TestRunAnsiblePlaybook:
    def test_run_ansible_playbook_not_found(self):
        with pytest.raises(ValueError):
            run_ansible_playbook("playbooks/test_playbook.yml")

    @pytest.mark.subprocess_vcr
    def test_run_ansible_playbook_success(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        result = run_ansible_playbook("ansible/playbooks/hello-control.yaml")
        assert "PLAY RECAP" in result


class TestGetAnsiblePlaybookRegistry:
    def test_get_ansible_playbook_registry(self):
        registry = get_ansible_playbook_registry()

        assert isinstance(registry, list)
        assert len(registry) > 0
        assert registry == [
            {
                "description": "Ping the cluster node group.",
                "name": "hello-cluster",
                "path": "ansible/playbooks/hello-cluster.yaml",
                "requires_approval": True,
                "tags": ["connectivity", "cluster"],
                "target": "cluster",
            },
            {
                "description": "Ping the control node group.",
                "name": "hello-control",
                "path": "ansible/playbooks/hello-control.yaml",
                "requires_approval": True,
                "tags": ["connectivity", "control"],
                "target": "control",
            },
            {
                "description": (
                    "Lists files in the root directory on both control and "
                    "cluster nodes and displays the output."
                ),
                "name": "list_files",
                "path": "ansible/playbooks/list-files.yaml",
                "requires_approval": True,
                "tags": ["file_management", "listing", "debugging"],
                "target": "both",
            },
        ]


class TestGetAnsibleInventoryGroups:
    def test_get_ansible_inventory_groups(self):
        groups = get_ansible_inventory_groups()

        assert groups == ["cluster", "control"]
