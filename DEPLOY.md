# Deploying: backups

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

## Notes

- Restoring the server's backup brings back **all users' data** as it was at that time. It is not a way to
  restore one user. Everyone is signed out after a restore.
- A document deleted during the few seconds a backup runs can be in the backup without its file. The restore
  report counts these as a warning.
- Test the scripts without any cloud account: `PYTHON=backend/.venv/bin/python scripts/test-backup.sh` (needs
  restic). CI runs this on every push.
