# Agent Notes

## Workflow

- When opening a PR, fill out `.github/pull_request_template.md` completely. Do not leave the summary, validation, infra notes, or risks sections as placeholders.
- Check `Makefile` before running validation or local workflows, and prefer its targets over ad hoc commands when an equivalent target exists.
- Keep control flow top-down and obvious.
- If the design starts to need more than ~2 helpers or ~1 new module, stop and ask first.

## Tools And Remote Boundaries

- Treat anything that reaches outside the local workspace as remote work. That includes Git pushes, PR creation, SSH access, Ansible runs against non-local hosts, cloud APIs, and any hosted service credentials.
- Prefer local inspection first. Read code, inventory, config, playbooks, and tests before running a remote action.
- Document the remote dependency in the PR description when a change depends on credentials, network access, or external systems.
- If a tool has both local and remote modes, make the local path the default in development and tests.

## Setup Expectations

- Python tooling is managed with `uv`. Install dependencies with `uv sync --frozen --all-groups`.
- Git HTTP integration tests also require Node dependencies from `package.json`. Install them with `npm install`.
- The main validation commands in this repo are:
  - `make check`
  - `make test`
  - `make test-git-http`
- Ansible playbooks live under `ansible/playbooks`, and the tool surface exposes a validated playbook registry rather than a plain filename list.
- Checked-in playbooks under `ansible/playbooks` must keep the metadata header fields `name`, `description`, `target`, `requires_approval`, and `tags`, because the registry parser validates them.
- The Ansible tool writes temp files under `.ansible/tmp` so runs do not depend on a system temp directory layout.

## Testing Guidance

- Add or update automated tests only for deterministic, non-agent tools by default.
- Do not add tests for agent behavior unless explicitly requested.
- Do not make tests depend on a live remote system unless the test is explicitly intended as manual verification.
- Prefer real local environments for deterministic tool tests when the setup is lightweight and self-contained, such as temp repos or local mock servers.
- Use `subprocess-vcr` when the realistic local setup is heavier or more fragile, such as Ansible subprocess coverage that depends on local tool installation and host configuration.
- Pytest defaults to replay mode through `addopts`, and `make test` records fixtures intentionally for the subprocess-vcr-backed cases.
- Use the `git_http_integration` marker for Git flows that need a realistic remote without hitting an external host.
- Keep unit tests focused on command construction, argument validation, and error handling for remote-capable tools.
- If a remote workflow cannot be covered in automated tests, add a short manual verification note to the PR description.
