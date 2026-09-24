#!/usr/bin/env bash
# Idempotent setup for the Walmart MCP server the agent drives.
#
# Every path is scoped inside the project on purpose: this agent runs under a
# file sandbox that only writes to the workspace, and each of these tools
# assumes it owns the user's home directory. The overrides are the fix.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
CACHE="$ROOT/.cache"

mkdir -p "$CACHE/tmp" "$CACHE/bun" "$CACHE/ms-playwright" "$CACHE/home"

# bun refuses to start without a writable tempdir and install cache.
export BUN_INSTALL_CACHE_DIR="$CACHE/bun"
export TMPDIR="$CACHE/tmp"
# patchright would otherwise install a 550MB browser into ~/Library/Caches.
export PLAYWRIGHT_BROWSERS_PATH="$CACHE/ms-playwright"
# The server hardcodes os.homedir()/.striderlabs/walmart (dist/session.js).
# Node resolves HOME first, so this keeps its cookie jar inside the project.
export HOME="$CACHE/home"

echo "==> installing the MCP server into vendor/walmart-mcp"
(cd vendor/walmart-mcp && bun install)

echo "==> downloading the browser patchright needs"
bunx patchright@1.63.0 install chromium

echo "==> patching the stale User-Agent"
python3 scripts/patch_mcp.py

echo "==> verifying"
PYTHONPATH=src python3 scripts/probe_mcp.py
