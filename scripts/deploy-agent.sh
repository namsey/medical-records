#!/usr/bin/env bash
# Deploy agent for one VM (DEPLOY.md B9). Installed by scripts/host-setup.sh as /usr/local/sbin/medical-records-deploy
# and run every 2 minutes by deploy/systemd/medical-records-deploy.timer.
#
# It deploys whatever the OCIR tag for this environment ("staging" or "prod") points at:
#   - resolves the tag to a digest without pulling, and does nothing when that digest is already deployed;
#   - prod: takes a backup first (not on the very first deploy: there is no data yet);
#   - pulls REPOSITORY@digest, checks out the commit in its org.opencontainers.image.revision label in
#     /opt/medical-records/repo and installs that commit's compose.yaml and Caddyfile, so they match the image;
#   - sets APP_IMAGE, runs `compose up -d` and waits until the app container is healthy and
#     https://SITE_DOMAIN/api/health answers ok (through the local Caddy);
#   - healthy: records it; unhealthy: goes back to the previous digest and compose files, remembers the digest
#     as bad (skipped until the tag moves elsewhere) and exits non-zero. A failed first deploy stops the app.
#
# Settings: /etc/medical-records/deploy.env (ENV_NAME, REPOSITORY, SITE_DOMAIN; written by host-setup.sh).
# Pause it with `touch /etc/medical-records/deploy-paused` (rm to resume). restore.sh --apply holds its lock.
# Nothing here prints secrets or record data.
set -euo pipefail
umask 022

CONFIG="${DEPLOY_CONFIG:-/etc/medical-records/deploy.env}"
[[ -r "$CONFIG" ]] || { echo "Cannot read $CONFIG (run scripts/host-setup.sh)" >&2; exit 2; }
set -a
# shellcheck source=/dev/null
source "$CONFIG"
set +a
: "${ENV_NAME:?ENV_NAME must be set in $CONFIG}"
: "${REPOSITORY:?REPOSITORY must be set in $CONFIG}"
: "${SITE_DOMAIN:?SITE_DOMAIN must be set in $CONFIG}"
[[ "$ENV_NAME" == "prod" || "$ENV_NAME" == "staging" ]] || { echo "ENV_NAME must be prod or staging" >&2; exit 2; }

COMPOSE_DIR="${COMPOSE_DIR:-/opt/medical-records/compose}"
REPO_DIR="${REPO_DIR:-/opt/medical-records/repo}"
STATE_DIR="${STATE_DIR:-/var/lib/medical-records}"
LOCK_FILE="${DEPLOY_LOCK:-/run/lock/medical-records-deploy.lock}"
PAUSE_FILE="${PAUSE_FILE:-/etc/medical-records/deploy-paused}"
COMPOSE_BIN="${COMPOSE_BIN:-/usr/local/sbin/medical-records-compose}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
HEALTH_CURL_OPTS="${HEALTH_CURL_OPTS:-}" # local tests only (e.g. -k for Caddy's internal certificate)
if [[ "$ENV_NAME" == "prod" ]]; then
  BACKUP_SERVICE="${BACKUP_SERVICE-medical-records-backup.service}"
else
  BACKUP_SERVICE="${BACKUP_SERVICE-}"
fi
export COMPOSE_DIR # read by the compose wrapper

log() { echo "$*"; }
record() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$STATE_DIR/deploy.log"; }
state() { cat "$STATE_DIR/$1" 2>/dev/null || true; }

mkdir -p "$STATE_DIR"
if [[ -e "$PAUSE_FILE" ]]; then
  log "Paused ($PAUSE_FILE exists): nothing deployed"
  exit 0
fi
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "Another deploy or a restore is running: trying again next time"
  exit 0
fi

# ---------- what should run ----------
tag="$ENV_NAME"
if ! out=$(docker buildx imagetools inspect "$REPOSITORY:$tag" --format '{{.Manifest.Digest}}' 2>&1); then
  if grep -qiE 'not found|manifest unknown' <<<"$out"; then
    log "No '$tag' tag in $REPOSITORY yet: nothing to deploy"
    exit 0
  fi
  echo "Cannot read $REPOSITORY:$tag from the registry: $out" >&2
  exit 1
fi
digest="$(tr -d '[:space:]' <<<"$out")"
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "Unexpected digest for $REPOSITORY:$tag: $digest" >&2; exit 1; }

current="$(state deployed-digest)"
[[ "$digest" == "$current" ]] && exit 0
bad="$(state bad-digest)"
if [[ -n "$bad" ]]; then
  [[ "$digest" == "$bad" ]] && exit 0 # a known-bad image: wait until the tag moves
  rm -f "$STATE_DIR/bad-digest"       # the tag moved on: forget it
fi
previous_revision="$(state deployed-revision)"
image="$REPOSITORY@$digest"

