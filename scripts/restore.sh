#!/usr/bin/env bash
# Restore a backup made by backup.sh.
#
#   scripts/restore.sh [--to DIR] [SNAPSHOT]          restore into DIR (default: a new folder under STATE_DIR)
#                                                     and check it; the live data is not touched
#   scripts/restore.sh --apply [--yes] [SNAPSHOT]     also replace the live data: stop the app, move DATA_DIR
#                                                     aside to DATA_DIR.before-restore-<time>, put the backup
#                                                     in place, start the app (it migrates an older backup)
#
# SNAPSHOT is a restic snapshot ID; the default is the latest one ("restic snapshots" lists them).
set -euo pipefail
umask 077

# shellcheck source=backup-common.sh
source "$(dirname "${BASH_SOURCE[0]}")/backup-common.sh"

apply=0
confirmed=0
target=""
snapshot="latest"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1 ;;
    --yes) confirmed=1 ;;
    --to) target="$2"; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    -*) echo "Unknown option $1" >&2; exit 2 ;;
    *) snapshot="$1" ;;
  esac
  shift
done

mkdir -p "$STATE_DIR"
if [[ -z "$target" ]]; then
  target="$(mktemp -d "$STATE_DIR/restore-XXXXXX")"
elif [[ -e "$target" && -n "$(ls -A "$target")" ]]; then
  echo "$target is not empty" >&2
  exit 2
fi
mkdir -p "$target"

log "Restoring snapshot $snapshot into $target"
if [[ "$snapshot" == "latest" ]]; then
  run_restic restore "latest:$STAGING_DIR" --host "$BACKUP_HOST" --target "$target"
else
  run_restic restore "$snapshot:$STAGING_DIR" --target "$target"
fi
"$PYTHON" "$SCRIPTS_DIR/verify_backup.py" "$target"

if [[ "$apply" == "0" ]]; then
  log "Restored copy left in $target (the live data was not touched). Delete it when you are done: it is not encrypted."
  exit 0
fi

if [[ -z "${APP_STOP_CMD:-}" || -z "${APP_START_CMD:-}" ]]; then
  echo "Set APP_STOP_CMD and APP_START_CMD in $BACKUP_ENV before using --apply" >&2
  exit 2
fi
if [[ "$confirmed" == "0" ]]; then
  read -r -p "This replaces the live data in $DATA_DIR (it is moved aside, not deleted). Type 'restore' to go on: " answer
  [[ "$answer" == "restore" ]] || { echo "Stopped; nothing changed."; exit 1; }
fi

aside="$DATA_DIR.before-restore-$(date -u +%Y%m%dT%H%M%SZ)"
log "Stopping the app"
eval "$APP_STOP_CMD"
if [[ -e "$DATA_DIR" ]]; then
  log "Moving the current data to $aside"
  mv "$DATA_DIR" "$aside"
else
  log "No current data at $DATA_DIR (new server)"
fi
mkdir -p "$DATA_DIR"
mv "$target/database/medical_records.db" "$DB_FILE"
mv "$target/files" "$FILES_DIR"
# Keep the owner of the old data folder (or of its parent on a new server), so the app can read and write it.
chown -R --reference="$(if [[ -e "$aside" ]]; then echo "$aside"; else dirname "$DATA_DIR"; fi)" "$DATA_DIR"
chmod 700 "$DATA_DIR"
rm -rf "$target"
log "Starting the app"
eval "$APP_START_CMD"
if [[ -e "$aside" ]]; then
  log "Restore finished. The previous data is in $aside until you delete it."
else
  log "Restore finished."
fi
