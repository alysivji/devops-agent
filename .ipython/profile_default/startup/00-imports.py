"""Preload common project imports for the local IPython shell."""

print("Loaded agents: OrchestratorAgent, GeneratePlaybookAgent, PlaybookMetadataAgent")
print(
    "Loaded tools: create_ansible_playbook, get_ansible_inventory_groups, "
    "get_ansible_playbook_registry, run_ansible_playbook, git_status, "
    "list_git_commits, create_git_commit, create_git_branch, git_push"
)
