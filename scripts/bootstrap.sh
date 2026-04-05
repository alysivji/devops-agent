#!/usr/bin/env bash
# Intended path in devops-agent: scripts/bootstrap-env.sh
# Creates .env from .env.example and sets GH_TOKEN (same env var gh uses; refuses if .env already exists).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXAMPLE=".env.example"
TARGET=".env"

if [[ ! -f "$EXAMPLE" ]]; then
  echo "error: missing $EXAMPLE (run from repo root or keep this script in scripts/)" >&2
  exit 1
fi

if [[ -f "$TARGET" ]]; then
  echo "error: $TARGET already exists; remove it first if you want a fresh file." >&2
  exit 1
fi

TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [[ -z "$TOKEN" && -n "${1:-}" ]]; then
  TOKEN="$1"
fi

if [[ -z "$TOKEN" ]]; then
  echo "usage: GH_TOKEN=... ${0##*/}" >&2
  echo "   or: GITHUB_TOKEN=... ${0##*/}  (legacy)" >&2
  echo "   or: ${0##*/} <token>" >&2
  exit 1
fi

cp "$EXAMPLE" "$TARGET"
chmod 600 "$TARGET"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
wrote=false
while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" == GH_TOKEN=* ]] || [[ "$line" == GITHUB_TOKEN=* ]]; then
    if [[ "$wrote" == false ]]; then
      printf 'GH_TOKEN=%s\n' "$TOKEN"
      wrote=true
    fi
  else
    printf '%s\n' "$line"
  fi
done <"$TARGET" >"$tmp"
if [[ "$wrote" == false ]]; then
  printf 'GH_TOKEN=%s\n' "$TOKEN" >>"$tmp"
fi
mv "$tmp" "$TARGET"
trap - EXIT

echo "wrote $ROOT/$TARGET (mode 600)"
