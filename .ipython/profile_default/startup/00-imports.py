"""Preload common project imports for the local IPython shell."""

from agent.generate_playbook import GeneratePlaybookAgent  # noqa: F401
from agent.orchestrator import OrchestratorAgent  # noqa: F401
from agent.playbook_metadata import PlaybookMetadataAgent  # noqa: F401
from agent.tools import (  # noqa: F401
    create_ansible_playbook,
    create_git_branch,
    create_git_commit,
    get_ansible_inventory_groups,
    get_ansible_playbook_registry,
    git_push,
    git_status,
    list_git_commits,
    run_ansible_playbook,
)

print("Loaded agents: OrchestratorAgent, GeneratePlaybookAgent, PlaybookMetadataAgent")
print(
    "Loaded tools: create_ansible_playbook, get_ansible_inventory_groups, "
    "get_ansible_playbook_registry, run_ansible_playbook, git_status, "
    "list_git_commits, create_git_commit, create_git_branch, git_push"
)
