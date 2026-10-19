#!/usr/bin/env bash
# Tests for backup.sh, restore.sh and pull-home-copy.sh against local restic repositories (no cloud needed).
#
#   PYTHON=backend/.venv/bin/python scripts/test-backup.sh
#
# PYTHON must have the backend's requirements (it creates real app data). Needs restic and flock.
set -euo pipefail
umask 077

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/medical-records-backup-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }

DATA="$WORK/srv/data"
STATE="$WORK/state"
REPO="$WORK/repo"
printf 'test-password\n' >"$WORK/password"
export BACKUP_ENV="$WORK/backup.env"
cat >"$BACKUP_ENV" <<EOF
DATA_DIR=$DATA
RESTIC_REPOSITORY=$REPO
RESTIC_PASSWORD_FILE=$WORK/password
RESTIC_CACHE_DIR=$WORK/cache
STATE_DIR=$STATE
PYTHON=$PYTHON
APP_STOP_CMD="touch $WORK/app-stopped"
APP_START_CMD="touch $WORK/app-started"
EOF
export RESTIC_REPOSITORY="$REPO" RESTIC_PASSWORD_FILE="$WORK/password" RESTIC_CACHE_DIR="$WORK/cache"
restic init --quiet

"$PYTHON" "$SCRIPTS/tests/app_data.py" seed "$DATA"

# 1. A backup taken while the app keeps adding records and files is consistent and complete.
"$PYTHON" "$SCRIPTS/tests/app_data.py" write "$DATA" 8 &
writer=$!
sleep 1
FORCE_CHECK=1 "$SCRIPTS/backup.sh" >"$WORK/backup-1.log" 2>&1 || { cat "$WORK/backup-1.log"; fail "backup during writes"; }
wait "$writer"
[[ ! -e "$DATA/../.backup-staging" ]] || fail "the unencrypted staging copy was left behind"
grep -q "no errors were found" "$WORK/backup-1.log" || fail "the weekly repository check did not run"
"$SCRIPTS/restore.sh" --to "$WORK/during-writes" >"$WORK/restore-1.log" 2>&1 || { cat "$WORK/restore-1.log"; fail "restore"; }
"$PYTHON" "$SCRIPTS/verify_backup.py" "$WORK/during-writes" --strict >/dev/null || fail "backup taken during writes"
pass "backup taken while the app writes is consistent, and every document has its file"

# 2. Back up a quiet app, lose everything, restore it: the database rows and every file are identical.
before="$("$PYTHON" "$SCRIPTS/tests/app_data.py" fingerprint "$DATA")"
first_success="$(cat "$STATE/last-success")"
sleep 1
"$SCRIPTS/backup.sh" >"$WORK/backup-2.log" 2>&1 || { cat "$WORK/backup-2.log"; fail "backup"; }
[[ "$(cat "$STATE/last-success")" != "$first_success" ]] || fail "last-success was not updated"
rm -rf "$DATA"
"$SCRIPTS/restore.sh" --apply --yes >"$WORK/restore-2.log" 2>&1 || { cat "$WORK/restore-2.log"; fail "restore --apply"; }
after="$("$PYTHON" "$SCRIPTS/tests/app_data.py" fingerprint "$DATA")"
[[ "$before" == "$after" ]] || fail "restored data differs from the backed-up data"
[[ -e "$WORK/app-stopped" && -e "$WORK/app-started" ]] || fail "the app was not stopped and started"
pass "restore --apply brings back identical database rows and files"

sqlite3_sessions="$("$PYTHON" -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select count(*) from sessions').fetchone()[0])" "$DATA/medical_records.db")"
[[ "$sqlite3_sessions" == "0" ]] || fail "login sessions were backed up"
pass "login sessions are not in the backup"

# 3. Restoring over existing data moves it aside instead of deleting it.
marker="$DATA/files/kept-by-restore"
touch "$marker"
"$SCRIPTS/restore.sh" --apply --yes >/dev/null 2>&1 || fail "second restore --apply"
[[ ! -e "$marker" ]] || fail "the live data was not replaced"
ls "$DATA".before-restore-*/files/kept-by-restore >/dev/null 2>&1 || fail "the previous data was not kept aside"
pass "restore --apply keeps the previous data in DATA_DIR.before-restore-<time>"

