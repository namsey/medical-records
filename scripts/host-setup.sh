#!/usr/bin/env bash
# Prepares a VM to run the Compose stack and deploy itself from OCI Container Registry (DEPLOY.md Part B, ctr-3).
# Run as root over SSH, from a real terminal so it can ask for the secrets. Safe to run again.
#
#   sudo ./host-setup.sh --env prod|staging --domain D [--alias A]... --registry R --repository REPO [--format-data-volume]
#                        [--reset-app-settings]
#
#   --alias        optional, repeatable: another name that only redirects to --domain (prod: www.<domain>; an old
#                  name kept for a while after a move). Give them on every run: the compose .env is rewritten.
#   --registry     the region's OCIR host, e.g. bom.ocir.io             (terraform output ocir_registry)
#   --repository   e.g. bom.ocir.io/<namespace>/medical-records/app     (terraform output ocir_repository)
#   --format-data-volume   prod only, first run only: mkfs the data volume, and only if blkid finds no filesystem
#   --reset-app-settings   ask again for the Google client, admin and grievance settings and rewrite them in app.env
#                  (SESSION_SECRET and every other line are kept; the old file is kept as app.env.previous), then
#                  restart the app. Use it to move to a new OAuth client or domain.
#
# It installs Docker, the data folder (owned by the app container's user, 10001), /etc/medical-records/app.env,
# the compose files, the medical-records-compose wrapper, the deploy agent and its timer, and signs in to OCIR
# with the pull-only user. Prod also gets ClamAV and the nightly backups. It never deploys or starts the app
# itself: the agent does that once the environment's tag ("staging" or "prod") exists in OCIR.
#
# Secrets are read with read -s and written only to files under /etc/medical-records (mode 600) or root's docker
# login (/root/.docker/config.json, mode 600); none is printed, except the restic password, shown once.
# shellcheck disable=SC2154 # google_secret, token and key_secret are set by ask_secret (printf -v)
set -euo pipefail
umask 022

REPO_URL="https://github.com/namsey/medical-records"
OPT=/opt/medical-records
REPO_DIR=$OPT/repo
COMPOSE_DIR=$OPT/compose
ETC=/etc/medical-records
DATA_MOUNT=/srv/medical-records
DATA_DEV=/dev/oracleoci/oraclevdb
APP_UID=10001 # the app container's user and group (Dockerfile)
REGION=ap-mumbai-1
BUCKET=medical-records-backup

env_name="" domain="" aliases="" registry="" repository="" format_volume=0 reset_settings=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) env_name="$2"; shift ;;
    --domain) domain="$2"; shift ;;
    --alias) aliases="${aliases:+$aliases }$2"; shift ;;
    --registry) registry="$2"; shift ;;
    --repository) repository="$2"; shift ;;
    --format-data-volume) format_volume=1 ;;
    --reset-app-settings) reset_settings=1 ;;
    -h|--help) sed -n '2,23p' "$0"; exit 0 ;;
    *) echo "Unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 2; }
[[ "$env_name" == "prod" || "$env_name" == "staging" ]] || { echo "--env must be prod or staging" >&2; exit 2; }
[[ -n "$domain" && -n "$registry" && -n "$repository" ]] || { echo "--domain, --registry and --repository are required" >&2; exit 2; }
for name in $aliases; do
  [[ "$name" =~ ^[a-z0-9.-]+$ && "$name" != "$domain" ]] || { echo "--alias takes a host name other than --domain, e.g. www.$domain" >&2; exit 2; }
