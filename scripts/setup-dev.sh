#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXAMPLE=".env.example"
TARGET=".env"
GIT_COMMON_DIR="$(git rev-parse --git-common-dir)"
MAIN_WORKTREE="$(cd "$GIT_COMMON_DIR/.." && pwd)"
MAIN_ENV="$MAIN_WORKTREE/$TARGET"

if [[ ! -f "$EXAMPLE" ]]; then
  echo "error: missing $EXAMPLE (run from repo root or keep this script in scripts/)" >&2
  exit 1
fi

if [[ ! -f "$TARGET" ]]; then
  SOURCE="$EXAMPLE"
  if [[ -f "$MAIN_ENV" && "$MAIN_ENV" != "$ROOT/$TARGET" ]]; then
    SOURCE="$MAIN_ENV"
  fi

  cp "$SOURCE" "$TARGET"
  chmod 600 "$TARGET"
  echo "wrote $ROOT/$TARGET from $SOURCE (mode 600)"
fi

make install
