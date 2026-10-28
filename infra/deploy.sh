#!/usr/bin/env bash
# SUPERSEDED by scripts/host-setup.sh (ctr-3): the VMs now run the Compose stack from OCI Container Registry and
# deploy themselves (DEPLOY.md Part B). This script sets up the old build-on-the-VM systemd service and host Caddy;
# it is kept for reference only. Do not run it on a VM prepared by host-setup.sh (it would fight over ports 80/443),
# and note it copies deploy/systemd/medical-records-backup.service, which now expects /opt/medical-records/repo.
#
# Server setup for the medical-records VM: DEPLOY.md B2-B11 and C6, safe to re-run.
#
#   sudo ./deploy.sh --domain D --admin-email E --namespace NS [--grievance-name NAME] [--format-data-volume]
#
# Run it from a real terminal (ssh -t) to be asked for the secrets; without a terminal the steps that need a
# secret are skipped and listed at the end. Secrets are typed with read -s and only written to files under
# /etc/medical-records (mode 600); none is printed, except the restic password, shown once on the terminal.
# mkfs only runs with --format-data-volume, and only when blkid finds no filesystem on the data volume.
set -euo pipefail
umask 022

REPO_URL="https://github.com/namsey/medical-records"
APP_DIR=/opt/medical-records
DATA_MOUNT=/srv/medical-records
DATA_DEV=/dev/oracleoci/oraclevdb
ETC=/etc/medical-records
REGION=ap-mumbai-1
BUCKET=medical-records-backup

domain="" admin_email="" namespace="" grievance_name="" format_volume=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) domain="$2"; shift ;;
    --admin-email) admin_email="$2"; shift ;;
    --namespace) namespace="$2"; shift ;;
    --grievance-name) grievance_name="$2"; shift ;;
    --format-data-volume) format_volume=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 2; }
[[ -n "$domain" && -n "$admin_email" && -n "$namespace" ]] || { echo "--domain, --admin-email and --namespace are required" >&2; exit 2; }

step() { printf '\n==> %s\n' "$*"; }
todo=()
have_tty() { [[ -t 0 && -t 1 ]]; }
ask_secret() { # ask_secret VAR "prompt": reads without echo, refuses empty
  local __v=""
  while [[ -z "$__v" ]]; do read -r -s -p "$2: " __v; echo; done
  printf -v "$1" '%s' "$__v"
}
as_ubuntu() { sudo -u ubuntu -H bash -c "$1"; }

step "Waiting for first-boot setup (cloud-init) to finish"
cloud-init status --wait >/dev/null || true

step "B1: updates and packages"
export DEBIAN_FRONTEND=noninteractive
# Also covers a first boot that ran before the reserved public IP was attached.
apt-get update -q >/dev/null && apt-get -y -q full-upgrade >/dev/null
apt-get install -y -q git python3-venv python3-pip sqlite3 restic unattended-upgrades >/dev/null

step "B2: ports 80/443 in the VM firewall"
if ! iptables -C INPUT -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null; then
  iptables -I INPUT -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j ACCEPT
  netfilter-persistent save
fi

step "B3: Node.js 22"
if ! node --version 2>/dev/null | grep -q '^v22\.'; then
  curl -fsSL https://deb.nodesource.com/setup_22.x -o /tmp/nodesource.sh
  bash /tmp/nodesource.sh >/dev/null
  apt-get install -y -q nodejs >/dev/null
fi
node --version

step "B4: data volume at $DATA_MOUNT"
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
grep -q "^$DATA_DEV $DATA_MOUNT " /etc/fstab || echo "$DATA_DEV $DATA_MOUNT ext4 defaults,_netdev,nofail 0 2" >> /etc/fstab
systemctl daemon-reload
mountpoint -q "$DATA_MOUNT" || mount "$DATA_MOUNT"
mountpoint -q "$DATA_MOUNT" || { echo "$DATA_MOUNT is not mounted" >&2; exit 1; }
df -h "$DATA_MOUNT" | tail -1

step "B5: app user and data folder"
id medical-records >/dev/null 2>&1 || useradd --system --home "$DATA_MOUNT" --shell /usr/sbin/nologin medical-records
install -d -m 700 -o medical-records -g medical-records "$DATA_MOUNT/data"

step "B6: code at the latest release tag, and build"
[[ -d "$APP_DIR/.git" ]] || git clone -q "$REPO_URL" "$APP_DIR"
chown -R ubuntu:ubuntu "$APP_DIR"
as_ubuntu "cd $APP_DIR && git fetch -q --tags origin"
tag=$(as_ubuntu "cd $APP_DIR && git tag --list 'v*' --sort=-v:refname | head -1")
[[ -n "$tag" ]] || { echo "No release tag (v*) in $REPO_URL" >&2; exit 1; }
built_marker="$APP_DIR/.deployed-tag"
if [[ "$(cat "$built_marker" 2>/dev/null)" != "$tag" ]]; then
  as_ubuntu "cd $APP_DIR && git checkout -q $tag \
    && { [[ -d backend/.venv ]] || python3 -m venv backend/.venv; } \
    && backend/.venv/bin/pip install -q -r backend/requirements.txt \
    && cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent"
  echo "$tag" > "$built_marker"
  chown ubuntu:ubuntu "$built_marker"
  rebuilt=1
fi
echo "release: $tag"

