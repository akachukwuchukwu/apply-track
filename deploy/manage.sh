#!/bin/bash
# Run a manage.py command exactly the way the service runs: as the www-data user,
# with the environment from /etc/applytrack.env. Use this instead of a bare
# `python manage.py ...` on the server, so the database file always keeps the
# right owner and the production settings are always the ones in effect.
#
#   bash deploy/manage.sh migrate
#   bash deploy/manage.sh createsuperuser
set -euo pipefail

APP_DIR="${APPLYTRACK_DIR:-/opt/applytrack}"
ENV_FILE="${APPLYTRACK_ENV:-/etc/applytrack.env}"
SERVICE_USER="${APPLYTRACK_USER:-www-data}"

if [ "$(id -un)" != "$SERVICE_USER" ]; then
  SELF="$(readlink -f "$0")"
  exec sudo -u "$SERVICE_USER" env "APPLYTRACK_DIR=$APP_DIR" "APPLYTRACK_ENV=$ENV_FILE" "APPLYTRACK_USER=$SERVICE_USER" bash "$SELF" "$@"
fi

set -a
. "$ENV_FILE"
set +a
cd "$APP_DIR"
exec "$APP_DIR/.venv/bin/python" manage.py "$@"
