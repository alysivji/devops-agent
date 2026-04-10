#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXAMPLE=".env.example"
TARGET=".env"

if [[ ! -f "$EXAMPLE" ]]; then
  echo "error: missing $EXAMPLE (run from repo root or keep this script in scripts/)" >&2
  exit 1
fi

if [[ ! -f "$TARGET" ]]; then
  cp "$EXAMPLE" "$TARGET"
  chmod 600 "$TARGET"
  echo "wrote $ROOT/$TARGET (mode 600)"
fi

make install
