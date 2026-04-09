# Devops Agent

Figuring out agentic workflows with a Turing Pi cluster.

See `AGENTS.md` for repo-specific guidance on remote tooling, testing expectations, branch naming, and PR writeups.

## Notes

### Roles

#### Control node

- Ansible installed
- SSH access to all CM3 nodes
- Agent runtime
- Observability

#### Agent responsibilities

- Generate playbooks
- Decide when to run them
- React to failures

### Commands

```bash
# install Python and Node test dependencies
uv sync --all-groups
npm install

# run tests
uv run pytest --subprocess-vcr=record

# run only Git HTTP integration tests
uv run pytest -m git_http_integration

# create key for workers
ssh-keygen -t ed25519

# copy to workers (did this with the rpi imager)
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

Git HTTP integration tests use `git-http-mock-server`, which shells out to the system `git`
installation. Run `npm install` before executing `uv run pytest -m git_http_integration`.
