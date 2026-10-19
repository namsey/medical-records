#!/usr/bin/env bash
# Nightly backup: a consistent copy of the database plus every stored file, encrypted by restic and sent to
# Oracle Object Storage in Mumbai. Run by deploy/systemd/medical-records-backup.timer; safe to run by hand.
#
#   BACKUP_ENV=/etc/medical-records/backup.env scripts/backup.sh
#
# Exits non-zero on any failure (systemd marks the run as failed) and only then leaves last-success alone.
set -euo pipefail
umask 077

# shellcheck source=backup-common.sh
source "$(dirname "${BASH_SOURCE[0]}")/backup-common.sh"

mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/backup.lock"
if ! flock -n 9; then
  log "Another backup is still running; not starting a second one"
  exit 1
fi

# The staging folder holds an unencrypted copy: always remove it, whatever happens.
cleanup() { rm -rf "$STAGING_DIR"; }
trap cleanup EXIT
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/database"

# 1. Database first. Files are written before their database row, so every document in this copy already has
#    its file on disk when the files are linked in step 2.
log "Copying the database"
"$PYTHON" "$SCRIPTS_DIR/snapshot_db.py" "$DB_FILE" "$STAGING_DIR/database/medical_records.db"

# 2. Files: stored files never change after they are written, so hard links give a fixed set to back up
#    without copying anything.
if [[ -d "$FILES_DIR" ]]; then
  cp -al "$FILES_DIR" "$STAGING_DIR/files"
else
  mkdir -p "$STAGING_DIR/files"
fi

log "Sending the encrypted backup"
run_restic backup --host "$BACKUP_HOST" --tag nightly "$STAGING_DIR"

log "Applying retention (7 daily, 4 weekly, 6 monthly)"
run_restic forget --host "$BACKUP_HOST" "${RETENTION[@]}" --prune

# Once a week (Sundays, or when FORCE_CHECK=1) re-read a sample of the stored data to catch damage in storage.
if [[ "$(date +%u)" == "7" || "${FORCE_CHECK:-0}" == "1" ]]; then
  log "Checking the repository (5% of the data)"
  run_restic check --read-data-subset=5%
fi

date -u +%Y-%m-%dT%H:%M:%SZ >"$STATE_DIR/last-success"
log "Backup finished"
