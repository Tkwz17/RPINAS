#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/rpinas"
mkdir -p "$APP_ROOT" /var/lib/rpinas
cp -r /opt/rpinas-src/backend "$APP_ROOT/backend"
python3 -m venv "$APP_ROOT/.venv"
"$APP_ROOT/.venv/bin/pip" install --upgrade pip
"$APP_ROOT/.venv/bin/pip" install -r "$APP_ROOT/backend/requirements.txt"
