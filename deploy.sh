#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Step 1: Build static site
echo "=== Building static site ==="
python3 build_site.py

# Step 2: Verify site was built
if [ ! -f "docs/data/episodes.json" ]; then
  echo "ERROR: docs/data/episodes.json not found — build may have failed." >&2
  exit 1
fi

# Step 3: Stage site output and channel config
echo ""
echo "=== Staging files ==="
git add docs/ channels.json

# Step 4: Check if there is anything to commit
if git diff --cached --quiet; then
  echo "Nothing to commit — site is already up to date."
  exit 0
fi

# Step 5: Commit
TIMESTAMP="$(date '+%Y-%m-%d %H:%M')"
git commit -m "chore: deploy static site — ${TIMESTAMP}"

# Step 6: Push
echo ""
echo "=== Pushing to GitHub ==="
git push

echo ""
echo "✓ Deployed successfully."
echo "  GitHub Pages should update within a minute."
