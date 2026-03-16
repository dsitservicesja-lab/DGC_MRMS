#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/DGC_IMS
SERVICE_NAME=dgc-ims
APP_USER=dgcims
SOURCE_DIR=$(cd "$(dirname "$0")/../.." && pwd)

if [[ $EUID -ne 0 ]]; then
  echo "Run this script with sudo or as root."
  exit 1
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR"
if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  if ! command -v rsync >/dev/null 2>&1; then
    apt-get update
    apt-get install -y rsync
  fi
  rsync -a --delete \
    --exclude ".git" \
    --exclude ".venv" \
    --exclude "__pycache__" \
    "$SOURCE_DIR/" "$APP_DIR/"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/deploy/systemd/dgc-ims.env.example" "$APP_DIR/.env"
  echo "Created $APP_DIR/.env from template. Edit this file before production use."
fi

cp "$APP_DIR/deploy/systemd/dgc-ims.service" "/etc/systemd/system/${SERVICE_NAME}.service"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager

echo "Deployment complete. Service is running on port 8082."
