#!/usr/bin/env bash
# Assemble the publishable tree by ALLOWLIST, then refuse to publish a leak.
#
# Allowlist rather than denylist on purpose: a new private file added later is
# excluded by default instead of published by accident.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/public"
cd "$ROOT"

FILES=(
  README.md
  VIDEO_RUNBOOK.md
  BUILD_LOG.public.md
  pyproject.toml
  .gitignore
  .env.example
)
DIRS=(
  src/meal_to_cart
  tests
  prompts
  site
  scripts
  data/sample
  .github
)

# Clear the tree but keep .git: rebuilding must not orphan the remote.
mkdir -p "$OUT"
find "$OUT" -mindepth 1 -maxdepth 1 -not -name ".git" -exec rm -rf {} +
for f in "${FILES[@]}"; do [ -e "$f" ] && cp -R "$f" "$OUT/"; done
for d in "${DIRS[@]}"; do
  [ -d "$d" ] || continue
  mkdir -p "$OUT/$d"
  # Skip caches and installed dependencies wherever they sit.
  (cd "$d" && find . -type f \
      -not -path "*/__pycache__/*" -not -name "*.pyc" \
      -not -path "*/node_modules/*" -not -path "*/.cache/*" \
      -print0 | while IFS= read -r -d '' file; do
      mkdir -p "$OUT/$d/$(dirname "$file")"
      cp "$file" "$OUT/$d/$file"
    done)
done

# Two data files matter but the rest of data/ is private.
mkdir -p "$OUT/data"
for f in extras.json rules.public.json private-terms.example.txt; do
  [ -e "data/$f" ] && cp "data/$f" "$OUT/data/"
done

# The vendored lockfile, without the installed tree.
mkdir -p "$OUT/vendor/walmart-mcp"
[ -e vendor/walmart-mcp/package.json ] && cp vendor/walmart-mcp/package.json "$OUT/vendor/walmart-mcp/"
[ -e vendor/walmart-mcp/bun.lock ] && cp vendor/walmart-mcp/bun.lock "$OUT/vendor/walmart-mcp/"

# Live-run output is machine-specific and gitignored upstream; never ship it.
rm -f "$OUT/site/data/live-run.json" "$OUT/site/data/dry-run.json"

echo "assembled $(find "$OUT" -type f | wc -l | tr -d ' ') files in dist/public"

# The gate. Publishing is gated on this exiting zero.
python3 -m meal_to_cart.guard "$OUT"
echo "OK: dist/public is safe to publish"
