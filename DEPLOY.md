# Deploying: backups and monitoring

How the server's data is backed up, copied home and restored. (Server setup itself is not covered here yet.)

## How it works

- **Every night (about 02:30 IST)** a systemd timer runs `scripts/backup.sh` on the VM:
  1. A consistent copy of the SQLite database is made with SQLite's online backup API, while the app keeps running.
     Login sessions are removed from the copy, and it must pass SQLite's integrity check.
  2. The copy and every stored file (`data/files/`) are sent with [restic](https://restic.net). Restic encrypts
     everything on the VM before it leaves (AES-256), so the bucket only ever holds encrypted data. Unchanged files
     are not sent again.
  3. Old snapshots are removed: **7 daily, 4 weekly and 6 monthly** are kept.
  4. On Sundays, restic re-reads 5% of the stored data to catch damage in storage.
  5. The time of the last good backup is written to `/var/lib/medical-records-backup/last-success`. A failed run
     exits with an error, so systemd marks it as failed (#45 alerts on both).
- **Where it goes**: a private Object Storage bucket in **Mumbai (`ap-mumbai-1`)**, through Oracle's
  S3-compatible endpoint. Data does not leave India.
- **Every week** your home machine pulls new snapshots into its own restic repository on your disk
  (`scripts/pull-home-copy.sh`), with a **read-only** key: the server cannot reach or delete the home copy.
- **Restore**: `scripts/restore.sh`. By default it restores into a separate folder and checks it, without
  touching the live data. With `--apply` it replaces the live data, after moving the old data aside.

> **The restic password is the only way to read the backups.** If it is lost, every backup is lost. Keep it in
> your password manager *and* on paper, never only on the VM.

## 1. Oracle setup (once, in the Oracle Cloud console)

Use the Mumbai region (top right of the console). You need your **Object Storage namespace**: Profile menu →
Tenancy → *Object storage namespace*.

1. **Bucket**: Storage → Buckets → *Create bucket*.
   - Name `medical-records-backup`, *Standard* tier, encryption with Oracle-managed keys.
   - Leave it **private** (no pre-authenticated requests, no public visibility).
2. **Groups and users**: Identity & Security → Domains → Default domain.
   - Create the groups `medical-records-backup-writers` and `medical-records-backup-readers`.
   - Create the users `backup-writer` (for the VM) and `backup-reader` (for your home machine), one in each group.
     They do not need console passwords.
3. **Policy**: Identity & Security → Policies → *Create policy* in the bucket's compartment. Replace
   `<compartment>` with its name. If your groups live in a non-default identity domain, prefix them with the
   domain name, for example `'MyDomain'/'medical-records-backup-writers'`.

   ```text
   Allow group medical-records-backup-writers to read buckets in compartment <compartment> where target.bucket.name = 'medical-records-backup'
   Allow group medical-records-backup-writers to manage objects in compartment <compartment> where target.bucket.name = 'medical-records-backup'
   Allow group medical-records-backup-readers to read buckets in compartment <compartment> where target.bucket.name = 'medical-records-backup'
   Allow group medical-records-backup-readers to read objects in compartment <compartment> where target.bucket.name = 'medical-records-backup'
   ```

4. **Keys**: for each user, open the user → *Customer secret keys* → *Generate secret key*. The secret is shown
   **only once**. The *Access key* is in the list after you close the dialog. These pairs become
   `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

The repository address is:

```text
s3:https://<namespace>.compat.objectstorage.ap-mumbai-1.oraclecloud.com/medical-records-backup
```

**Size and cost.** Oracle's Always Free tier includes a limited amount of Object Storage (20 GB at the time of
writing, check your tenancy's limits). Above that, storage is billed. See how much the backups use with
`restic stats --mode raw-data` (step 3 below).

## 2. VM setup (once)

The scripts expect the app's data in `DATA_DIR` (default `/srv/medical-records/data`), with `medical_records.db`
and `files/` directly inside it. Those are the app's defaults when it runs from `/srv/medical-records`. The
backup's staging folder (`/srv/medical-records/.backup-staging`) must be on the **same disk** as the data, because
files are hard-linked into it, not copied.

```bash
sudo apt-get install -y restic                       # restic 0.16 or newer
sudo git clone https://github.com/namsey/medical-records /opt/medical-records   # or copy the release there

sudo install -d -m 700 /etc/medical-records
sudo sh -c 'openssl rand -base64 32 > /etc/medical-records/restic-password'
sudo chmod 600 /etc/medical-records/restic-password
sudo cat /etc/medical-records/restic-password        # copy it into your password manager NOW

sudo install -m 600 /opt/medical-records/scripts/backup.env.example /etc/medical-records/backup.env
sudo nano /etc/medical-records/backup.env            # DATA_DIR, RESTIC_REPOSITORY, the backup-writer key,
                                                     # APP_STOP_CMD / APP_START_CMD

# Create the (empty, encrypted) repository in the bucket, once:
sudo bash -c 'set -a; source /etc/medical-records/backup.env; restic -o s3.bucket-lookup=path init'

sudo cp /opt/medical-records/deploy/systemd/medical-records-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start medical-records-backup.service  # the first backup, now
sudo journalctl -u medical-records-backup.service -n 30
sudo systemctl enable --now medical-records-backup.timer
systemctl list-timers medical-records-backup.timer   # shows the next run
```

## 3. Checking the backups

```bash
cat /var/lib/medical-records-backup/last-success                      # time of the last good backup (UTC)
systemctl status medical-records-backup.service                       # did the last run fail?
sudo bash -c 'set -a; source /etc/medical-records/backup.env; restic -o s3.bucket-lookup=path snapshots'
sudo bash -c 'set -a; source /etc/medical-records/backup.env; restic -o s3.bucket-lookup=path stats --mode raw-data'
```

## 4. Weekly copy at home

On your own computer (Linux or macOS), install restic and create `~/.config/medical-records/home-copy.env`
(`chmod 600`). It uses the **backup-reader** key:

```bash
RESTIC_FROM_REPOSITORY=s3:https://<namespace>.compat.objectstorage.ap-mumbai-1.oraclecloud.com/medical-records-backup
RESTIC_FROM_PASSWORD_FILE=/home/you/.config/medical-records/server-restic-password   # the server's restic password
AWS_DEFAULT_REGION=ap-mumbai-1
AWS_ACCESS_KEY_ID=<backup-reader access key>
AWS_SECRET_ACCESS_KEY=<backup-reader secret key>
RESTIC_REPOSITORY=/media/you/backup-disk/medical-records          # on your home disk
RESTIC_PASSWORD_FILE=/home/you/.config/medical-records/home-restic-password     # a NEW password for the home copy
```

Then run `scripts/pull-home-copy.sh` by hand once, and every week from cron (`crontab -e`):

```text
0 10 * * 0  /path/to/medical-records/scripts/pull-home-copy.sh >> ~/medical-records-home-copy.log 2>&1
```

The home repository keeps 8 weekly and 12 monthly snapshots. The first run creates it.

**Windows**: install restic (`winget install restic.restic`), put the same values in environment variables, and
schedule this weekly in Task Scheduler:

```powershell
restic -o s3.bucket-lookup=path -o s3.region=ap-mumbai-1 --no-lock copy
restic forget --keep-weekly 8 --keep-monthly 12 --prune
```

(Create the home repository once first with
`restic -o s3.bucket-lookup=path -o s3.region=ap-mumbai-1 init --copy-chunker-params`.)

## 5. Restore drill (every month, about 10 minutes)

A backup is only useful if it restores. Do this monthly, and always after changing anything about backups.

1. Restore the latest snapshot into a scratch folder. The live data is not touched:

   ```bash
   sudo /opt/medical-records/scripts/restore.sh            # or: restore.sh <snapshot id> (see "restic snapshots")
   ```

   The report must say `OK database integrity check` and `OK every document has its file`. It also shows the
   schema revision and the number of users, records and documents. They should match what you expect.
2. Look at the restored data with the app, on another port, reachable only from the VM. Use the restored folder
   printed in step 1:

   ```bash
   cd /opt/medical-records/backend
   sudo DATABASE_URL=sqlite:////var/lib/medical-records-backup/restore-XXXXXX/database/medical_records.db \
        FILES_DIR=/var/lib/medical-records-backup/restore-XXXXXX/files \
        .venv/bin/python -m app --port 8001
   ```

   From your computer: `ssh -L 8001:127.0.0.1:8001 <vm>`, then open <http://localhost:8001>. Sign-in needs an
   OAuth redirect for that address, so for a quick look the report from step 1 is usually enough.
3. Delete the restored folder. **It is not encrypted.**

   ```bash
   sudo rm -rf /var/lib/medical-records-backup/restore-*
   ```

4. Note the drill below.

| Date | Snapshot | Result | Notes |
| --- | --- | --- | --- |
| | | | |

## 6. Disaster recovery (the VM or its disk is gone)

1. Create a new VM in Mumbai and set up the app (no data yet).
2. Follow section 2 up to and including `backup.env` (same repository, same restic password). **Do not** run
   `restic init` again.
3. `sudo /opt/medical-records/scripts/restore.sh --apply`. It restores the latest snapshot, checks it, stops
   the app, puts the data in place and starts the app. If the backup is from an older version, the app upgrades
   it when it starts.
4. Point the DNS name at the new VM, then enable the backup timer.

To roll back on a working server (for example after a bad change), `restore.sh --apply <snapshot id>` does the
same. The data it replaces is moved to `DATA_DIR.before-restore-<time>`, never deleted.

## 7. Optional: virus scan of uploads (ClamAV)

Off by default. When it is on, every uploaded file is scanned before it is saved. If the scanner does not answer,
the upload is refused (never saved unscanned). clamd needs about 1 GB of RAM.

```bash
sudo apt-get install -y clamav-daemon
sudo systemctl enable --now clamav-freshclam clamav-daemon     # signatures update by themselves
sudo usermod -aG clamav <the user the app runs as>              # so the app can use clamd's socket
```

Then add `CLAMAV_SOCKET=/run/clamav/clamd.ctl` to the app's environment and restart it. To check it:

1. clamd itself: download the harmless EICAR test file from eicar.org and run `clamdscan eicar.com`; it must say
   `FOUND`. (Uploading it to the app is not a useful test: the app refuses it earlier, because it is not a real
   PDF or image.)
2. The app's connection: upload an ordinary PDF. It only saves if clamd answered, and if it cannot reach clamd the
   app says "The virus scanner is not available" and logs "Virus scanner unavailable".

clamd's default stream limit (25 MB) is above the 20 MB file limit.

## 8. Monitoring and alerts

The app has three public health checks. Each answers `200 {"status": "ok"}` or `503 {"status": "problem",
"reason": ...}` and nothing else (no numbers, paths or user data):

| Check | Fails when |
| --- | --- |
| `/api/health` | the app or its database is down (or the whole VM: then nothing answers) |
| `/api/health/disk` | the data disk or the system disk is more than 80% full (`DISK_ALERT_PERCENT`) |
| `/api/health/backup` | the last backup run failed, or no backup succeeded in the last 26 hours (`BACKUP_MAX_AGE_HOURS`) |

**Admin → Server** in the app shows the details: disk use per disk, the last good and failed backup, and when the
app started.

### App settings

Add to the app's environment (`/etc/medical-records/app.env`) and restart it:

```bash
BACKUP_STATUS_DIR=/var/lib/medical-records-backup   # where backup.sh writes last-success and last-failure
```

### Alerts with UptimeRobot (free plan)

UptimeRobot is a US service. It learns only your app's address and whether these checks answer ok, never any
user data.

1. Sign up at uptimerobot.com with your email, and confirm the email alert contact.
2. Add three **HTTP(s)** monitors, interval 5 minutes:
   - `Medical records: app` → `https://<your domain>/api/health`
   - `Medical records: disk` → `https://<your domain>/api/health/disk`
   - `Medical records: backup` → `https://<your domain>/api/health/backup`
3. Alert the email contact on "down" and "up" for each.
4. Test it: stop the app (`sudo systemctl stop medical-records`). Within about 10 minutes you get emails for all
   three. Start it again, and the "up" emails follow.

A backup that fails at night turns `/api/health/backup` red straight away. The next good backup clears it.

If Oracle ever stops or reclaims the VM (for example under the Always Free idle rules), the `app` monitor reports it.

### App service and log rotation

The app runs as a systemd service. Its logs and the backup's go to the system journal, which is capped at 500 MB
and one month:

```bash
sudo useradd --system --home /srv/medical-records --shell /usr/sbin/nologin medical-records
sudo install -m 600 -o medical-records /dev/null /etc/medical-records/app.env   # then fill it in
sudo cp /opt/medical-records/deploy/systemd/medical-records.service /etc/systemd/system/
sudo install -D -m 644 /opt/medical-records/deploy/journald/medical-records.conf \
     /etc/systemd/journald.conf.d/medical-records.conf
sudo systemctl restart systemd-journald
sudo systemctl daemon-reload && sudo systemctl enable --now medical-records
journalctl -u medical-records -n 50        # the app's recent log lines
journalctl --disk-usage                    # stays under 500 MB
```

The app never logs record contents, search terms or file names.

## Notes

- Restoring the server's backup brings back **all users' data** as it was at that time. It is not a way to
  restore one user. Everyone is signed out after a restore.
- A document deleted during the few seconds a backup runs can be in the backup without its file. The restore
  report counts these as a warning.
- Test the scripts without any cloud account: `PYTHON=backend/.venv/bin/python scripts/test-backup.sh` (needs
  restic). CI runs this on every push.
