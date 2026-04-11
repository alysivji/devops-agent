"""Preload common project imports for the local IPython shell."""

from devops_bot.agents.orchestrator import OrchestratorAgent  # noqa: F401
from devops_bot.agents.playbook_generator import GeneratePlaybookAgent  # noqa: F401
from devops_bot.agents.playbook_metadata import PlaybookMetadataAgent  # noqa: F401
from devops_bot.tools import (  # noqa: F401
    create_git_branch,
    create_git_commit,
    get_ansible_inventory_groups,
    get_ansible_playbook_registry,
    git_push,
    git_status,
    http_get,
    list_git_commits,
    run_ansible_playbook,
    search_web,
)
from devops_bot.tools.playbooks import create_ansible_playbook  # noqa: F401

print("Loaded agents: OrchestratorAgent, GeneratePlaybookAgent, PlaybookMetadataAgent")
print(
    "Loaded tools: create_ansible_playbook, get_ansible_inventory_groups, "
    "get_ansible_playbook_registry, run_ansible_playbook, search_web, "
    "http_get, git_status, list_git_commits, create_git_commit, "
    "create_git_branch, git_push"
)
