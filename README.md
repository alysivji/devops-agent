# Devops Agent

Figuring out agentic workflows with a Turing Pi cluster.

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

## Human-In-The-Loop Playbook Generation

The first generation workflow supports these inventory targets:

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
uv run python -m agent.main "create a hello world playbook for local nodes"
```

The generated review includes the proposed filename, metadata header fields, and the full YAML before asking for approval.

### Commands

```bash
# install Python and Node test dependencies
uv sync --frozen --all-groups
npm install

# run tests
make test

# run only Git HTTP integration tests
make test-git-http

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
pattern, and `make test` records those fixtures while pytest replays them by default.

Git HTTP integration tests use `git-http-mock-server`, which shells out to the system `git`
installation. Run `npm install` before executing `make test-git-http`.

## Setup

`./scripts/setup-dev.sh` creates a local `.env` only when one does not already exist. In a linked
worktree, it prefers copying the main worktree's `.env`; otherwise it falls back to `.env.example`.
