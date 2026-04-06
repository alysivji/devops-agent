from agent.tools import run_ansible_playbook

import pytest


class TestRunAnsiblePlaybook:
    def test_run_ansible_playbook_not_found(self):
        with pytest.raises(FileNotFoundError):
            run_ansible_playbook("playbooks/test_playbook.yml")

    @pytest.mark.subprocess_vcr
    def test_run_ansible_playbook_success(self):
        result = run_ansible_playbook("ansible/playbooks/hello-control.yaml")
