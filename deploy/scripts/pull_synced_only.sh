#!/usr/bin/env bash
set -euo pipefail

BRANCH=${1:-main}
SERVICE_NAME=${SERVICE_NAME:-dgc-ims}
RESTART_SERVICE=${RESTART_SERVICE:-1}

# Ensure we are in a git repository.
git rev-parse --is-inside-work-tree >/dev/null

# Abort if there are any local edits, staged changes, or untracked files.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Abort: local changes detected. Commit/stash/clean before pulling."
  exit 1
fi

if ! git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  echo "Abort: local branch '${BRANCH}' not found."
  exit 1
fi

git checkout "$BRANCH"

git fetch origin "$BRANCH"

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse "origin/${BRANCH}")
BASE=$(git merge-base @ "origin/${BRANCH}")

if [[ "$LOCAL" != "$BASE" ]]; then
  echo "Abort: local branch has commits not fully synced with origin/${BRANCH}."
  echo "Push or reconcile local commits first."
  exit 1
fi

if [[ "$LOCAL" == "$REMOTE" ]]; then
  echo "Already up to date."
  exit 0
fi

# Fast-forward only, never create merge commits.
git pull --ff-only origin "$BRANCH"

if [[ -x .venv/bin/pip ]]; then
  .venv/bin/pip install -r requirements.txt
fi

if [[ "$RESTART_SERVICE" == "1" ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl restart "$SERVICE_NAME"
    sudo systemctl status "$SERVICE_NAME" --no-pager
  fi
fi

echo "Update complete: pulled committed and synced changes from origin/${BRANCH}."
