# Specialized DevOps Agents

## Why

The current agent is centered on Ansible playbook generation, editing, registry lookup, execution, and failure recovery. That is useful, but adding every future DevOps capability as another direct tool on the main orchestrator will make tool selection noisy and make the system prompt harder to reason about.

The direction should be a thin routing layer with specialized agents for different task groups. Each specialized agent should have a narrow mandate, a small tool surface, and a structured handoff contract.

## Design Principles

- Prefer explicit workflows for high-risk DevOps operations.
- Keep each agent's tool list small and task-specific.
- Put safety boundaries in code and tool wrappers, not only in prompts.
- Use read-only inspection before mutation whenever possible.
- Make remote work explicit and approval-gated.
- Return JSON-serializable tool results with plain dict/list/scalar shapes.
- Treat generated playbooks as reviewable artifacts before execution.
- Verify requested end state after execution instead of assuming success from a completed command.

## Proposed Agent Split

### RequestRouterAgent

Owns initial request classification and handoff.

Responsibilities:

- Decide whether the request is read-only, playbook creation, playbook execution, failure recovery, or change documentation.
- Keep the top-level prompt short.
- Avoid direct access to broad remote mutation tools.
- Hand off to exactly one specialized agent for the next step unless a workflow explicitly requires multiple stages.

Tools:

- Minimal registry or metadata lookup tools only.
- No direct arbitrary shell or remote execution tools.

### InventoryInspectorAgent

Owns read-only discovery and current-state checks.

Responsibilities:

- Inspect inventory groups and host metadata.
- Check SSH reachability.
- Gather host facts.
- Inspect service status, package state, disk space, memory, ports, and relevant Kubernetes or system health signals when available.
- Return structured facts that other agents can use.

Tools:

- Read-only Ansible inventory tools.
- Read-only host/service inspection tools.
- Read-only Kubernetes or HTTP health tools if added later.

### PlaybookGeneratorAgent

Owns new playbook creation.

Responsibilities:

- Generate playbooks from natural-language requests.
- Include the required metadata header fields: `name`, `description`, `target`, `requires_approval`, and `tags`.
- Prefer idempotent Ansible modules over shell commands.
- Include goal-oriented validation tasks where appropriate.
- Syntax-check generated YAML before presenting it for approval.

Tools:

- Existing playbook generation and metadata helpers.
- Ansible syntax-check helper.

### PlaybookEditorAgent

Owns edits to existing registry playbooks.

Responsibilities:

- Only edit playbooks that are already present in the validated registry.
- Preserve required metadata headers.
- Repair failed playbooks based on structured failure diagnosis.
- Syntax-check edited YAML before asking to write changes.

Tools:

- Existing playbook editing helpers.
- Registry validation.
- Ansible syntax-check helper.

### ExecutionAgent

Owns approved playbook execution.

Responsibilities:

- Run only validated registry playbooks.
- Enforce approval for remote-impacting or risky playbooks.
- Perform preflight checks before execution.
- Summarize changed hosts, failed hosts, and failure diagnosis.
- Trigger post-run verification through inspection rather than assuming success.

Tools:

- `ansible_list_playbooks`
- `ansible_run_playbook`
- Future preflight check tools
- Future post-run verification handoff

### FailureRecoveryAgent

Owns recovery after failed execution.

Responsibilities:

- Consume structured Ansible failure diagnosis.
- Decide whether the next step is inspection, playbook editing, prerequisite automation, or stopping with a clear blocker.
- Avoid rerunning the exact same failing playbook without a corrective action.
- Prefer narrow remediation over broad cluster-wide changes.

Tools:

- Read-only inspection handoff.
- Playbook editor handoff.
- Playbook generator handoff for missing prerequisite automation.

### ChangeWriterAgent

Owns repository change lifecycle.

Responsibilities:

