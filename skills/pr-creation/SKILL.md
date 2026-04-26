---
name: pr-creation
description: >-
  Create, open, publish, or update a GitHub pull request from this
  devops-agent checkout. Use whenever the user asks to create a PR for this
  repository, including branch rename, push, and `gh pr create` fallback from
  the current branch.
---

# PR Creation

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

Rename is required when any of these are true:

- the branch name reflects exploratory or stale work such as `inspect-*`, `tmp-*`, `wip-*`, or `debug-*`
- the branch name no longer matches the requested scope or the actual branch diff
- the branch includes multiple commits whose combined scope is broader than the current branch name suggests

When renaming, default to a lowercase kebab-case slug derived from the requested change scope unless the user explicitly provided a branch name. Rename locally before any push:

```bash
git branch -m <new-branch-name>
```

3. If there are uncommitted changes, commit only the intended files before opening the PR.

4. Push the current branch only after the branch name is correct:

```bash
git push -u origin "$(git branch --show-current)"
```

5. Choose a PR title that makes sense to reviewers scanning the PR list or merge history without local branch context. The PR title and branch name serve different purposes.

Use these title rules:

- do not default the PR title to the branch name
- prefer a reviewer-facing description of the user-visible or operational change
- use a user-provided title only if it is already clear and reviewer-friendly
- if the provided title is vague, stale, or branch-shaped, replace it with a clearer title that matches the actual diff

Good PR titles should still make sense to someone reading the merge list six months later.

6. Fill out `.github/pull_request_template.md` completely. Do not leave summary, validation, infra notes, or risks as placeholders. Mention remote dependencies when the change depends on credentials, network access, host state, Ansible execution, or external systems.

7. Create a draft PR directly with `gh pr create` from the already-pushed branch. Use explicit arguments:

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
- Do not push a stale exploratory branch name just because the branch already exists locally. Rename first when the name is misleading.
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
