# Agent Notes

## Workflow

- When the user asks to create, open, publish, or update a PR for this repository, use the local `$pr-creation` skill.
- When opening a PR, fill out `.github/pull_request_template.md` completely. Do not leave the summary, validation, infra notes, or risks sections as placeholders.
- Check `justfile` before running validation or local workflows, and prefer its recipes over ad hoc commands when an equivalent recipe exists.
- Keep control flow top-down and obvious.
- Prefer the smallest obvious implementation over extensible design. Optimize for readability by a future human maintainer, not reuse.
- If the design starts to need more than ~2 helpers or ~1 new module, stop and ask first.

## Tools And Remote Boundaries

- Treat anything that reaches outside the local workspace as remote work. That includes Git pushes, PR creation, SSH access, Ansible runs against non-local hosts, cloud APIs, and any hosted service credentials.
- Prefer local inspection first. Read code, inventory, config, playbooks, and tests before running a remote action.
- Document the remote dependency in the PR description when a change depends on credentials, network access, or external systems.
- If a tool has both local and remote modes, make the local path the default in development and tests.
- When opening a PR from the SSH/control-node checkout, use the documented `gh pr create` fallback directly from the already-pushed branch with explicit `--base`, `--head`, `--title`, `--body`, and `--draft`. Do not try the GitHub connector first from this checkout, because it commonly fails with `Resource not accessible by integration`. If `gh pr edit` fails on GitHub GraphQL project-card fields, update the PR body with the REST path instead, for example `gh api repos/<owner>/<repo>/pulls/<number> -X PATCH -f body=...`.
- For structured `@tool` results, keep the returned runtime value JSON-serializable with plain dict/list/scalar shapes. Use `TypedDict` to document those shapes when helpful, and avoid returning Pydantic models or other objects directly through tool wrappers.
- Use untracked `.env` files for local secret values. Commit only placeholder examples such as `.env.example`, document the required variable names, and make Ansible playbooks fail fast with an early `assert` when a required environment variable is missing. Do not commit real secret values in playbooks, inventories, docs, or environment examples.

## Setup Expectations

- Python tooling is managed with `uv`. Install dependencies with `uv sync --frozen --all-groups`.
- Git HTTP integration tests also require Node dependencies from `package.json`. Install them with `npm install`.
- Helm/Kubernetes integration tests use KWOK with local Docker, Helm, kubectl, and kwokctl. `./scripts/setup-dev.sh` installs KWOK for local development; CI installs the pinned tool versions directly.
- The main validation commands in this repo are:
  - `just check`
  - `just test`
  - `just test-git-http`
- Ansible playbooks live under `ansible/playbooks`, and the tool surface exposes a validated playbook registry rather than a plain filename list.
- Checked-in playbooks under `ansible/playbooks` must keep the metadata header fields `name`, `description`, `target`, `requires_approval`, and `tags`, because the registry parser validates them.
- The Ansible tool writes temp files under `.ansible/tmp` so runs do not depend on a system temp directory layout.

## Testing Guidance

- Add or update automated tests only for deterministic, non-agent tools by default.
- Do not add tests for agent behavior unless explicitly requested.
- Do not make tests depend on a live remote system unless the test is explicitly intended as manual verification.
- Prefer real local environments for deterministic tool tests when the setup is lightweight and self-contained, such as temp repos or local mock servers.
- Use `subprocess-vcr` when the realistic local setup is heavier or more fragile, such as Ansible subprocess coverage that depends on local tool installation and host configuration.
- Use `pytest-vcr` for HTTP-based tool tests when the client library is compatible with VCR interception and the upstream endpoint is stable enough for recorded replay.
- If the HTTP client is not VCR-interceptable, keep the networked wrapper deterministic with local unit tests at the library boundary instead of forcing live HTTP into the suite.
- Pytest defaults to replay mode through `addopts`, and `just test` records fixtures intentionally for the subprocess-vcr-backed cases.
- Use the `git_http_integration` marker for Git flows that need a realistic remote without hitting an external host.
- Use the `kwok_integration` marker for Helm/Kubernetes flows that need real Kubernetes API objects without touching the live k3s cluster. Prefer KWOK-backed local coverage over live remote-cluster tests for these tool wrappers.
- Keep unit tests focused on command construction, argument validation, serialization shape, and error handling for remote-capable tools.
- When adding structured tool outputs, add typing that reflects the actual serialized shape exposed to the model runtime.
- If a remote workflow cannot be covered in automated tests, add a short manual verification note to the PR description.
