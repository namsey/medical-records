# Shared settings for backup.sh and restore.sh. Sourced, not run.
#
# Settings come from the file named by BACKUP_ENV (default /etc/medical-records/backup.env, see
# backup.env.example). Nothing here prints record contents: only counts, times and file names of the backup itself.

# shellcheck shell=bash
# The variables below are used by the scripts that source this file.
# shellcheck disable=SC2034

BACKUP_ENV="${BACKUP_ENV:-/etc/medical-records/backup.env}"
if [[ ! -r "$BACKUP_ENV" ]]; then
  echo "Cannot read the settings file $BACKUP_ENV (copy scripts/backup.env.example there)" >&2
  exit 1
fi
set -a
# shellcheck source=backup.env.example
source "$BACKUP_ENV"
set +a

: "${DATA_DIR:?DATA_DIR must be set in $BACKUP_ENV}"
: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY must be set in $BACKUP_ENV}"
: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE must be set in $BACKUP_ENV}"

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
STATE_DIR="${STATE_DIR:-/var/lib/medical-records-backup}"
# Must be on the same disk as DATA_DIR: files are hard-linked into it, not copied.
STAGING_DIR="${STAGING_DIR:-$(dirname "$DATA_DIR")/.backup-staging}"
DB_FILE="$DATA_DIR/medical_records.db"
FILES_DIR="$DATA_DIR/files"

# One fixed host name, so snapshots and retention stay in one group even after moving to a new VM.
BACKUP_HOST="medical-records"
RETENTION=(--keep-daily 7 --keep-weekly 4 --keep-monthly 6)

# Oracle Object Storage's S3-compatible endpoint needs path-style bucket names.
RESTIC_OPTIONS=()
if [[ "$RESTIC_REPOSITORY" == s3:* ]]; then
  RESTIC_OPTIONS+=(-o s3.bucket-lookup=path)
  if [[ -n "${AWS_DEFAULT_REGION:-}" ]]; then
    RESTIC_OPTIONS+=(-o "s3.region=$AWS_DEFAULT_REGION")
  fi
fi

run_restic() {
  restic "${RESTIC_OPTIONS[@]}" "$@"
}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}
