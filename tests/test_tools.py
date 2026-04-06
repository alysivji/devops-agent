import pytest

from agent.tools import list_ansible_playbooks, run_ansible_playbook


class TestRunAnsiblePlaybook:
    def test_run_ansible_playbook_not_found(self):
        with pytest.raises(FileNotFoundError):
            run_ansible_playbook("playbooks/test_playbook.yml")

    @pytest.mark.subprocess_vcr
    def test_run_ansible_playbook_success(self):
        result = run_ansible_playbook("ansible/playbooks/hello-control.yaml")
        assert "PLAY RECAP" in result


class TestListAnsiblePlaybooks:
    def test_list_ansible_playbooks(self):
        playbooks = list_ansible_playbooks()
        assert isinstance(playbooks, list)
        assert len(playbooks) > 0
        assert "ansible/playbooks/hello-control.yaml" in playbooks
        assert "ansible/playbooks/hello-workers.yaml" in playbooks
