#!/usr/bin/env bash
# Run this from inside the repo root (git init/commit already done, or this
# script will do it for you). Requires `gh auth login` already done.
set -euo pipefail

REPO_NAME="prusaslicer-v3x-ai-integration"
REPO_DESC="AI-driven parameter optimization for PrusaSlicer 3.0 calibration prints — MCP server, DB, and dashboard."

if [ ! -d .git ]; then
  git init -b main
fi

git add -A
git commit -m "Initial scaffold: MCP-driven parameter optimizer for PrusaSlicer 3.0" || true

gh repo create "$REPO_NAME" \
  --public \
  --description "$REPO_DESC" \
  --source=. \
  --remote=origin \
  --push
