# Agent Notes

## Workflow

- When opening a PR, fill out `.github/pull_request_template.md` completely. Do not leave the summary, validation, infra notes, or risks sections as placeholders.

## Tools And Remote Boundaries

- Treat anything that reaches outside the local workspace as remote work. That includes Git pushes, PR creation, SSH access, Ansible runs against non-local hosts, cloud APIs, and any hosted service credentials.
- Prefer local inspection first. Read code, inventory, config, playbooks, and tests before running a remote action.
- Document the remote dependency in the PR description when a change depends on credentials, network access, or external systems.
- If a tool has both local and remote modes, make the local path the default in development and tests.

## Setup Expectations

- Python tooling is managed with `uv`. Install dependencies with `uv sync --frozen --all-groups`.
- Git HTTP integration tests also require Node dependencies from `package.json`. Install them with `npm install`.
- The main validation commands in this repo are:
  - `uv run pre-commit run --all-files`
  - `uv run mypy`
  - `uv run pytest`
  - `uv run pytest --subprocess-vcr=record`
  - `uv run pytest -m git_http_integration`
- Ansible playbooks live under `ansible/playbooks`, and the tool surface exposes a validated playbook registry rather than a plain filename list.
- Checked-in playbooks under `ansible/playbooks` must keep the metadata header fields `name`, `description`, `target`, `requires_approval`, and `tags`, because the registry parser validates them.
- The Ansible tool writes temp files under `.ansible/tmp` so runs do not depend on a system temp directory layout.

## Testing Guidance

- Do not make tests depend on a live remote system unless the test is explicitly intended as manual verification.
- For subprocess-driven integrations, prefer recorded fixtures with `subprocess-vcr` so tests remain deterministic.
- Pytest defaults to replay mode through `addopts`, so use `--subprocess-vcr=record` only when intentionally updating fixtures.
- Use the `git_http_integration` marker for Git flows that need a realistic remote without hitting an external host.
- Keep unit tests focused on command construction, argument validation, and error handling for remote-capable tools.
- If a remote workflow cannot be covered in automated tests, add a short manual verification note to the PR description.
