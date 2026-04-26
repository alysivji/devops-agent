#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXAMPLE=".env.example"
TARGET=".env"
KWOK_VERSION="${KWOK_VERSION:-v0.7.0}"
KWOK_INSTALL_DIR="${KWOK_INSTALL_DIR:-$HOME/.local/bin}"
GIT_COMMON_DIR="$(git rev-parse --git-common-dir)"
MAIN_WORKTREE="$(cd "$GIT_COMMON_DIR/.." && pwd)"
MAIN_ENV="$MAIN_WORKTREE/$TARGET"

install_kwok_binary() {
  local binary="$1"
  local os="$2"
  local arch="$3"
  local destination="$KWOK_INSTALL_DIR/$binary"

  mkdir -p "$KWOK_INSTALL_DIR"
  curl -fsSL \
    "https://github.com/kubernetes-sigs/kwok/releases/download/${KWOK_VERSION}/${binary}-${os}-${arch}" \
    -o "$destination"
  chmod +x "$destination"
  echo "installed $binary $KWOK_VERSION to $destination"
}

ensure_kwok() {
  if command -v kwok >/dev/null 2>&1 && command -v kwokctl >/dev/null 2>&1; then
    return
  fi

  if command -v brew >/dev/null 2>&1; then
    if brew install kwok; then
      return
    fi
    echo "brew install kwok failed; falling back to pinned release binaries" >&2
  fi

  local os
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  local arch
  case "$(uname -m)" in
    x86_64 | amd64)
      arch="amd64"
      ;;
    arm64 | aarch64)
      arch="arm64"
      ;;
    *)
      echo "error: unsupported architecture for KWOK install: $(uname -m)" >&2
      exit 1
      ;;
  esac

  case "$os" in
    darwin | linux)
      install_kwok_binary "kwok" "$os" "$arch"
      install_kwok_binary "kwokctl" "$os" "$arch"
      ;;
    *)
      echo "error: unsupported OS for KWOK install: $os" >&2
      exit 1
      ;;
  esac

  if [[ ":$PATH:" != *":$KWOK_INSTALL_DIR:"* ]]; then
    echo "note: add $KWOK_INSTALL_DIR to PATH to use kwok and kwokctl from new shells"
  fi
}

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

if ! command -v just >/dev/null 2>&1; then
  echo "error: just is required. Install it first, for example with: brew install just" >&2
  exit 1
fi

just install

ensure_kwok