- Summarize code/playbook/doc changes.
- Run the repo's preferred validation recipes from `justfile`.
- Fill `.github/pull_request_template.md` completely when opening a PR.
- Document remote dependencies, credentials, and manual verification when automation depends on external systems.

Tools:

- Local Git status/commit tools.
- Validation command runners.
- PR creation tools only when explicitly approved as remote work.

## Suggested Workflow

1. `RequestRouterAgent` classifies the user request.
2. Read-only requests go to `InventoryInspectorAgent`.
3. New automation requests go to `PlaybookGeneratorAgent`.
4. Existing automation requests go to `ExecutionAgent`.
5. Execution failures go to `FailureRecoveryAgent`.
6. Playbook fixes go to `PlaybookEditorAgent`.
7. Repository documentation and PR prep go to `ChangeWriterAgent`.

## Tooling Guidelines

- Do not expose all tools to all agents.
- Do not add a new tool directly to the top-level orchestrator unless it is needed for routing.
- Prefer local inspection tools before remote tools.
- If a tool can mutate remote state, its wrapper should encode approval and risk behavior.
- If a tool has both local and remote modes, default to local mode in development and tests.
- Tool return values should be JSON-serializable plain dict/list/scalar shapes.
- Use `TypedDict` for structured tool results where helpful.
- Avoid returning Pydantic models directly from tool wrappers.

## Risk Model

Use simple risk tiers to guide routing and approval:

- `read_only_local`: local file or registry inspection.
- `read_only_remote`: SSH, HTTP, Kubernetes, or Ansible fact gathering without mutation.
- `local_mutation`: creating or editing local playbooks, docs, tests, or metadata.
- `remote_mutation`: package installs, config changes, service restarts, or playbook execution on remote hosts.
- `disruptive_remote_mutation`: reboots, firewall changes, storage changes, Kubernetes control plane changes, or cluster-wide service changes.
- `destructive`: data deletion, disk formatting, credential rotation, or irreversible cluster changes.

Default behavior:

- `read_only_local`: no approval required.
- `read_only_remote`: explain what will be inspected; approval may be required depending on the repo's remote-work policy.
- `local_mutation`: normal code review and validation.
- `remote_mutation`: explicit approval required.
- `disruptive_remote_mutation`: explicit approval plus rollback or recovery notes required.
- `destructive`: stop unless the user explicitly requested the destructive action and recovery implications are documented.

## Near-Term Implementation Plan

1. Rename the existing `OrchestratorAgent` conceptually into a router role without changing public CLI behavior.
2. Move the current prompt's generation-specific guidance toward `PlaybookGeneratorAgent`.
3. Move execution and retry guidance toward a future `ExecutionAgent` and `FailureRecoveryAgent`.
4. Add a small routing contract type that records:
   - request category
   - risk tier
   - selected agent
   - reason for handoff
   - required approval mode
5. Keep the first implementation incremental: do not add Kubernetes, cloud, or arbitrary shell tooling as part of the initial split.

## Testing Guidance

Add or update deterministic tests only.

Test cases:

- Router classifies a registry lookup as read-only.
- Router classifies a new automation request as playbook generation.
- Router classifies an existing playbook run as execution.
- Router classifies a failed execution diagnosis as failure recovery.
- Remote mutation requests require approval metadata.
- Structured handoff values are JSON-serializable.
- Existing playbook generation and editing tests continue to pass.

Avoid tests that require live remote hosts unless they are explicitly marked as manual verification.

## Open Questions

- Whether specialized agents should be separate classes immediately or introduced first as prompt sections and routing contracts.
- Whether read-only remote inspection should always require approval under this repo's remote-work policy, or whether it can be approved once per run.
- Whether run history should record agent handoffs as first-class events.

## Assumptions

- The first doc-only change does not alter runtime behavior.
- The initial implementation should keep the existing CLI entrypoint.
- The next implementation should avoid adding broad new tool categories until routing and risk boundaries are clearer.