mark_bad() {
  echo "$digest" >"$STATE_DIR/bad-digest"
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$digest" >"$STATE_DIR/last-failure"
}

# Checks out a commit and installs its compose files. 2: could not fetch (try again later); 1: unknown commit.
install_compose() {
  if ! git -C "$REPO_DIR" cat-file -e "$1^{commit}" 2>/dev/null; then
    git -C "$REPO_DIR" fetch -q origin || return 2
    git -C "$REPO_DIR" cat-file -e "$1^{commit}" 2>/dev/null || return 1
  fi
  git -C "$REPO_DIR" -c advice.detachedHead=false checkout -q --detach "$1"
  install -m 644 "$REPO_DIR/deploy/compose/compose.yaml" "$REPO_DIR/deploy/compose/Caddyfile" "$COMPOSE_DIR/"
}

set_image() {
  local env_file="$COMPOSE_DIR/.env"
  grep -v '^APP_IMAGE=' "$env_file" >"$env_file.new" || true
  echo "APP_IMAGE=$1" >>"$env_file.new"
  mv "$env_file.new" "$env_file"
}

# Healthy = the app container's health check passes AND the site answers through the local Caddy.
healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT)) container status
  while ((SECONDS < deadline)); do
    container="$("$COMPOSE_BIN" ps -q app 2>/dev/null || true)"
    status="$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo missing)"
    [[ "$status" == "unhealthy" ]] && return 1
    # shellcheck disable=SC2086 # HEALTH_CURL_OPTS is a list of options
    if [[ "$status" == "healthy" ]] &&
      curl -fsS --max-time 5 $HEALTH_CURL_OPTS --resolve "$SITE_DOMAIN:443:127.0.0.1" \
        "https://$SITE_DOMAIN/api/health" 2>/dev/null | grep -q '"status": *"ok"'; then
      return 0
    fi
    sleep 5
  done
  return 1
}

# ---------- deploy ----------
log "Deploying $image ('$tag'; running now: ${current:-nothing})"
if [[ -n "$current" && -n "$BACKUP_SERVICE" ]]; then
  log "Backup before switching ($BACKUP_SERVICE)"
  if ! systemctl start "$BACKUP_SERVICE"; then
    record "FAILED $digest: the backup before the switch failed; nothing changed"
    echo "The backup before the switch failed: nothing changed. See journalctl -u $BACKUP_SERVICE" >&2
    exit 1
  fi
fi

docker pull -q "$image" >/dev/null
revision="$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
if [[ ! "$revision" =~ ^[0-9a-f]{40}$ ]]; then
  mark_bad
  record "FAILED $digest: no commit in its revision label; nothing changed"
  echo "$image has no org.opencontainers.image.revision label: not deployed" >&2
  exit 1
fi
rc=0
install_compose "$revision" || rc=$?
if ((rc == 2)); then
  echo "Could not fetch $REPO_DIR from its origin: trying again next time" >&2
  exit 1
elif ((rc != 0)); then
  mark_bad
  record "FAILED $digest: commit $revision is not in the repository; nothing changed"
  echo "Commit $revision of $image is not in the repository: not deployed" >&2
  exit 1
fi

set_image "$image"
if "$COMPOSE_BIN" up -d --remove-orphans && healthy; then
  echo "$digest" >"$STATE_DIR/deployed-digest"
  echo "$revision" >"$STATE_DIR/deployed-revision"
  [[ -n "$current" ]] && echo "$current" >"$STATE_DIR/previous-digest"
  record "OK $tag $digest $revision"
  log "Deployed $digest (commit $revision)"
  # Keep the image now running and the one before it, for a quick way back.
  docker image ls --digests --format '{{.Digest}}' "$REPOSITORY" | while read -r d; do
    [[ "$d" == "$digest" || "$d" == "$current" || "$d" == "<none>" ]] && continue
    docker image rm "$REPOSITORY@$d" >/dev/null 2>&1 || true
  done
  exit 0
fi

# ---------- unhealthy: back to what ran before ----------
mark_bad
"$COMPOSE_BIN" logs --no-color --tail 20 app 2>&1 || true
if [[ -n "$current" ]]; then
  log "Unhealthy: going back to $current"
  install_compose "${previous_revision:-$revision}" || true
  set_image "$REPOSITORY@$current"
  if "$COMPOSE_BIN" up -d --remove-orphans && healthy; then
    record "FAILED $digest: unhealthy; back on $current"
  else
    record "FAILED $digest: unhealthy; back on $current, which is NOT healthy either"
  fi
else
  log "Unhealthy on the first deploy: stopping the app (there is nothing to go back to)"
  "$COMPOSE_BIN" stop app || true
  record "FAILED $digest: unhealthy on the first deploy; app stopped"
fi
echo "Deploy of $digest failed: it stays skipped until the '$tag' tag points at another image" >&2
exit 1
