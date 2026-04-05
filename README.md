# Devops Agent

Figuring out agentic workflows with a Turing Pi cluster.

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
