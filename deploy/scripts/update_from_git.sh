#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash deploy/scripts/update_from_git.sh [branch]
# Optional environment variables:
#   APP_DIR=/opt/DGC_IMS
#   REMOTE=origin
#   SERVICE_NAME=dgc-ims
#   RESTART_SERVICE=1   # set to 0 to skip restart

BRANCH=${1:-main}
APP_DIR=${APP_DIR:-/opt/DGC_IMS}
REMOTE=${REMOTE:-origin}
SERVICE_NAME=${SERVICE_NAME:-dgc-ims}
RESTART_SERVICE=${RESTART_SERVICE:-1}

if [[ ! -d "$APP_DIR" ]]; then
  echo "Abort: APP_DIR '$APP_DIR' does not exist."
  exit 1
fi

cd "$APP_DIR"

# Ensure this is a git repository.
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Abort: '$APP_DIR' is not a git repository."
  exit 1
fi

# Abort if there are local edits, staged changes, or untracked files.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Abort: local changes detected. Commit/stash/clean before updating."
  exit 1
fi

# Ensure target branch exists locally.
if ! git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  echo "Abort: local branch '${BRANCH}' not found."
  exit 1
fi

# Ensure remote is configured.
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "Abort: remote '${REMOTE}' not configured."
  exit 1
fi

git checkout "$BRANCH"
git fetch "$REMOTE" "$BRANCH"

LOCAL=$(git rev-parse @)
REMOTE_SHA=$(git rev-parse "${REMOTE}/${BRANCH}")
BASE=$(git merge-base @ "${REMOTE}/${BRANCH}")

if [[ "$LOCAL" != "$BASE" ]]; then
  echo "Abort: local branch has commits not fully synced with ${REMOTE}/${BRANCH}."
  echo "Push or reconcile local commits first."
  exit 1
fi

if [[ "$LOCAL" == "$REMOTE_SHA" ]]; then
  echo "Already up to date (${BRANCH})."
  exit 0
fi

# Fast-forward only, never create merge commits.
git pull --ff-only "$REMOTE" "$BRANCH"

if [[ -x .venv/bin/pip ]]; then
  .venv/bin/pip install -r requirements.txt
fi

if [[ "$RESTART_SERVICE" == "1" ]] && command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl status "$SERVICE_NAME" --no-pager
fi

echo "Update complete: synced '${BRANCH}' from '${REMOTE}'."
