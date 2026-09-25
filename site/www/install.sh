#!/bin/sh
# Cartographer installer · https://codecartographer.dev
#
#   curl -fsSL https://codecartographer.dev/install.sh | sh
#   curl -fsSL https://codecartographer.dev/install.sh | sh -s -- --all      # also Codex CLI and Cursor
#   curl -fsSL https://codecartographer.dev/install.sh | sh -s -- --auto     # map sessions automatically when they end
#
# What it does: downloads Cartographer into ~/.cartographer/app, links ~/.local/bin/cartographer,
# and puts /wrap, /replay, /complete and /cartographer-setup into Claude Code (~/.claude/skills).
# Nothing runs in the background unless you pass --auto. Nothing leaves your machine.
# Needs: python3 (3.9 or newer). Uses curl, or git as a fallback.
set -eu

SITE="${CARTOGRAPHER_SITE:-https://codecartographer.dev}"
REPO="${CARTOGRAPHER_REPO:-https://github.com/situatedstrategies/cartographer}"
AGENTS="claude-code"
EXTRA=""
for arg in "$@"; do
  case "$arg" in
    --all) AGENTS="all" ;;
    --auto|--manual) EXTRA="$EXTRA $arg" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (try --all, --auto, --manual)" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }
fail() { printf '\ncartographer install: %s\n' "$1" >&2; exit 1; }

PY="$(command -v python3 || true)"
[ -n "$PY" ] || fail "python3 is required (3.9 or newer). macOS: run 'xcode-select --install' or 'brew install python'. Linux: your package manager."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || fail "found $("$PY" -V 2>&1); Python 3.9 or newer is required."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
say "Downloading Cartographer"
if [ -n "${CARTOGRAPHER_TARBALL:-}" ]; then
  tar -xzf "$CARTOGRAPHER_TARBALL" -C "$TMP"
elif command -v curl >/dev/null && curl -fsSL "$SITE/cartographer.tar.gz" -o "$TMP/cartographer.tar.gz"; then
  tar -xzf "$TMP/cartographer.tar.gz" -C "$TMP"
elif command -v git >/dev/null; then
  git clone --depth 1 -q "$REPO" "$TMP/cartographer"
else
  fail "could not download from $SITE, and git is not installed to fall back on."
fi
SRC="$TMP/cartographer"
[ -f "$SRC/bin/cartographer" ] || fail "download did not contain Cartographer (no bin/cartographer in $SRC)."

say "Installing into ~/.cartographer/app and Claude Code"
"$PY" "$SRC/bin/cartographer" install --agent "$AGENTS" $EXTRA

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) printf '\nSo the "cartographer" command works from any folder, add ~/.local/bin to your PATH once:\n'
     printf '  echo '"'"'export PATH="$HOME/.local/bin:$PATH"'"'"' >> ~/.zshrc && source ~/.zshrc\n'
     printf '(use ~/.bashrc instead of ~/.zshrc if your shell is bash)\n' ;;
esac

say "Done. Next:"
printf '  cartographer serve --open     # your dashboard: profile, sessions, maps (this machine only)\n'
printf '  /wrap                         # in Claude Code, at the end of a session\n'
printf '  cartographer doctor           # what is installed and where\n\n'