done
[[ "$registry" == *.ocir.io ]] || { echo "--registry looks like bom.ocir.io" >&2; exit 2; }
[[ "$repository" == "$registry"/*/* ]] || { echo "--repository looks like $registry/<namespace>/medical-records/app" >&2; exit 2; }
[[ "$format_volume" == "0" || "$env_name" == "prod" ]] || { echo "--format-data-volume is for prod only (staging has no data volume)" >&2; exit 2; }
[[ "$reset_settings" == "0" || ( -t 0 && -t 1 ) ]] || { echo "--reset-app-settings asks for secrets: run it from a terminal (ssh -t)" >&2; exit 2; }
namespace="${repository#"$registry"/}"
namespace="${namespace%%/*}"

step() { printf '\n==> %s\n' "$*"; }
todo=()
have_tty() { [[ -t 0 && -t 1 ]]; }
ask_secret() { # ask_secret VAR "prompt": reads without echo, refuses empty
  local __v=""
  while [[ -z "$__v" ]]; do read -r -s -p "$2: " __v; echo; done
  printf -v "$1" '%s' "$__v"
}
ask() { # ask VAR "prompt" [default]
  local __v=""
  while [[ -z "$__v" ]]; do read -r -p "$2${3:+ [$3]}: " __v; __v="${__v:-${3:-}}"; done
  printf -v "$1" '%s' "$__v"
}

if [[ "$env_name" == "staging" && "$domain" != *staging* ]]; then
  echo
  echo "  !!! WARNING: --env staging, but the domain '$domain' does not contain 'staging'."
  echo "  !!! Staging must have its own domain, its own Google OAuth client and its own SESSION_SECRET,"
  echo "  !!! so a staging sign-in can never reach prod. Check the domain before going on."
  echo
  if have_tty; then
    read -r -p "  Type 'yes' to continue with '$domain' as staging: " ok
    [[ "$ok" == "yes" ]] || { echo "Stopped; nothing changed."; exit 1; }
  fi
fi

if [[ -e /etc/systemd/system/medical-records.service ]] || systemctl is-active -q caddy 2>/dev/null; then
  echo "This VM still runs the pre-container setup (medical-records.service or host Caddy, infra/deploy.sh)." >&2
  echo "Stop and disable them first (DEPLOY.md B9): they hold ports 80/443 and the data." >&2
  exit 1
fi

step "Waiting for first-boot setup (cloud-init) to finish"
cloud-init status --wait >/dev/null 2>&1 || true

step "B1: packages and automatic security updates"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q >/dev/null
packages=(ca-certificates curl git python3 sqlite3 unattended-upgrades)
[[ "$env_name" == "prod" ]] && packages+=(restic)
apt-get install -y -q "${packages[@]}" >/dev/null
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' >/etc/apt/apt.conf.d/20auto-upgrades

step "B2: ports 80/443 in the VM firewall"
if ! iptables -C INPUT -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null; then
  iptables -I INPUT -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT
  netfilter-persistent save
fi

step "B3: Docker Engine, Compose and Buildx (Docker's apt repository)"
if ! docker compose version >/dev/null 2>&1 || ! docker buildx version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck source=/dev/null
  codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $codename stable" \
    >/etc/apt/sources.list.d/docker.list
  apt-get update -q >/dev/null
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin >/dev/null
fi
systemctl enable -q --now docker
docker compose version

step "B4/B5: data folder"
if [[ "$env_name" == "prod" ]]; then
  for _ in $(seq 1 30); do [[ -e "$DATA_DEV" ]] && break; sleep 2; done
  [[ -e "$DATA_DEV" ]] || { echo "$DATA_DEV not found: is the block volume attached?" >&2; exit 1; }
  if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
    if [[ "$format_volume" == "1" ]]; then
      mkfs.ext4 -L medical-data "$DATA_DEV"
    else
      echo "The data volume has no filesystem. Re-run with --format-data-volume to create one (first time only)." >&2
      exit 3
    fi
  fi
  mkdir -p "$DATA_MOUNT"
  grep -q "^$DATA_DEV $DATA_MOUNT " /etc/fstab || echo "$DATA_DEV $DATA_MOUNT ext4 defaults,_netdev,nofail 0 2" >>/etc/fstab
  systemctl daemon-reload
  mountpoint -q "$DATA_MOUNT" || mount "$DATA_MOUNT"
  mountpoint -q "$DATA_MOUNT" || { echo "$DATA_MOUNT is not mounted" >&2; exit 1; }
else
  mkdir -p "$DATA_MOUNT" # staging: on the boot volume
fi
mkdir -p "$DATA_MOUNT/data"
if [[ -n "$(find "$DATA_MOUNT/data" \( ! -uid "$APP_UID" -o ! -gid "$APP_UID" \) -print -quit)" ]]; then
  chown -R "$APP_UID:$APP_UID" "$DATA_MOUNT/data"
fi
chmod 700 "$DATA_MOUNT/data"
df -h "$DATA_MOUNT" | tail -1

step "B6: the code ($REPO_DIR; the deploy agent keeps it at the running release)"
install -d -m 755 "$OPT"
[[ -d "$REPO_DIR/.git" ]] || git clone -q "$REPO_URL" "$REPO_DIR"
git -C "$REPO_DIR" log -1 --format='at %h %s'

step "B7: app settings ($ETC/app.env)"
install -d -m 700 "$ETC"
# The settings asked for below; --reset-app-settings rewrites only these and keeps every other line.
ASKED_KEYS='^(GOOGLE_CLIENT_ID|GOOGLE_CLIENT_SECRET|GOOGLE_REDIRECT_URI|ADMIN_EMAIL|GRIEVANCE_NAME|GRIEVANCE_EMAIL)='
current() { { sed -n "s/^$1=//p" "$ETC/app.env" 2>/dev/null || true; } | tail -1; } # a non-secret's value now, as the default
ask_app_settings() {
  if [[ "$env_name" == "staging" ]]; then
    echo "  Use the STAGING Google OAuth client (redirect https://$domain/api/auth/callback), never prod's."
  fi
  ask google_id "Google OAuth client ID"
  ask_secret google_secret "Google OAuth client secret (not shown)"
  ask admin_email "Admin email (your Google account)" "$(current ADMIN_EMAIL)"
  ask grievance_name "Grievance officer name (privacy notice)" "$(current GRIEVANCE_NAME)"
  local was_email
  was_email=$(current GRIEVANCE_EMAIL)
  ask grievance_email "Grievance email" "${was_email:-$admin_email}"
}
asked_settings() {
  printf '%s\n' "GOOGLE_CLIENT_ID=$google_id" "GOOGLE_CLIENT_SECRET=$google_secret" \
    "GOOGLE_REDIRECT_URI=https://$domain/api/auth/callback" "ADMIN_EMAIL=$admin_email" \
    "GRIEVANCE_NAME=$grievance_name" "GRIEVANCE_EMAIL=$grievance_email"
}
settings_reset=0
if [[ ! -s "$ETC/app.env" ]]; then
  if have_tty; then
    ask_app_settings
    session_secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))') # new on every VM
    install -m 600 /dev/null "$ETC/app.env"
    # Where the data lives (DATABASE_URL, FILES_DIR, UPLOAD_DIR) is set by compose.yaml.
    { asked_settings; echo "SESSION_SECRET=$session_secret"; } >"$ETC/app.env"
    unset google_secret session_secret
    echo "written"
  else
    todo+=("app.env (Google client ID/secret): re-run from a terminal")
  fi
elif [[ "$reset_settings" == "1" ]]; then
  ask_app_settings
  install -m 600 /dev/null "$ETC/app.env.new"
  { asked_settings; grep -Ev "$ASKED_KEYS" "$ETC/app.env" || true; } >"$ETC/app.env.new"
  unset google_secret
  install -m 600 "$ETC/app.env" "$ETC/app.env.previous"
  mv "$ETC/app.env.new" "$ETC/app.env"
  settings_reset=1
  echo "rewritten (SESSION_SECRET and other lines kept; the old file is $ETC/app.env.previous)"
fi
if [[ -s "$ETC/app.env" ]]; then
  grep -q "^GOOGLE_REDIRECT_URI=https://$domain/" "$ETC/app.env" ||
    echo "  WARNING: GOOGLE_REDIRECT_URI in $ETC/app.env is not on https://$domain/: check it."
  if [[ "$env_name" == "prod" ]]; then
    grep -q '^BACKUP_STATUS_DIR=' "$ETC/app.env" || echo 'BACKUP_STATUS_DIR=/var/lib/medical-records-backup' >>"$ETC/app.env"
  fi
fi

if [[ "$env_name" == "prod" ]]; then
  step "C6: ClamAV (prod only)"
  dpkg -s clamav-daemon >/dev/null 2>&1 || apt-get install -y -q clamav-daemon >/dev/null
  systemctl enable --now clamav-freshclam clamav-daemon >/dev/null 2>&1 || true
  if [[ -s "$ETC/app.env" ]] && ! grep -q '^CLAMAV_SOCKET=' "$ETC/app.env"; then
    echo 'CLAMAV_SOCKET=/run/clamav/clamd.ctl' >>"$ETC/app.env"
  fi
fi

step "B8: compose files ($COMPOSE_DIR), the medical-records-compose wrapper and log limits"
install -d -m 755 "$COMPOSE_DIR"
install -m 644 "$REPO_DIR/deploy/compose/compose.yaml" "$REPO_DIR/deploy/compose/Caddyfile" "$COMPOSE_DIR/"
app_image="$(grep '^APP_IMAGE=' "$COMPOSE_DIR/.env" 2>/dev/null || echo 'APP_IMAGE=')" # set by the agent; kept
memory=1g
[[ "$env_name" == "prod" ]] && memory=2g
cat >"$COMPOSE_DIR/.env.new" <<EOF
DATA_DIR=$DATA_MOUNT/data
SITE_DOMAIN=$domain
SITE_ALIASES=$aliases
APP_MEMORY_LIMIT=$memory
$app_image
EOF
mv "$COMPOSE_DIR/.env.new" "$COMPOSE_DIR/.env"
install -m 755 "$REPO_DIR/scripts/compose-wrapper.sh" /usr/local/sbin/medical-records-compose
install -D -m 644 "$REPO_DIR/deploy/journald/medical-records.conf" /etc/systemd/journald.conf.d/medical-records.conf
systemctl restart systemd-journald

step "B6: sign in to OCIR ($registry) with the pull-only user"
if ! grep -q "\"$registry\"" /root/.docker/config.json 2>/dev/null; then
  if have_tty; then
    echo "  Username: <namespace>/<user> for the Default identity domain, <namespace>/<domain>/<user> otherwise."
    ask username "OCIR username" "$namespace/vm-image-puller"
    ask_secret token "Auth token of $username (not shown)"
    printf '%s' "$token" | DOCKER_CONFIG=/root/.docker docker login "$registry" -u "$username" --password-stdin >/dev/null
    unset token
    chmod 600 /root/.docker/config.json
    echo "signed in"
  else
    todo+=("OCIR sign-in (vm-image-puller auth token): re-run from a terminal")
  fi
fi

if [[ "$env_name" == "prod" ]]; then
  step "B11: backups (restic to the $BUCKET bucket; prod only)"
  if [[ ! -s "$ETC/restic-password" ]]; then
    if have_tty; then
      install -m 600 /dev/null "$ETC/restic-password"
      openssl rand -base64 32 >"$ETC/restic-password"
      echo
      echo "  RESTIC PASSWORD (shown once; save it in your password manager AND on paper now):"
      echo
      echo "      $(cat "$ETC/restic-password")"
      echo
      read -r -p "  Type 'saved' when it is stored safely: " ok
      while [[ "$ok" != "saved" ]]; do read -r -p "  Type 'saved': " ok; done
      clear || true
    else
      todo+=("restic password: re-run from a terminal")
    fi
  fi
  if [[ ! -s "$ETC/backup.env" ]]; then
    if have_tty; then
      ask key_id "backup-writer Access key (from the Customer secret key)"
      ask_secret key_secret "backup-writer Secret key (not shown)"
      install -m 600 /dev/null "$ETC/backup.env"
      cat >"$ETC/backup.env" <<EOF
DATA_DIR=$DATA_MOUNT/data
RESTIC_REPOSITORY=s3:https://$namespace.compat.objectstorage.$REGION.oraclecloud.com/$BUCKET
AWS_DEFAULT_REGION=$REGION
AWS_ACCESS_KEY_ID=$key_id
AWS_SECRET_ACCESS_KEY=$key_secret
RESTIC_PASSWORD_FILE=$ETC/restic-password
RESTIC_CACHE_DIR=/var/cache/medical-records-backup
STATE_DIR=/var/lib/medical-records-backup
APP_STOP_CMD="medical-records-compose stop app"
APP_START_CMD="medical-records-compose start app"
DATA_OWNER=$APP_UID:$APP_UID
EOF
      unset key_secret
    else
      todo+=("backup.env (Object Storage key): re-run from a terminal")
    fi
  fi
  install -m 644 "$REPO_DIR"/deploy/systemd/medical-records-backup.{service,timer} /etc/systemd/system/
  systemctl daemon-reload
  if [[ -s "$ETC/backup.env" && -s "$ETC/restic-password" ]]; then
    restic_env() { bash -c "set -a; source $ETC/backup.env; restic -o s3.bucket-lookup=path $*"; }
    # init only creates a repository that does not exist yet (it refuses an existing one).
    restic_env cat config >/dev/null 2>&1 || restic_env init
    # No "first backup" here: on a rebuilt VM it would make an empty snapshot the latest one. The timer runs
    # nightly, and the agent backs up before every switch to a new image.
    systemctl enable -q --now medical-records-backup.timer
    systemctl list-timers medical-records-backup.timer --no-pager | head -2
  fi
fi

step "B9: the deploy agent (medical-records-deploy, every 2 minutes)"
install -m 755 "$REPO_DIR/scripts/deploy-agent.sh" /usr/local/sbin/medical-records-deploy
cat >"$ETC/deploy.env" <<EOF
ENV_NAME=$env_name
REPOSITORY=$repository
SITE_DOMAIN=$domain
EOF
install -m 644 "$REPO_DIR"/deploy/systemd/medical-records-deploy.{service,timer} /etc/systemd/system/
systemctl daemon-reload
if grep -q "\"$registry\"" /root/.docker/config.json 2>/dev/null && [[ -s "$ETC/app.env" ]]; then
  systemctl enable -q --now medical-records-deploy.timer
  systemctl start --no-block medical-records-deploy.service
  echo "enabled; follow it with: journalctl -fu medical-records-deploy"
else
  todo+=("deploy agent not enabled yet: needs app.env and the OCIR sign-in")
fi

if [[ "$settings_reset" == "1" ]]; then
  step "Restarting the app with the new settings"
  # Under the deploy agent's lock: the agent (started above, or by its timer) may be replacing the same container.
  # Whatever it deploys meanwhile already reads the new app.env; this restart then covers the case of no deploy.
  if flock -w 600 /run/lock/medical-records-deploy.lock medical-records-compose up -d --force-recreate --wait app; then
    echo "  Check the sign-in, then delete the old settings: sudo rm $ETC/app.env.previous"
  else
    todo+=("app not restarted (a deploy still running, or no image yet): check sudo medical-records-compose ps")
  fi
fi

step "Status"
for u in docker medical-records-deploy.timer clamav-daemon medical-records-backup.timer; do
  printf '  %-32s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null || true)"
done
if ((${#todo[@]})); then
  echo; echo "Still to do:"; printf '  - %s\n' "${todo[@]}"
fi
