# Django Agent Runner Plan

## Current State

The agent currently runs from the command line as a single synchronous workflow:

```text
CLI prompt -> OrchestratorAgent.run(prompt) -> synchronous tools -> final CLI response
```

The tool layer includes blocking subprocess work, including Ansible and Git commands. It also
contains terminal-centric interactions such as `input()` approval prompts and `print()` previews
for generated or edited playbooks. That works for the CLI, but it does not map cleanly to web or
chat channels where requests need to return quickly and user approval may happen later.

## Target Direction

Django should become the service framework around the existing agent package:

```text
Django web chat -> persisted workflow/job -> Celery worker -> existing agent/tools
```

Django owns the web UI, persisted state, approval UI, and job visibility. Celery owns long-running
execution. The existing `devops_bot` CLI and agent/tool modules remain the core execution path.

## First Slice

The first implementation slice should lock these choices:

- Django web chat first.
- SQLite first.
- Celery + Redis for background jobs.
- Local-only no-login web UI.
- Existing CLI remains supported.
- No Slack or WhatsApp in the first slice.
- No git worktree parallelism in the first slice.

## Execution Model

HTTP requests must not run the agent directly. A request should create durable state, enqueue work,
and return or render a job page.

```text
POST prompt
  -> create workflow/job row
  -> enqueue Celery task
  -> return/render job page

Celery worker
  -> runs OrchestratorAgent.run(prompt)
  -> records events/state
  -> marks job completed, failed, or waiting_for_approval
```

Synchronous `subprocess.run(...)` can remain inside tools for now because that work runs in Celery,
not in the Django request path.

## State Model

The initial durable concepts should be:

- `AgentWorkflow`, or the final chosen name for the top-level unit.
- `AgentJob`.
- `AgentEvent`.
- `PendingApproval`.

The top-level naming decision is still open. Candidate names:

- `AgentWorkflow`
- `AgentRun`
- `AgentSession`

Recommendation: use `AgentWorkflow`, because one workflow can include multiple jobs when an
approval continuation is needed.

## Approval Model

Approval should be a persisted workflow state, not terminal `input()` and not literal Python
call-stack suspension.

```text
worker reaches approval-required action
  -> persist PendingApproval
  -> mark workflow waiting_for_approval
  -> stop current job

user clicks approve
  -> mark approval approved
  -> create continuation job
  -> Celery resumes from persisted workflow context
```

The continuation should use saved workflow context plus the approved action. This gives the product
behavior of pause and resume without relying on a Celery worker process staying blocked in memory.

## Concurrency Constraint

The first implementation has a hard constraint:

```text
Only one active agent workflow may run at a time.
```

An active workflow is any workflow in one of these states:

```text
queued | running | waiting_for_approval
```

When a new prompt is submitted while another active workflow exists, Django should reject the new
submission or show the active workflow instead. The recommended first behavior is to reject the new
submission with a clear message and link to the active workflow.

This constraint is important because:

- Current tools can mutate local files.
- Current tools can run git commands.
- Current tools can run Ansible against shared hosts.
- One workspace means concurrent workflows can interfere with each other.

## Future Worktree-Based Parallelism

Git worktrees are the likely path to multiple simultaneous agent workflows later.

```text
one workflow -> one isolated git worktree -> one worker execution context
```

Important future requirements:

- Allocate a worktree per workflow.
- Persist the worktree path on the workflow.
- Run agent/tools with that worktree as the current working directory.
- Add a cleanup and retention policy.
- Add locking for shared remote targets, because worktrees isolate files but not infrastructure.
- Keep Ansible target concurrency separate from git and workspace concurrency.

## Non-Goals For First Slice

- No Slack integration.
- No WhatsApp integration.
- No public internet deployment.
- No Postgres migration.
- No multi-workflow concurrency.
- No worktree allocator.
- No streaming subprocess output unless it falls out naturally from event polling.
- No redesign of the agent's core orchestration prompt beyond what is needed for persisted
  approvals.

## Open Naming Decision

The top-level workflow name is not fully decided yet. Use `AgentWorkflow` as the recommended
placeholder in the first implementation because it describes the unit that can span an initial job,
a waiting approval, and one or more continuation jobs.

The final naming decision should be made before adding Django models so migrations do not churn.

## Validation

For this doc-only change, validation is:

```bash
git diff --check
```

No test suite is required unless implementation code changes too.

## Assumptions

- This planning doc is intended to guide later implementation rather than implement Django now.
- The top-level workflow name is not fully decided yet; use `AgentWorkflow` as the recommended
  placeholder.
- The first implementation must serialize active workflows, even though git worktrees are expected
  to unlock parallelism later.
