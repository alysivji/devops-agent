# Devops Agent

Figuring out agentic DevOps tooling with a Turing Pi cluster.

See `AGENTS.md` for repo-specific guidance on remote tooling, testing expectations, and PR writeups.

## Notes

### Roles

#### Control node

- Intel i5-6500T
- 16GB DDR4 RAM
- Ansible installed
- SSH access to all Raspberry Pi Compute Module 3+ cluster nodes
- Agent runtime
- Control plane and control panel services
- Observability sink and supporting management services

#### Cluster nodes

- Raspberry Pi Compute Module 3+
- 1.2GHz CPU
- 1GB LPDDR2 SDRAM
- 32GB eMMC storage
- Intended for distributed workloads and Kubernetes containers

#### Agent responsibilities

- Generate playbooks
- Decide when to run them
- React to failures
- Route host/substrate work to Ansible and schedulable app workloads to Helm/Kubernetes

## Human-In-The-Loop Playbook Generation

Ansible playbook generation is for host/substrate automation, node-local durable
services, and cluster prerequisites such as k3s, kubeconfig, and Helm
installation. Ephemeral or schedulable application workloads should use the
Helm/Kubernetes tool path instead. For stateful services such as Postgres,
MinIO, or logging, choose the workflow based on lifecycle and storage ownership:
host-managed durable services belong in Ansible, while cluster-managed workloads
belong in Helm/Kubernetes.

For Kubernetes application desired state, prefer repo-owned Helm charts under
`helm/charts/` when the user asks to create or store deployable artifacts. The
agent exposes a chart registry for that directory, similar to the Ansible
playbook registry. Use live Helm install/upgrade only when the user asks to
apply the workload to the cluster. Existing charts are edited through a
chart-aware agent that can update values, templates, helpers, and related files
together before running Helm lint.

Kubernetes and Helm failure handling is also available as a Strands skill under
`skills/kubernetes-troubleshooting/`; the orchestrator loads repo skills via the
Strands `AgentSkills` plugin.

The first generation tool supports these inventory targets:

- `control` for local playbooks
- `cluster` for remote playbooks over SSH
- `both` for playbooks that include work on both host groups

The agent now generates an Ansible playbook from a natural-language prompt, drafts metadata for the playbook header, shows a structured review, and asks for explicit yes/no approval before creating any file in `ansible/playbooks/`.

### Draft metadata

Every playbook metadata header must include:

- `name`
- `description`
- `target`
- `requires_approval`
- `tags`

`requires_approval` records whether a human should approve execution before the playbook is run. Use `requires_approval: true` when the playbook should not be executed without explicit review.

### Model

Set `OPENAI_MODEL=gpt-5.4` by default for stronger reasoning and coding quality. If you need a lower-cost option, use `gpt-5.4-mini`.

### Example

```bash
uv run devops-agent "create a hello world playbook for local nodes"
uv run devops-agent "Install a k3s cluster with a single control plane on the control node and all cluster nodes joining as workers."
uv run devops-agent "Install Helm"
uv run devops-agent "deploy nginx to Kubernetes with Helm"
```

The generated review includes the proposed filename, metadata header fields, and the full YAML before asking for approval.

## Run History

CLI runs capture a machine-readable run history by default and append each completed session to `docs/autonomous-devops-run-history.jsonl`.

Run history includes:

- the initial prompt
- major decisions and operational why text
- tool usage summaries
- approval and decline outcomes
- success and failure summaries

Run history does not include:

- hidden reasoning
- full raw model transcripts
- full rendered playbook YAML bodies in the history artifact
- unredacted values for fields that look like secrets, tokens, passwords, or keys

Disable run history by setting `DEVOPS_AGENT_RUN_HISTORY_ENABLED=false`.

Human-readable talk generation is intentionally deferred. This first pass writes only the JSONL artifact.

## Strands Session Storage

The JSONL run history remains a compact summary and audit artifact. Optional
Strands session storage persists the agent's messages and state for object-level
inspection and future backend experiments. It is disabled by default.

For local S3-compatible storage, point the session backend at a reachable MinIO
or S3-compatible endpoint. The control-node MinIO service listens on
`http://127.0.0.1:9000` for S3 API calls and serves the browser console at
`http://127.0.0.1:9001`.

Use these `.env` values for local MinIO exploration, replacing the bucket and
credentials with values provisioned on the MinIO server:

```bash
DEVOPS_AGENT_SESSION_BACKEND=s3
DEVOPS_AGENT_SESSION_S3_BUCKET=devops-agent-sessions
DEVOPS_AGENT_SESSION_S3_PREFIX=local/
DEVOPS_AGENT_SESSION_S3_REGION=us-east-1
DEVOPS_AGENT_SESSION_S3_ENDPOINT_URL=http://127.0.0.1:9000
MINIO_ROOT_USER=<minio-access-key>
MINIO_ROOT_PASSWORD=<minio-secret-key>
```

The session S3 credentials default to `MINIO_ROOT_USER` and
`MINIO_ROOT_PASSWORD` for local MinIO. Use
`DEVOPS_AGENT_SESSION_S3_ACCESS_KEY_ID` and
`DEVOPS_AGENT_SESSION_S3_SECRET_ACCESS_KEY` only when the session store should
use different credentials from the MinIO service.

Each CLI invocation creates a new Strands session. When run history is enabled,
the S3 session ID matches the JSONL `run_id`, so objects appear under keys like
`local/session_<run_id>/`.

Pass `--session-id` to choose the Strands session ID explicitly:

```bash
uv run devops-agent --session-id support-session "create a hello world playbook for local nodes"
```

When `--session-id` is set, run history still writes its own `run_id`; the
Strands session objects use the CLI-provided session ID.

Other S3-compatible providers can use the same session settings with different
credentials, bucket, prefix, region, and endpoint URL. Example endpoints:

- MinIO: `http://127.0.0.1:9000`
- Cloudflare R2: `https://<account-id>.r2.cloudflarestorage.com`
- Google Cloud Storage S3-compatible/XML API: `https://storage.googleapis.com`

The session storage credentials need object read/write/delete and list access:
`s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, and `s3:ListBucket`.

Live S3-compatible storage is optional local infrastructure. Default tests do
not require MinIO or cloud credentials.

### Commands

```bash
# install Python and Node test dependencies
just install

# run tests
just test

# run only Git HTTP integration tests
just test-git-http

# create key for cluster nodes
ssh-keygen -t ed25519

# copy to cluster nodes (did this with the rpi imager)
ssh-copy-id pi@worker-1

# copy key to control box
ssh-copy-id -f -i ~/.ssh/turingpi.pub control

# bootstrap control node
# ssh onto node
# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# install ansible
uv tool install ansible-core --with ansible

# create Fine Grained Personal Access Token with ability to create PR
# https://github.com/settings/personal-access-tokens/
```

## Testing

Prefer real local test environments when they are cheap to stand up. In this repo,
the Git tool tests run against temp repositories and the local HTTP mock server
instead of recorded subprocess fixtures.

Use `subprocess-vcr` for subprocess-heavy paths that are harder to make portable
across developer machines. The Ansible execution coverage currently follows that
pattern, and `just test` records those fixtures while pytest replays them by default.

Git HTTP integration tests use `git-http-mock-server`, which shells out to the system `git`
installation. Run `just install` before executing `just test-git-http`.

## Setup

`./scripts/setup-dev.sh` creates a local `.env` only when one does not already exist. In a linked
worktree, it prefers copying the main worktree's `.env`; otherwise it falls back to `.env.example`.