step "B7: app settings ($ETC/app.env)"
install -d -m 700 "$ETC"
if [[ ! -s "$ETC/app.env" ]]; then
  if have_tty; then
    read -r -p "Google OAuth client ID: " google_id
    ask_secret google_secret "Google OAuth client secret (not shown)"
    session_secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
    install -m 600 /dev/null "$ETC/app.env"
    cat > "$ETC/app.env" <<EOF
GOOGLE_CLIENT_ID=$google_id
GOOGLE_CLIENT_SECRET=$google_secret
GOOGLE_REDIRECT_URI=https://$domain/api/auth/callback
ADMIN_EMAIL=$admin_email
SESSION_SECRET=$session_secret
DATABASE_URL=sqlite:///$DATA_MOUNT/data/medical_records.db
FILES_DIR=$DATA_MOUNT/data/files
UPLOAD_DIR=$DATA_MOUNT/data/uploads
BACKUP_STATUS_DIR=/var/lib/medical-records-backup
GRIEVANCE_NAME=$grievance_name
GRIEVANCE_EMAIL=$admin_email
EOF
    unset google_secret session_secret
    echo "written"
  else
    todo+=("app.env (Google client ID/secret): re-run from a terminal")
  fi
fi

step "B8: systemd service and log rotation"
install -D -m 644 "$APP_DIR/deploy/journald/medical-records.conf" /etc/systemd/journald.conf.d/medical-records.conf
systemctl restart systemd-journald
cp "$APP_DIR"/deploy/systemd/medical-records.service "$APP_DIR"/deploy/systemd/medical-records-backup.{service,timer} /etc/systemd/system/
systemctl daemon-reload

step "C6: ClamAV"
dpkg -s clamav-daemon >/dev/null 2>&1 || apt-get install -y -q clamav-daemon >/dev/null
systemctl enable --now clamav-freshclam clamav-daemon >/dev/null 2>&1 || true
usermod -aG clamav medical-records
if [[ -s "$ETC/app.env" ]] && ! grep -q '^CLAMAV_SOCKET=' "$ETC/app.env"; then
  echo 'CLAMAV_SOCKET=/run/clamav/clamd.ctl' >> "$ETC/app.env"
fi

if [[ -s "$ETC/app.env" ]]; then
  systemctl enable -q medical-records
  if [[ "${rebuilt:-0}" == "1" ]] || ! systemctl is-active -q medical-records; then systemctl restart medical-records; fi
  for _ in $(seq 1 30); do curl -fs http://127.0.0.1:8000/api/health >/dev/null && break; sleep 2; done
  curl -s http://127.0.0.1:8000/api/health; echo
fi

step "B9: Caddy (HTTPS)"
if ! command -v caddy >/dev/null; then
  apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https curl >/dev/null
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q >/dev/null && apt-get install -y -q caddy >/dev/null
fi
cat > /etc/caddy/Caddyfile.new <<EOF
{
    # No HTTP/3: UDP 443 is closed in the OCI security list and iptables. Advertising it made phones try QUIC
    # first, and uploads then failed with "Could not reach the server".
    servers {
        protocols h1 h2
    }
}

$domain {
    encode gzip
    request_body {
        max_size 25MB
    }
    reverse_proxy 127.0.0.1:8000
}
EOF
if ! cmp -s /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile; then
  mv /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
else
  rm /etc/caddy/Caddyfile.new
fi

step "B11: backups (restic to the $BUCKET bucket)"
if [[ ! -s "$ETC/restic-password" ]]; then
  if have_tty; then
    install -m 600 /dev/null "$ETC/restic-password"
    openssl rand -base64 32 > "$ETC/restic-password"
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
    read -r -p "backup-writer Access key (from the Customer secret key): " key_id
    ask_secret key_secret "backup-writer Secret key (not shown)"
    install -m 600 /dev/null "$ETC/backup.env"
    cat > "$ETC/backup.env" <<EOF
DATA_DIR=$DATA_MOUNT/data
RESTIC_REPOSITORY=s3:https://$namespace.compat.objectstorage.$REGION.oraclecloud.com/$BUCKET
AWS_DEFAULT_REGION=$REGION
AWS_ACCESS_KEY_ID=$key_id
AWS_SECRET_ACCESS_KEY=$key_secret
RESTIC_PASSWORD_FILE=$ETC/restic-password
RESTIC_CACHE_DIR=/var/cache/medical-records-backup
STATE_DIR=/var/lib/medical-records-backup
APP_STOP_CMD="systemctl stop medical-records"
APP_START_CMD="systemctl start medical-records"
EOF
    unset key_secret
  else
    todo+=("backup.env (Object Storage key): re-run from a terminal")
  fi
fi
if [[ -s "$ETC/backup.env" && -s "$ETC/restic-password" ]]; then
  restic_env() { bash -c "set -a; source $ETC/backup.env; restic -o s3.bucket-lookup=path $*"; }
  if ! restic_env cat config >/dev/null 2>&1; then
    restic_env init
  fi
  if [[ ! -s /var/lib/medical-records-backup/last-success ]] && systemctl is-active -q medical-records; then
    systemctl start medical-records-backup.service
    journalctl -u medical-records-backup.service -n 15 --no-pager
  fi
  systemctl enable -q --now medical-records-backup.timer
  systemctl list-timers medical-records-backup.timer --no-pager | head -2
fi

step "Status"
for u in medical-records caddy clamav-daemon medical-records-backup.timer; do
  printf '  %-30s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null || true)"
done
if ((${#todo[@]})); then
  echo; echo "Still to do:"; printf '  - %s\n' "${todo[@]}"
fi
