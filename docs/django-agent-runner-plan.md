# Django Agent Runner Plan

## Current State

The agent currently runs from the command line as a single synchronous workflow:

```text
CLI prompt -> OrchestratorAgent.run(prompt) -> synchronous tools -> final CLI response
```

The CLI now also supports optional Strands session storage. A run can choose a stable Strands `session_id`, and the existing run-history path records the configured session details when storage is enabled. Reusing that `session_id` lets the agent load prior messages and state through the Strands session manager.

The tool layer includes blocking subprocess work, including Ansible and Git commands. It also contains terminal-centric interactions such as `input()` approval prompts and `print()` previews for generated or edited playbooks. That works for the CLI, but it does not map cleanly to web or chat channels where requests need to return quickly and user approval may happen later.

The important split for Django is:

- Strands session storage owns model/session continuity.
- Django owns product workflow state, approvals, locks, job visibility, and UI.
- JSONL run history remains a compact audit artifact, not the primary resume mechanism.

## Target Direction

Django should become the service framework around the existing agent package:

```text
Django web chat
  -> AgentWorkflow(session_id, state)
  -> AgentJob
  -> Celery worker
  -> OrchestratorAgent(session_id=workflow.session_id)
  -> existing agent/tools
```

Django owns the web UI, persisted workflow state, approval UI, locking, and job visibility. Strands owns persisted agent messages and state. Celery owns long-running execution. The existing `devops_bot` CLI and agent/tool modules remain the core execution path.

## First Slice

The first implementation slice should lock these choices:

- Django web chat first.
- SQLite first.
- Celery + Redis for background jobs.
- Local-only no-login web UI.
- Existing CLI remains supported.
- Persist one Strands `session_id` per workflow.
- Resume continuation jobs by reusing the same Strands `session_id`.
- Use the existing S3-compatible Strands session storage path first.
- No Slack or WhatsApp in the first slice.
- No git worktree parallelism in the first slice.

## Execution Model

HTTP requests must not run the agent directly. A request should create durable state, enqueue work, and return or render a job page.

```text
POST prompt
  -> create workflow/job row
  -> enqueue Celery task
  -> return/render job page

Celery worker
  -> runs OrchestratorAgent(session_id=workflow.session_id).run(prompt)
  -> records events/state
  -> marks job completed, failed, or waiting_for_approval
```

Synchronous `subprocess.run(...)` can remain inside tools for now because that work runs in Celery, not in the Django request path.

Continuation jobs should not reconstruct the model transcript themselves. They should reuse the workflow's Strands `session_id` and pass a compact continuation prompt or control message that identifies the approved pending action. This gives a restartable process-level workflow while letting Strands reload the prior agent context.

This is still a new invocation, not Python call-stack suspension. Any approval-required tool path must stop cleanly, persist the approval request, and let the next Celery job continue using the same session.

## State Model

The initial durable concepts should be:

- `AgentWorkflow`, or the final chosen name for the top-level unit.
- `AgentJob`.
- `AgentEvent`.
- `PendingApproval`.

`AgentWorkflow` should include:

- `session_id`: the stable Strands session ID used for all jobs in the workflow.
- `status`: the workflow state.
- `initial_prompt`: the user's original request.
- Optional session metadata such as backend and storage prefix for debugging.

`AgentJob` should include the workflow, attempt/sequence number, job kind, submitted prompt or continuation payload, Celery task ID, timestamps, and terminal result details.

The top-level naming decision is still open. Candidate names:

- `AgentWorkflow`
- `AgentRun`
- `AgentSession`

Recommendation: use `AgentWorkflow`, because one workflow can include multiple jobs and one or more Strands sessions. Avoid using `AgentSession` for the top-level Django model unless the product semantics truly match Strands sessions; otherwise the name will be overloaded.

## Approval Model

Approval should be a persisted workflow state, not terminal `input()` and not literal Python call-stack suspension.

```text
worker reaches approval-required action
  -> persist PendingApproval
  -> mark workflow waiting_for_approval
  -> stop current job

user clicks approve
  -> mark approval approved
  -> create continuation job
  -> Celery re-invokes OrchestratorAgent with the same Strands session_id
  -> approved action continues through the tool approval gate
```

The continuation should use the workflow row, the approved action payload, and the stable Strands session ID. This gives the product behavior of pause and resume without relying on a Celery worker process staying blocked in memory.

The approval tool path should become non-terminal. Instead of `input()`, it should call an approval service that can:

- Return approved immediately when the matching `PendingApproval` has already been approved.
- Persist a new `PendingApproval` and raise a controlled pause signal when approval is needed.
- Return declined or raise a controlled denial when the user rejects the approval.

