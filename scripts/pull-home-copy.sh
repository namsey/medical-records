#!/usr/bin/env bash
# Weekly copy of the backups to a disk at home. Runs on YOUR machine, not on the server.
#
#   HOME_COPY_ENV=~/.config/medical-records/home-copy.env scripts/pull-home-copy.sh
#
# Pulls every new snapshot from the Mumbai bucket into a restic repository on your disk, using a READ-ONLY key:
# the server cannot reach or delete this copy. The home repository has its own password and keeps
# 8 weekly and 12 monthly snapshots. See DEPLOY.md for the settings file.
set -euo pipefail
umask 077

HOME_COPY_ENV="${HOME_COPY_ENV:-$HOME/.config/medical-records/home-copy.env}"
if [[ ! -r "$HOME_COPY_ENV" ]]; then
  echo "Cannot read the settings file $HOME_COPY_ENV (see DEPLOY.md)" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$HOME_COPY_ENV"
set +a

: "${RESTIC_FROM_REPOSITORY:?the Mumbai bucket (s3:https://...)}"
: "${RESTIC_FROM_PASSWORD_FILE:?the restic password of the server backups}"
: "${RESTIC_REPOSITORY:?the repository on your home disk}"
: "${RESTIC_PASSWORD_FILE:?the own password of the home repository}"

options=()
if [[ "$RESTIC_FROM_REPOSITORY" == s3:* ]]; then
  options+=(-o s3.bucket-lookup=path)
  if [[ -n "${AWS_DEFAULT_REGION:-}" ]]; then
    options+=(-o "s3.region=$AWS_DEFAULT_REGION")
  fi
fi

if ! restic cat config >/dev/null 2>&1; then
  echo "Creating the home repository at $RESTIC_REPOSITORY"
  # Same chunking as the server repository, so unchanged data is not stored twice.
  restic "${options[@]}" init --copy-chunker-params
fi

# --no-lock: the read-only key cannot write the lock file restic would normally leave in the bucket.
restic "${options[@]}" --no-lock copy
restic forget --keep-weekly 8 --keep-monthly 12 --prune
restic snapshots --latest 1
echo "Home copy up to date: $(date)"