# 4. A failed backup exits non-zero, keeps last-success and leaves no unencrypted copy.
good_success="$(cat "$STATE/last-success")"
sed -i "s|^RESTIC_REPOSITORY=.*|RESTIC_REPOSITORY=$WORK/no-such-repo|" "$BACKUP_ENV"
if "$SCRIPTS/backup.sh" >"$WORK/backup-3.log" 2>&1; then fail "a backup to a missing repository succeeded"; fi
[[ "$(cat "$STATE/last-success")" == "$good_success" ]] || fail "last-success changed after a failure"
[[ ! -e "$DATA/../.backup-staging" ]] || fail "the staging copy was left behind after a failure"
[[ -s "$STATE/last-failure" && "$(stat -c %a "$STATE/last-failure")" == "644" ]] || fail "the failure was not recorded"
sed -i "s|^RESTIC_REPOSITORY=.*|RESTIC_REPOSITORY=$REPO|" "$BACKUP_ENV"
pass "a failed backup exits non-zero, records last-failure, keeps last-success and leaves no unencrypted copy"
sleep 1
"$SCRIPTS/backup.sh" >/dev/null 2>&1 || fail "backup after a failure"
[[ "$(cat "$STATE/last-success")" > "$(cat "$STATE/last-failure")" ]] || fail "a later success is not newer than the failure"
[[ "$(stat -c %a "$STATE/last-success")" == "644" && "$(stat -c %a "$STATE")" == "755" ]] || fail "status not readable by the app"
pass "a later good backup is newer than the failure, and the app can read both times"

# 5. Two backups never run at once.
exec 8>"$STATE/backup.lock"
flock -n 8
if "$SCRIPTS/backup.sh" >/dev/null 2>&1; then fail "a second backup ran while one was running"; fi
exec 8>&-
pass "a second backup does not start while one is running"

# 6. The home copy pulls from a repository it cannot write to.
chmod -R a-w "$REPO"
printf 'home-password\n' >"$WORK/home-password"
cat >"$WORK/home-copy.env" <<EOF
RESTIC_FROM_REPOSITORY=$REPO
RESTIC_FROM_PASSWORD_FILE=$WORK/password
RESTIC_REPOSITORY=$WORK/home-repo
RESTIC_PASSWORD_FILE=$WORK/home-password
RESTIC_CACHE_DIR=$WORK/cache
EOF
HOME_COPY_ENV="$WORK/home-copy.env" "$SCRIPTS/pull-home-copy.sh" >"$WORK/home.log" 2>&1 || { cat "$WORK/home.log"; chmod -R u+w "$REPO"; fail "home copy"; }
chmod -R u+w "$REPO"
mkdir -p "$WORK/home-restore"
RESTIC_REPOSITORY="$WORK/home-repo" RESTIC_PASSWORD_FILE="$WORK/home-password" \
  restic restore latest --target "$WORK/home-restore" --quiet
home_db="$(find "$WORK/home-restore" -name medical_records.db | head -1)"
[[ -n "$home_db" ]] || fail "the home copy has no database"
"$PYTHON" "$SCRIPTS/verify_backup.py" "$(dirname "$(dirname "$home_db")")" --strict >/dev/null || fail "home copy"
pass "the home copy pulls with read-only access and restores"

# 7. Retention keeps 7 daily, 4 weekly and 6 monthly snapshots.
export RESTIC_REPOSITORY="$WORK/retention-repo"
restic init --quiet
retention="$(BACKUP_ENV="$BACKUP_ENV" bash -c 'source "$1"; echo "${RETENTION[@]}"' _ "$SCRIPTS/backup-common.sh")"
[[ "$retention" == "--keep-daily 7 --keep-weekly 4 --keep-monthly 6" ]] || fail "retention is not 7 daily / 4 weekly / 6 monthly"
# shellcheck disable=SC2086
"$PYTHON" "$SCRIPTS/tests/check_retention.py" $retention || fail "retention"
pass "retention flags: $retention"

echo "All backup tests passed"
