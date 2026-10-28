#!/usr/bin/env bash
# `docker compose` for the stack on a VM (DEPLOY.md B8). Installed by scripts/host-setup.sh as
# /usr/local/sbin/medical-records-compose:
#
#   sudo medical-records-compose ps | logs app | stop app | start app | up -d --force-recreate app
#
# Runs in /opt/medical-records/compose, so compose reads its .env (APP_IMAGE, DATA_DIR, SITE_DOMAIN,
# APP_MEMORY_LIMIT). Refuses while no image is deployed yet: compose.yaml needs APP_IMAGE.
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/opt/medical-records/compose}"

if ! grep -q '^APP_IMAGE=.' "$COMPOSE_DIR/.env" 2>/dev/null; then
  echo "No image is deployed yet ($COMPOSE_DIR/.env has no APP_IMAGE). The deploy agent sets it on its first" >&2
  echo "deploy: see 'journalctl -u medical-records-deploy'." >&2
  exit 3
fi
exec docker compose --project-directory "$COMPOSE_DIR" -f "$COMPOSE_DIR/compose.yaml" "$@"
