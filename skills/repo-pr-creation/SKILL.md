---
name: repo-pr-creation
description: >-
  Open GitHub pull requests from this devops-agent SSH/control-node checkout.
  Use when the user asks to create, open, publish, or update a PR for this
  repository, especially after local commits are already on a feature branch.
---

# Repo PR Creation

Use this workflow for this repository checkout because the GitHub connector commonly fails here with `Resource not accessible by integration`.

## Workflow

1. Inspect local state first:

```bash
git status -sb
git branch -vv
git remote -v
```

2. Inspect the full branch scope against `origin/main` before renaming the branch or opening the PR. Review the commit list and changed files, not just the latest commit:

```bash
git log --oneline --decorate origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
```

If the branch name is now misleading relative to the full diff, rename it before pushing or creating the PR.

3. If there are uncommitted changes, commit only the intended files before opening the PR.

4. Push the current branch before creating the PR:

```bash
git push -u origin "$(git branch --show-current)"
```

5. Fill out `.github/pull_request_template.md` completely. Do not leave summary, validation, infra notes, or risks as placeholders. Mention remote dependencies when the change depends on credentials, network access, host state, Ansible execution, or external systems.

6. Create a draft PR directly with `gh pr create` from the already-pushed branch. Use explicit arguments:

```bash
gh pr create \
  --repo alysivji/devops-agent \
  --base main \
  --head "$(git branch --show-current)" \
  --title "[codex] <short description>" \
  --body-file /tmp/devops-agent-pr-body.md \
  --draft
```

Use `--body "..."` instead of `--body-file` only for short bodies that still fully complete the PR template.

## Important Boundaries

- Do not try the GitHub connector first from this checkout.
- Do not wrap `gh pr create` in inline token extraction or an inline `GH_TOKEN=...` shell assignment. Use the direct `gh pr create` shape above.
- Do not use `gh --fill` because this repo expects the PR template to be completed deliberately.
- If `gh pr edit` fails on GitHub GraphQL project-card fields, update the PR body through the REST path instead:

```bash
gh api repos/alysivji/devops-agent/pulls/<number> \
  -X PATCH \
  -F body=@/tmp/devops-agent-pr-body.md
```

## Validation Note

Prefer `justfile` recipes before PR creation. For the main validation path, use:

```bash
just check
```