## Why `contextvars` Here

The current agent package now has two different kinds of state:

- Durable workflow state that should live in Django models and queues.
- Execution-local services needed by shared agent/tool code while one run is active.

The execution-local part is where `contextvars` fits. Shared functions such as the playbook and Helm tools, plus orchestrator hooks, are invoked from framework-managed call paths and do not naturally receive a workflow/runtime object as an argument. A `ContextVar` gives those functions access to the current run's approval service and event sink without falling back to a process-global singleton.

This is specifically not a persistence mechanism and not a replacement for Django tables or Strands session storage:

- Django should persist workflow rows, jobs, approvals, and UI-visible state.
- Strands should persist model/session state in the S3-compatible session store.
- `contextvars` should hold only execution-local services for the active Python run.

This matters even if today's terminal path feels single-threaded. Module globals break once the runtime moves behind Django/Gunicorn, starts serving overlapping requests, or uses async streaming for partial replies. `ContextVar` values track the active execution context, including async task context, rather than only OS thread identity.

References:

- Python `contextvars`: https://docs.python.org/3/library/contextvars.html
- PEP 567: https://peps.python.org/pep-0567/

## State Machine Shape

The Django side should have an explicit state machine, even if the first implementation is a small model/service layer instead of a third-party workflow engine.

Initial workflow states:

```text
queued -> running -> completed
queued -> running -> failed
queued -> running -> waiting_for_approval -> queued -> running -> completed
queued -> running -> waiting_for_approval -> failed
queued -> canceled
waiting_for_approval -> canceled
```

State transitions should be the only place that creates continuation jobs, records approval decisions, and releases or acquires the single-active-workflow lock. If this grows beyond a few model methods, choose a lightweight Django state-machine library before adding more ad hoc flags.

## Concurrency Constraint

The first implementation has a hard constraint:

```text
Only one active agent workflow may run at a time.
```

An active workflow is any workflow in one of these states:

```text
queued | running | waiting_for_approval
```

When a new prompt is submitted while another active workflow exists, Django should reject the new submission or show the active workflow instead. The recommended first behavior is to reject the new submission with a clear message and link to the active workflow.

This constraint is important because:

- Current tools can mutate local files.
- Current tools can run git commands.
- Current tools can run Ansible against shared hosts.
- One workspace means concurrent workflows can interfere with each other.
- Strands session storage preserves agent context, but it does not isolate filesystem or infrastructure side effects.

## Session Storage Path

For the first Django slice, use the existing Strands S3-compatible session manager as the canonical agent session store. Django should generate and persist the `session_id` when the workflow is created, pass it into every `OrchestratorAgent` invocation, and expose the session ID on the workflow detail page for debugging.

Django should not need to store full model transcripts in relational tables for the first slice. Relational state should cover indexable product data: workflow status, jobs, approvals, events, created timestamps, final summaries, and error details.

For future multi-session agents, add a child model such as `WorkflowAgentSession` only when needed:

- `workflow`
- `agent_role`
- `session_id`
- `backend`
- `storage_prefix`
- `status`

That keeps the first slice simple while leaving room for multiple coordinated agents later. A more robust session store is only needed when the product needs indexed session metadata, per-agent session lifecycle management, or cross-workflow session queries beyond what the Strands object store provides.

## Future Worktree-Based Parallelism

Git worktrees are the likely path to multiple simultaneous agent workflows later.

```text
one workflow -> one isolated git worktree -> one worker execution context
```

Important future requirements:

- Allocate a worktree per workflow.
- Persist the worktree path on the workflow.
- Keep Strands session IDs tied to the workflow, not the worktree path.
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
- No redesign of the agent's core orchestration prompt beyond what is needed for persisted approvals.
- No custom multi-agent session store unless the single-session Strands workflow proves too limited.

## Open Naming Decision

The top-level workflow name is not fully decided yet. Use `AgentWorkflow` as the recommended placeholder in the first implementation because it describes the unit that can span an initial job, a waiting approval, and one or more continuation jobs. Store the Strands identifier as `session_id` on that model.

The final naming decision should be made before adding Django models so migrations do not churn.

## Validation

For this doc-only change, validation is:

```bash
git diff --check
```

No test suite is required unless implementation code changes too.

## Assumptions

- This planning doc is intended to guide later implementation rather than implement Django now.
- The top-level workflow name is not fully decided yet; use `AgentWorkflow` as the recommended placeholder.
- The first implementation must serialize active workflows, even though git worktrees are expected to unlock parallelism later.
- Strands session storage can reload agent context for a restarted job, but Django still needs a workflow state machine for approvals, locking, and UI state.
