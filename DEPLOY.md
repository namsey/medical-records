# Deploying on Oracle Cloud Free Tier (India)

A step-by-step guide to running this app for invited users on Oracle Cloud's Always Free tier, with all data kept in
India: first the Oracle resources (Part A), then the server (Part B), then running it day to day (Part C).

> **Which code:** this guide is for the multi-user version (roadmap #38–#45: invites, data separation, backups,
> quotas, privacy, monitoring). Deploy from `main` once that work is merged there (until then it is on the
> `claude/feature` branch). The deploy files it uses (`deploy/`, `scripts/`) come with that code.

## What you end up with

```text
 Phone / browser ──HTTPS──▶ Caddy (TLS, Let's Encrypt) ──▶ app (FastAPI)   Docker Compose stack, deployed by an
                                     one Ampere A1 VM, Ubuntu 24.04, Oracle Mumbai    agent from OCI Container Registry
                                              │
                         block volume /srv/medical-records (SQLite database + files)
                                              │  nightly, encrypted (restic)
                                              ▼
                          Object Storage bucket, Oracle Mumbai ──weekly──▶ your disk at home
 UptimeRobot ──checks /api/health, /disk, /backup every 5 min──▶ emails you when something is wrong
```

**About the database.** The app uses **SQLite**: the database is one file (`medical_records.db`) on the VM's data
disk. You do **not** create an Oracle Database (Autonomous Database, MySQL HeatWave or Base Database). The app
cannot use them, and they would only add cost and another place for health data. The "database resource" you
create on Oracle is the **block volume** that holds the SQLite file and the attached files (step A8).

### What it uses from the Always Free tier

Check Oracle's current Always Free page before you start: the limits below are from the time of writing.

| Resource | Used here | Always Free allowance (at the time of writing) |
| --- | --- | --- |
| Ampere A1 compute | 2 VMs: prod 1 OCPU / 8 GB, staging 1 OCPU / 4 GB | 1,500 OCPU-hours and 9,000 GB-hours a month: 2 OCPUs and 12 GB RAM in total, running all month |
| Boot + block volumes | 2 × 50 GB boot + 100 GB data (prod) = 200 GB | 200 GB in total |
| Object Storage | encrypted backups (prod) | 20 GB, 50,000 requests a month |
| Outbound data | the app's traffic | 10 TB a month |
| Public IPv4 | 2 reserved (one per VM) | – |

Always Free resources only exist in your **home region**, and you choose that once, when you sign up.

**The two VMs together are the whole A1 allowance** (2 OCPUs, 12 GB, and all 200 GB of storage). Oracle cut it
from 4 OCPUs / 24 GB: do not make either VM bigger or add a third A1 instance. On a free (not Pay As You Go)
account, an instance over the limit gets shut down. Terraform refuses a plan that goes over these totals.

### What you need before you start

- A computer with a terminal (Linux, macOS, or Windows with PowerShell / WSL) and SSH.
- A Google account for the admin (`ADMIN_EMAIL`) and a Google Cloud project for sign-in (step A11).
- A domain name you control (for example `records.yourname.in`), or a free subdomain from a dynamic-DNS service.
  HTTPS needs a name; a bare IP address will not work for Google sign-in.
- A password manager, for the restic password and the app's secrets.

---

## Part A: Oracle Cloud resources (in the web console)

### Two environments, created by Terraform

`infra/` creates everything below for two environments, **prod** and **staging**, in one VCN (`10.0.0.0/16`):

| | prod | staging |
| --- | --- | --- |
| VM (`VM.Standard.A1.Flex`, Ubuntu 24.04) | `medical-records-prod`: 1 OCPU, 8 GB RAM | `medical-records-staging`: 1 OCPU, 4 GB RAM |
| Fault domain | `FAULT-DOMAIN-1` | `FAULT-DOMAIN-2` |
| Subnet and security list | `10.0.0.0/24` | `10.0.1.0/24` |
| Boot volume | 50 GB | 50 GB |
| Data volume (A8) | 100 GB at `/dev/oracleoci/oraclevdb` | **none**: data lives on the boot volume |
| Reserved public IP | yes | yes |
| Backups (A9: bucket, users, policy) and budget (A2) | yes | **none** |

Together that is 2 of 2 OCPUs, 12 of 12 GB RAM and 200 of 200 GB of boot + block storage, so there is no room to
give staging a data volume or either VM more. The sizes are in the `environments` variable (`infra/variables.tf`),
and `terraform plan` stops with a clear message if they go over the Always Free totals.

Staging is for trying changes, with synthetic data only: it has no backups, and nothing on it is kept. It needs its
**own domain name** (for example a second DuckDNS name, A10) and its **own Google OAuth client** (A11), so a
staging sign-in can never be redirected to prod.

You still do A1, A3, A5, A10 and A11 by hand. Copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars`,
fill it in, then run `terraform init` and `terraform plan` / `terraform apply` in `infra/`. `terraform output`
shows each VM's public IP and SSH command. The console steps below are what Terraform does, for reference.
Terraform also creates the container registry and its two users (A12); their auth tokens are made by hand.

### A1. Create the Oracle Cloud account (home region: Mumbai)

1. Sign up at <https://www.oracle.com/cloud/free/>.
2. When asked for the **home region**, choose **India West (Mumbai)** (`ap-mumbai-1`). India South (Hyderabad) also
   keeps data in India, but this guide and the backup settings use Mumbai. **The home region cannot be changed
   later**, and Always Free resources only exist there.
3. Card verification makes a small temporary charge; Always Free resources stay free.
4. Turn on multi-factor authentication for your Oracle login (Profile → My profile → Security / MFA).

**Optional: upgrade to Pay As You Go** (Billing & Cost Management → Upgrade and manage payment). Always Free
resources stay free after upgrading. It usually makes it easier to get Ampere capacity, and Oracle's reclaiming of
idle Always Free instances applies to free-tier accounts (check Oracle's current policy). If you upgrade, do step
A2 first so nothing paid can surprise you.

### A2. Budget alert (so nothing costs money by surprise)

Billing & Cost Management → **Budgets** → *Create budget*:

- Target: your root compartment (the tenancy). Amount: for example ₹100 a month.
- Alert rule: *Actual spend* above **1%** of the budget, email to you.

Any paid resource you create by mistake then emails you within a day.

### A3. Compartment

Identity & Security → **Compartments** → *Create compartment*: name `medical-records`, parent: the root
compartment. Create everything below in this compartment (pick it in the *Compartment* list on each page).

### A4. Network (VCN, public subnet, firewall rules)

1. Networking → **Virtual cloud networks** → *Start VCN Wizard* → **Create VCN with Internet Connectivity**.
2. Name `medical-records-vcn`, compartment `medical-records`. Keep the default address ranges (VCN `10.0.0.0/16`,
   public subnet `10.0.0.0/24`). *Next* → *Create*.
3. Open the new VCN → **Security Lists** → *Default Security List for medical-records-vcn* → **Ingress rules**:
   - Edit the SSH rule (port 22): change the source from `0.0.0.0/0` to **your own public IP** with `/32`
     (search "what is my IP"). If your home IP changes, update this rule.
   - *Add ingress rules*: source `0.0.0.0/0`, TCP, destination port **80** (Let's Encrypt and the redirect to HTTPS).
   - *Add ingress rules*: source `0.0.0.0/0`, TCP, destination port **443** (the app).

Terraform instead gives each environment its own subnet (`10.0.0.0/24` prod, `10.0.1.0/24` staging) with its own
security list holding these three rules, and empties the default security list (no rules, attached to nothing).

### A5. SSH key (on your own computer)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle-medical-records -C "medical-records VM"
cat ~/.ssh/oracle-medical-records.pub        # you paste this into Oracle in A6
```

Keep the private key (`~/.ssh/oracle-medical-records`) safe; it is the only way into the VM.

### A6. Compute instance (the VM)

Compute → **Instances** → *Create instance*:

1. **Name** `medical-records-prod` (and `medical-records-staging`), compartment `medical-records`.
2. **Placement**: the availability domain shown (Mumbai has one).
3. **Image and shape** → *Edit*:
   - *Change image* → **Canonical Ubuntu 24.04** (the aarch64 build is picked automatically for Ampere).
   - *Change shape* → **Ampere** → `VM.Standard.A1.Flex`, **1 OCPU, 8 GB memory** for prod (**1 OCPU, 4 GB** for
     staging). It shows "Always Free-eligible". (2 OCPUs / 12 GB in total is now the whole Always Free A1
     allowance, 1,500 OCPU-hours and 9,000 GB-hours a month. Do not go bigger: on a free account an instance over
     the limit gets shut down.)
4. **Networking**: `medical-records-vcn`, its **public subnet**, *Automatically assign public IPv4 address*: yes.
5. **Add SSH keys** → *Paste public keys* → the line from A5.
6. **Boot volume**: keep the default size (about 47–50 GB) and in-transit encryption on.
7. *Create*. When it shows **Running**, note its **Public IP address**.

**"Out of capacity for shape VM.Standard.A1.Flex"** is common. Try again later (early morning IST often works),
try 1 OCPU / 6 GB and resize later, or upgrade to Pay As You Go (A1).

The public IP stays the same while the instance exists, including across stop and start. If you ever rebuild the
VM, point the DNS record (A10) at the new address. (A *reserved* public IP, under Networking → IP management, keeps
the address across rebuilds; check that it stays within your free allowance before using one.)

### A7. Try the SSH connection

```bash
ssh -i ~/.ssh/oracle-medical-records ubuntu@<public IP>
```

The user on Oracle's Ubuntu images is `ubuntu`. Type `exit` to leave again.

### A8. Block volume for the database and files

This disk holds the SQLite database and every uploaded file, separate from the system disk, so the app's data
survives rebuilding or replacing the VM.

Prod only: staging has no data volume (the 200 GB are used up), so its data stays on its boot volume.

1. Storage → **Block volumes** → *Create block volume*: name `medical-records-prod-data`, compartment
   `medical-records`, the **same availability domain** as the VM, size **100 GB** (boot + block volumes share the
   200 GB allowance), default performance (*Balanced*), Oracle-managed encryption key. *Create*.
2. Compute → Instances → `medical-records-prod` → **Attached block volumes** → *Attach block volume*:
   - Volume: `medical-records-prod-data`.
   - Attachment type: **Paravirtualized** (no iSCSI commands needed).
   - Device path: **`/dev/oracleoci/oraclevdb`**.
   - Access: read/write. *Attach*.

The volume is formatted and mounted on the server in step B4. Never put the SQLite file on Oracle File Storage
(NFS): SQLite in WAL mode needs a local disk.

### A9. Object Storage bucket and keys for backups

Prod only: staging has no backups.

You need your **Object Storage namespace**: Profile menu → Tenancy → *Object storage namespace*.

1. **Bucket**: Storage → **Buckets** → *Create bucket* (compartment `medical-records`).
   - Name `medical-records-backup`, *Standard* tier, encryption with Oracle-managed keys.
   - Leave it **private** (no pre-authenticated requests, no public visibility).
2. **Groups and users**: Identity & Security → Domains → Default domain.
   - Create the groups `medical-records-backup-writers` and `medical-records-backup-readers`.
   - Create the users `backup-writer` (for the VM) and `backup-reader` (for your home machine), one in each group.
     They do not need console passwords.
3. **Policy**: Identity & Security → **Policies** → *Create policy* in compartment `medical-records`, with these
   statements (if your groups are in a non-default identity domain, prefix them, for example
   `'MyDomain'/'medical-records-backup-writers'`):

   ```text
   Allow group medical-records-backup-writers to read buckets in compartment medical-records where target.bucket.name = 'medical-records-backup'
   Allow group medical-records-backup-writers to manage objects in compartment medical-records where target.bucket.name = 'medical-records-backup'
   Allow group medical-records-backup-readers to read buckets in compartment medical-records where target.bucket.name = 'medical-records-backup'
   Allow group medical-records-backup-readers to read objects in compartment medical-records where target.bucket.name = 'medical-records-backup'
   ```

4. **Keys**: for each of the two users, open the user → *Customer secret keys* → *Generate secret key*. The
   secret is shown **only once**; the *Access key* is in the list after you close the dialog. Put both pairs in
   your password manager: they become `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

The backup repository address is:

```text
s3:https://<namespace>.compat.objectstorage.ap-mumbai-1.oraclecloud.com/medical-records-backup
```

### A10. Domain name (DNS)

At your domain's DNS provider, create an **A record**: `records.yourname.in` → the VM's public IP (A6). Staging
gets a second name (for example `staging-records.yourname.in`, or its own DuckDNS name) → the staging VM's IP.
Check it from your computer before going on (it can take a few minutes up to a few hours):

```bash
nslookup records.yourname.in      # must show the VM's IP
```

Extra names that should only redirect to the main one (prod's `www.records.yourname.in`, or the old name for a
while after moving to a new domain) get their own A record to the same IP and an `--alias` in Part B; Caddy gets a
certificate for each and answers with a permanent redirect. When you move to a new domain, also change the Google
OAuth redirect URI (A11, and `GOOGLE_REDIRECT_URI` in B7) and the `APP_URL` of that GitHub environment
(docs/CICD.md).

Cloudflare in front (orange cloud) works too: set SSL/TLS to **Full (strict)**. Caddy takes the visitor's IP from
`CF-Connecting-IP` only when the request really comes from one of Cloudflare's address ranges (listed in
`deploy/compose/Caddyfile`; check them against https://www.cloudflare.com/ips/ now and then).

### A11. Google sign-in (OAuth client)

Google only confirms who is signing in; it never sees records.

1. <https://console.cloud.google.com> → create a project, for example `medical-records`.
2. **APIs & Services → OAuth consent screen** (Google Auth Platform → Branding / Audience):
   - User type **External**, app name, your support email and developer contact.
   - Scopes: only `openid`, `email` and `profile` (non-sensitive, no Google review needed).
   - **Publishing status: In production**, so invited people can sign in without being added as Google test users.
3. **Credentials → Create credentials → OAuth client ID** → *Web application*:
   - Authorized redirect URI: `https://records.yourname.in/api/auth/callback` (exactly).
   - Note the **Client ID** and **Client secret** (password manager).
4. For staging, create a **second OAuth client** the same way, with the staging name in its redirect URI
   (`https://staging-records.yourname.in/api/auth/callback`). Never add the staging URI to the prod client.

### A12. Container registry (OCIR) and its users

The VMs never build the app: they run the app image from a private repository in **OCI Container Registry**
(Mumbai), `medical-records/app`. Terraform (`infra/ocir.tf`) creates it with two users that can only touch the
repositories in the `medical-records` compartment (only this one):

| User | Group / policy | Used by | May |
| --- | --- | --- | --- |
| `ci-image-pusher` | `medical-records-image-pushers`, *manage repos* (in the `medical-records` compartment) | GitHub Actions (docs/CICD.md; and you, when publishing by hand: B9) | push images, move tags |
| `vm-image-puller` | `medical-records-image-pullers`, *read repos* | both VMs | pull only |

1. In `infra/`: `terraform plan` (it adds the repository, two groups, two users, two memberships and one policy,
   and changes nothing else), then `terraform apply`. Note the outputs:

   ```bash
   terraform output ocir_registry      # bom.ocir.io
   terraform output ocir_repository    # bom.ocir.io/<namespace>/medical-records/app
   terraform output ocir_usernames     # the docker login names of the two users
   ```

2. **Auth tokens** (the registry passwords; Terraform does not make them, so they never land in its state). For
   each of the two users: Identity & Security → **Domains** → *Default domain* → **User management** → **Users** →
   the user → **Auth tokens** (in newer consoles under the *Tokens and keys* tab) → *Generate token*, description
   `medical-records registry`. The token is shown **only once**: put it in your password manager. A user can have
   at most two tokens; to replace one, generate the new one, update where it is used, then delete the old one.
3. **Login username**: `<namespace>/<username>` for users in the Default identity domain, for example
   `<namespace>/vm-image-puller`; for a user in another identity domain, `<namespace>/<domain name>/<username>`.
   The registry host is `bom.ocir.io` and the password is the auth token. Try it from your computer:
   `docker login bom.ocir.io -u <namespace>/ci-image-pusher`.

---

## Part B: Server setup (over SSH)

One script prepares each VM, and a small agent on it then deploys whatever image the OCIR tag for that environment
points at: `staging` on the staging VM, `prod` on prod.

```text
 you / pipeline ──push image, move tag "staging" or "prod"──▶ OCIR medical-records/app
                                                                     │  checked every 2 minutes
 VM: medical-records-deploy (systemd timer) ◀──────────────────────┘
       pull by digest ─▶ compose files of that commit ─▶ docker compose up ─▶ healthy? keep : go back
```

Copy the script to each VM and run it from a real terminal (`ssh -t`), so it can ask for the secrets:

```bash
scp -i ~/.ssh/oracle-medical-records scripts/host-setup.sh ubuntu@<prod IP>:
ssh -t -i ~/.ssh/oracle-medical-records ubuntu@<prod IP> sudo ./host-setup.sh --env prod \
  --domain records.yourname.in --alias www.records.yourname.in --registry bom.ocir.io \
  --repository bom.ocir.io/<namespace>/medical-records/app --format-data-volume

scp -i ~/.ssh/oracle-medical-records scripts/host-setup.sh ubuntu@<staging IP>:
ssh -t -i ~/.ssh/oracle-medical-records ubuntu@<staging IP> sudo ./host-setup.sh --env staging \
  --domain staging-records.yourname.in --registry bom.ocir.io \
  --repository bom.ocir.io/<namespace>/medical-records/app
```

`--format-data-volume` only on prod's very first run (B4). `--alias` is optional and repeatable (A10); give the
same ones on every run, because the compose `.env` is rewritten. It asks for:

- the Google OAuth client ID and secret (**staging: its own client from A11**, never prod's), the admin email and
  the grievance officer;
- the `vm-image-puller` auth token (A12);
- prod only: the `backup-writer` key (A9), and it shows the new restic password once (B11).

It is safe to run again (after a reboot, to change a setting, or to update the agent); it keeps what exists and
lists anything still to do at the end. B1–B9 below are what it does.

### B1. Updates and tools

`git`, `python3`, `sqlite3`, `restic` (prod) and automatic security updates (`unattended-upgrades`). The app itself
runs in its image (Python 3.13); the VM's own `python3` is only used by the backup scripts.

### B2. Ports 80 and 443 inside the VM

Oracle's Ubuntu images have their own firewall (iptables) that only lets SSH in, on top of the security list from
A4. The script allows web traffic and saves the rules:

```bash
sudo iptables -L INPUT -n --line-numbers | head      # the ACCEPT for 80,443 comes before any REJECT
```

### B3. Docker Engine, Compose and Buildx

From Docker's own apt repository (Ubuntu's `docker.io` package has no Compose v2). VMs created from the current
`infra/cloud-init.yaml` already have them; on older VMs the script installs them.

### B4. The data volume (prod) or folder (staging)

Prod: the 100 GB volume (A8) is formatted only with `--format-data-volume` and only if it has no filesystem yet,
then mounted at `/srv/medical-records` (in `/etc/fstab` with `nofail`). If you ever attach this volume to a new VM,
leave the option out: it is just mounted. Staging has no data volume: `/srv/medical-records` is on its boot volume.

### B5. Data folder

`/srv/medical-records/data`, mode 700, owned by **10001:10001**, the user and group the app container runs as (there
is no such user on the VM, and none is needed). The database, files and the app's pre-migration copies live there.

### B6. Code, compose files and the registry sign-in

- `/opt/medical-records/repo`: a clone of this repository. The agent keeps it at the commit of the image that is
  running, so the backup scripts and compose files always match the app.
- `/opt/medical-records/compose`: `compose.yaml` and `Caddyfile` from that commit, and `.env` with `DATA_DIR`,
  `SITE_DOMAIN`, `SITE_ALIASES` (the `--alias` names), `APP_MEMORY_LIMIT` (prod 2g, staging 1g) and `APP_IMAGE` (empty until the first deploy).
- `docker login bom.ocir.io` as `<namespace>/vm-image-puller` (A12), stored in `/root/.docker/config.json`.

### B7. App settings

`/etc/medical-records/app.env` (mode 600, root), from the answers above:

```bash
GOOGLE_CLIENT_ID=<from A11>
GOOGLE_CLIENT_SECRET=<from A11>
GOOGLE_REDIRECT_URI=https://records.yourname.in/api/auth/callback
ADMIN_EMAIL=<your Google email: the admin account>
SESSION_SECRET=<generated on the VM: each VM has its own>
GRIEVANCE_NAME=<your name>
GRIEVANCE_EMAIL=<email for privacy questions>
BACKUP_STATUS_DIR=/var/lib/medical-records-backup     # prod
CLAMAV_SOCKET=/run/clamav/clamd.ctl                   # prod (C6)
# Optional: DEFAULT_QUOTA_MB=100   MAX_UPLOAD_SIZE_MB=20   SESSION_IDLE_HOURS=24
```

Where the data lives (`DATABASE_URL`, `FILES_DIR`, `UPLOAD_DIR`) is set by `compose.yaml`: inside the container it
is `/data`. The app refuses to start if a required setting is missing or if `GOOGLE_REDIRECT_URI` is not
`https://`. After changing `app.env`, recreate the app: the container reads it only when it is created:

```bash
sudo medical-records-compose up -d --force-recreate --wait app
```

### B8. The stack: app + Caddy, and `medical-records-compose`

Every `docker compose` command for the stack goes through `medical-records-compose`, which runs in
`/opt/medical-records/compose` (and refuses until an image is deployed):

```bash
sudo medical-records-compose ps                     # app (healthy) and caddy, both Up
sudo medical-records-compose logs --tail 50 app     # the app's recent log lines
journalctl -t medical-records-app -n 50             # the same, from the journal (also after a redeploy)
```

The app container runs as 10001 with a read-only system, can write only `/data` (and `/tmp`), and is not published
on any port: only Caddy reaches it, over the stack's own network. Caddy is the second container, on ports 80 and
443: it gets and renews the Let's Encrypt certificate by itself (it needs the DNS record from A10 and ports 80/443
open in A4 and B2), keeps it in a Docker volume, and passes each visitor's real IP to the app (trusted only from
Caddy's fixed address; behind Cloudflare, the IP from `CF-Connecting-IP`, see A10). HTTP/3 is off on purpose: UDP 443 is closed, and phones that tried it first failed to
upload. Both containers restart by themselves after a crash or a reboot. Their logs go to the journal, capped at
500 MB and one month (`deploy/journald/medical-records.conf`). The app never logs record contents, search terms or
file names.

### B9. The deploy agent

`medical-records-deploy` runs every 2 minutes (`medical-records-deploy.timer`). Each run:

1. reads which digest the environment's tag points at (`staging` or `prod`); if it is the one running, it stops;
2. prod: takes a backup first (B11; not on the very first deploy). If the backup fails, nothing changes, and it
   tries again for that image after 30 minutes;
3. pulls the image by digest, checks out its commit (the image's `org.opencontainers.image.revision` label) in
   `/opt/medical-records/repo` and installs that commit's `compose.yaml` and `Caddyfile`;
4. sets `APP_IMAGE`, runs `docker compose up -d` and waits up to 3 minutes until the app container is healthy and
   `https://<domain>/api/health` answers ok through Caddy;
5. healthy: done. Not healthy: it goes back to the image and compose files that ran before, remembers the new digest
   as bad (it is skipped until the tag points at another image), and the run fails (`systemctl status` and the
   journal show it). A failed **first** deploy stops the app, as there is nothing to go back to.

```bash
systemctl status medical-records-deploy.timer        # active (waiting), next run within 2 minutes
journalctl -u medical-records-deploy -n 30           # what the last runs did
cat /var/lib/medical-records/deploy.log              # one line per deploy or failure
cat /var/lib/medical-records/deployed-digest         # what runs now
sudo touch /etc/medical-records/deploy-paused        # pause it (maintenance, a breach); rm the file to resume
```

Until a tag exists the agent only logs "No 'prod' tag … yet". `restore.sh --apply` holds the agent's lock, so no
deploy starts the app halfway through a restore.

**Publishing an image by hand.** Normally the Deliver workflow does this (docs/CICD.md); by hand is for the first
image or when GitHub Actions is down. On your computer, from a commit that is on `main` on GitHub (the agent
fetches that commit), with Docker Buildx:

```bash
REPO=bom.ocir.io/<namespace>/medical-records/app
SHA=$(git rev-parse HEAD)
docker login bom.ocir.io -u <namespace>/ci-image-pusher        # password: its auth token (A12)
docker buildx build --platform linux/arm64,linux/amd64 \
  --build-arg GIT_SHA=$SHA --build-arg APP_VERSION=main-${SHA:0:7} -t $REPO:sha-$SHA --push .
docker buildx imagetools create -t $REPO:staging $REPO:sha-$SHA   # staging deploys it within ~2 minutes
# after checking staging:
docker buildx imagetools create -t $REPO:prod $REPO:sha-$SHA      # prod: backup, then deploy
```

The arm64 half is built under emulation unless your computer is arm64 (an Apple Silicon Mac builds it natively).

### B10. First sign-in

1. Open `https://records.yourname.in` on your phone and **Sign in with Google** with the `ADMIN_EMAIL` account.
2. Read and accept the privacy notice (review its wording first: see the README, "Privacy and your data").
3. **Profile → Admin** is there. Do not invite anyone until B11 and B12 are done and you have done one restore
   drill (C3).

### B11. Backups (restic to the Mumbai bucket)

Prod only: staging has no backups. `host-setup.sh --env prod` sets them up:

- `/etc/medical-records/restic-password`: a new random password, **shown once** while the script runs. Copy it into
  your password manager and onto paper before you type `saved`.
- `/etc/medical-records/backup.env` (mode 600), from the `backup-writer` key (A9):

  ```bash
  DATA_DIR=/srv/medical-records/data
  RESTIC_REPOSITORY=s3:https://<namespace>.compat.objectstorage.ap-mumbai-1.oraclecloud.com/medical-records-backup
  AWS_DEFAULT_REGION=ap-mumbai-1
  AWS_ACCESS_KEY_ID=<backup-writer access key from A9>
  AWS_SECRET_ACCESS_KEY=<backup-writer secret key from A9>
  RESTIC_PASSWORD_FILE=/etc/medical-records/restic-password
  RESTIC_CACHE_DIR=/var/cache/medical-records-backup
  STATE_DIR=/var/lib/medical-records-backup
  APP_STOP_CMD="medical-records-compose stop app"
  APP_START_CMD="medical-records-compose start app"
  DATA_OWNER=10001:10001
  ```

- `restic init`, only when the bucket holds no repository yet; then the nightly timer (02:30 IST).

It does **not** take a first backup by itself (on a rebuilt VM that would put an empty snapshot on top of the real
ones). The agent backs up before every switch to a new image, and the timer every night. Once the app runs, take
the first one by hand and check it:

```bash
sudo systemctl start medical-records-backup.service  # a backup, now
sudo journalctl -u medical-records-backup.service -n 30
systemctl list-timers medical-records-backup.timer   # next run: about 02:30 IST
curl -s https://records.yourname.in/api/health/backup   # {"status":"ok"}
```

> **The restic password is the only way to read the backups.** If it is lost, every backup is lost. Keep it in
> your password manager *and* on paper, never only on the VM.

How the nightly backup works:

- It copies the SQLite database with SQLite's online backup API while the app keeps running (login sessions are
  removed from the copy, and it must pass SQLite's integrity check), then hard-links the stored files next to it.
  The copy's folder (`/srv/medical-records/.backup-staging`) is on the same disk and is always removed afterwards.
- restic encrypts everything on the VM (AES-256) and sends only what changed to the private Mumbai bucket.
- It keeps **7 daily, 4 weekly and 6 monthly** snapshots, and on Sundays re-reads 5% of the stored data.
- It writes the time of the last good run to `/var/lib/medical-records-backup/last-success`, and of a failed run
  to `last-failure`; `/api/health/backup` reads them (B12).

### B12. Monitoring and alerts (UptimeRobot)

The app has three public health checks. Each answers `200 {"status": "ok"}` or `503 {"status": "problem",
"reason": ...}` and nothing else (no numbers, paths or user data):

| Check | Fails when |
| --- | --- |
| `/api/health` | the app or its database is down (or the whole VM: then nothing answers) |
| `/api/health/disk` | the data disk or the system disk is more than 80% full (`DISK_ALERT_PERCENT`) |
| `/api/health/backup` | the last backup run failed, or no backup succeeded in 26 hours (`BACKUP_MAX_AGE_HOURS`) |

UptimeRobot is a US service. It learns only your app's address and whether these checks answer ok, never any
user data.

1. Sign up at <https://uptimerobot.com> with your email, and confirm the email alert contact.
2. Add three **HTTP(s)** monitors, interval 5 minutes:
   - `Medical records: app` → `https://records.yourname.in/api/health`
   - `Medical records: disk` → `https://records.yourname.in/api/health/disk`
   - `Medical records: backup` → `https://records.yourname.in/api/health/backup`
3. Alert the email contact on "down" and "up" for each.
4. Test it: `sudo medical-records-compose stop app`. Within about 10 minutes you get emails for all three.
   `sudo medical-records-compose start app`, and the "up" emails follow. (The agent does not restart a stopped
   app; it only acts when the `prod` tag moves.)

**Admin → Server** in the app shows the details: disk use per disk, the last good and failed backup, and when the
app started. If Oracle ever stops or reclaims the VM, the `app` monitor reports it.

### B13. Weekly copy of the backups at home

On your own computer (Linux or macOS), install restic and create `~/.config/medical-records/home-copy.env`
(`chmod 600`). It uses the **backup-reader** key, so the server can never reach or delete the home copy:

```bash
RESTIC_FROM_REPOSITORY=s3:https://<namespace>.compat.objectstorage.ap-mumbai-1.oraclecloud.com/medical-records-backup
RESTIC_FROM_PASSWORD_FILE=/home/you/.config/medical-records/server-restic-password   # the server's restic password
AWS_DEFAULT_REGION=ap-mumbai-1
AWS_ACCESS_KEY_ID=<backup-reader access key>
AWS_SECRET_ACCESS_KEY=<backup-reader secret key>
RESTIC_REPOSITORY=/media/you/backup-disk/medical-records          # on your home disk
RESTIC_PASSWORD_FILE=/home/you/.config/medical-records/home-restic-password     # a NEW password for the home copy
```

Run `scripts/pull-home-copy.sh` (from a clone of this repository) by hand once, then every week from cron
(`crontab -e`):

```text
0 10 * * 0  /path/to/medical-records/scripts/pull-home-copy.sh >> ~/medical-records-home-copy.log 2>&1
```

The home repository keeps 8 weekly and 12 monthly snapshots; the first run creates it.

**Windows**: install restic (`winget install restic.restic`), put the same values in environment variables, create
the home repository once with `restic -o s3.bucket-lookup=path -o s3.region=ap-mumbai-1 init --copy-chunker-params`,
and schedule this weekly in Task Scheduler:

```powershell
restic -o s3.bucket-lookup=path -o s3.region=ap-mumbai-1 --no-lock copy
restic forget --keep-weekly 8 --keep-monthly 12 --prune
```

### B14. Security checklist before inviting anyone

- [ ] SSH only with your key, and only from your IP (A4). Oracle's Ubuntu images already disable password login.
- [ ] Multi-factor authentication on your Oracle account (A1) and on the admin Google account.
- [ ] Budget alert set (A2).
- [ ] `https://records.yourname.in` shows a valid certificate; `http://` redirects to `https://`.
- [ ] The three UptimeRobot monitors are green and you received the test alert emails (B12).
- [ ] One backup ran and one **restore drill** passed (C3); the restic password is in two safe places.
- [ ] The privacy notice and `docs/BREACH_RUNBOOK.md` are reviewed, and `GRIEVANCE_NAME` / `GRIEVANCE_EMAIL` set.

Then invite people from **Profile → Admin** (see the README, "Inviting people").

---

## Part C: Running it

### C1. Updating the app

A new version reaches a VM only by moving its tag in OCIR; the agent (B9) does the rest. The Deliver workflow
moves the tags (docs/CICD.md):

1. **Merge to main.** CI passes, Deliver builds `sha-<commit>` and moves **`staging`** to it, then waits for
   `https://staging-records.yourname.in/api/version` to report the commit and smoke-tests it. Try the app there with
   synthetic data.
2. **Push a tag `vX.Y.Z`** on that commit and approve the *production* deployment in GitHub. Deliver moves
   **`prod`**; the prod agent backs up, then deploys; Deliver waits for `https://records.yourname.in/api/version`
   and smoke-tests it. If anything fails it moves the tag back.

Without GitHub Actions, publish and move the tags by hand as in B9.

If the new image is not healthy within 3 minutes, the agent goes back to the previous one by itself and skips that
image. To roll back a release that is healthy but wrong: Actions → Deliver → *Run workflow* with the previous
version (docs/CICD.md), or by hand, move the tag back to the previous image:

```bash
docker buildx imagetools create -t $REPO:prod $REPO:sha-<previous commit>   # or the previous digest
```

(The previous digest is in `/var/lib/medical-records/previous-digest` and `deploy.log` on the VM.)

Database migrations run by themselves when the app starts, and only go forward. Before changing the database, the
app saves a copy to `/srv/medical-records/data/backups/pre-<revision>-<time>.db`. Rolling back to an image older than
a database change needs a restore (C4), not just the tag.

### C2. Checking the backups

```bash
cat /var/lib/medical-records-backup/last-success                      # time of the last good backup (UTC)
systemctl status medical-records-backup.service --no-pager            # did the last run fail?
sudo bash -c 'set -a; source /etc/medical-records/backup.env; restic -o s3.bucket-lookup=path snapshots'
sudo bash -c 'set -a; source /etc/medical-records/backup.env; restic -o s3.bucket-lookup=path stats --mode raw-data'
```

The last command shows how much of the Object Storage allowance (20 GB at the time of writing) the backups use.

### C3. Restore drill (every month, about 10 minutes)

A backup is only useful if it restores. Do this monthly, and always after changing anything about backups.

0. Pause the agent, so nothing is deployed during the drill: `sudo touch /etc/medical-records/deploy-paused`.
1. Restore the latest snapshot into a scratch folder. The live data is not touched:

   ```bash
   sudo /opt/medical-records/repo/scripts/restore.sh       # or: restore.sh <snapshot id> (see "restic snapshots")
   ```

   The report must say `OK database integrity check` and `OK every document has its file`. It also shows the
   schema revision and the number of users, records and documents; they should match what you expect.
2. Optionally look at the restored data with the running image on another port, reachable only from the VM (use
   the folder printed in step 1):

   ```bash
   R=/var/lib/medical-records-backup/restore-XXXXXX
   sudo chown -R 10001:10001 $R
   sudo bash -c 'source /opt/medical-records/compose/.env; docker run --rm --read-only --tmpfs /tmp --user 10001:10001 \
     --env-file /etc/medical-records/app.env -e CLAMAV_SOCKET= -e BACKUP_STATUS_DIR= -e SYSTEM_DISK_PATH= \
     -e DATABASE_URL=sqlite:////data/database/medical_records.db -e FILES_DIR=/data/files \
     -v '$R':/data -p 127.0.0.1:8001:8000 "$APP_IMAGE"'
   ```

   From your computer: `ssh -L 8001:127.0.0.1:8001 -i ~/.ssh/oracle-medical-records ubuntu@<public IP>`, then open
   <http://localhost:8001>. Sign-in needs an OAuth redirect for that address, so the report from step 1 is
   usually enough. Stop it with Ctrl+C.
3. Delete the restored folder. **It is not encrypted.**

   ```bash
   sudo rm -rf /var/lib/medical-records-backup/restore-*
   ```

4. Make sure the stack runs and resume the agent:

   ```bash
   sudo medical-records-compose up -d --wait          # starts the stack if anything stopped; else changes nothing
   sudo medical-records-compose ps
   sudo rm /etc/medical-records/deploy-paused
   ```

5. Note the drill below.

| Date | Snapshot | Result | Notes |
| --- | --- | --- | --- |
| | | | |

### C4. Disaster recovery (the VM or its disk is gone)

1. Recreate what is gone with Terraform (`terraform apply` in `infra/`: the VM, and the data volume if it is lost too).
   Point DNS at the IP if it changed (A10; the reserved IPs normally survive).
2. **Before** host-setup, put the **same** restic password in place, so it is not replaced by a new one:
   `sudo install -d -m 700 /etc/medical-records && sudo install -m 600 /dev/stdin /etc/medical-records/restic-password`
   (paste it, then Ctrl+D).
3. Run `host-setup.sh --env prod` (Part B), with the same `backup-writer` key; `--format-data-volume` only for a
   new, empty volume. It finds the existing repository and does not run `restic init`. The agent then deploys the
   `prod` image on an empty database.
4. Stop the nightly timer until the restore is done (`sudo systemctl stop medical-records-backup.timer`), and pick
   the **snapshot from before the disaster** by its ID and time:

   ```bash
   sudo bash -c 'set -a; source /etc/medical-records/backup.env; restic -o s3.bucket-lookup=path snapshots'
   sudo /opt/medical-records/repo/scripts/restore.sh --apply <snapshot id>
   sudo systemctl start medical-records-backup.timer
   ```

   `restore.sh --apply` restores it, checks it, holds the agent's lock, stops the app, puts the data in place (owned
   by 10001) and starts the app. A backup from an older version is upgraded when the app starts. Never restore
   "latest" blindly here: a backup taken on the new, empty VM would be the latest.
5. Check the UptimeRobot monitors are green.

To roll back on a working server (for example after a bad change), `restore.sh --apply <snapshot id>` does the
same; the data it replaces is moved to `/srv/medical-records/data.before-restore-<time>`, never deleted. If the bad
change came with a new image, move the `prod` tag back first (C1), or the agent keeps the newer image.

Restoring brings back **all accounts' data** as it was at that time (it is not a way to restore one person), and
everyone is signed out.

### C5. Oracle Always Free: things to know

- **Idle reclaim:** Oracle may stop Always Free instances it considers idle (very low CPU, network and memory use
  over 7 days; check the current rules). The `app` monitor tells you if it happens; start the instance again from
  the console. Upgrading to Pay As You Go (A1) avoids this for free-tier resources, according to Oracle's
  documentation at the time of writing.
- **Stay within the limits:** one A1 VM of 2 OCPUs / 12 GB (the whole allowance: 1,500 OCPU-hours and 9,000
  GB-hours a month; on a free account an instance over it gets shut down), boot + block volumes up to 200 GB, Object
  Storage up to 20 GB. The budget alert (A2) catches mistakes.
- **Storage growth:** each account has a 100 MB storage limit by default (`DEFAULT_QUOTA_MB`). Thousands of
  accounts could outgrow the free 100 GB volume and 20 GB of backups; watch **Admin → Server** and
  `restic stats`, and plan paid storage before that.

### C6. Optional: virus scan of uploads (ClamAV)

Off by default. When it is on, every uploaded file is scanned before it is saved; if the scanner does not answer,
the upload is refused (never saved unscanned). clamd needs about 1 GB of RAM.

On prod, `host-setup.sh` does this; staging has no scanner. By hand:

```bash
sudo apt-get install -y clamav-daemon
sudo systemctl enable --now clamav-freshclam clamav-daemon     # signatures update by themselves
echo 'CLAMAV_SOCKET=/run/clamav/clamd.ctl' | sudo tee -a /etc/medical-records/app.env
sudo medical-records-compose up -d --force-recreate --wait app   # the app reads app.env when it is created
```

clamd runs on the VM, not in the stack; the app container sees the VM's `/run/clamav` folder (read-only), where
systemd keeps clamd's socket open to every user.

To check it: download the harmless EICAR test file from eicar.org and run `clamdscan eicar.com` (it must say
`FOUND`); then upload an ordinary PDF in the app. It only saves if clamd answered. (Uploading the EICAR file to the
app is not a useful test: the app refuses it earlier, because it is not a real PDF or image.)

### C7. Troubleshooting

| Problem | Look at |
| --- | --- |
| Browser cannot connect at all | DNS (A10), security list ports 80/443 (A4), VM firewall (B2), `sudo medical-records-compose ps` |
| Certificate error | `journalctl -t medical-records-caddy -n 50`: Let's Encrypt needs the DNS record and port 80 open |
| "502 Bad Gateway" | the app is down: `sudo medical-records-compose ps`, `journalctl -t medical-records-app -n 50` |
| A new version does not appear | `journalctl -u medical-records-deploy -n 30` (B9): paused? a known-bad image? the backup before the switch failed? |
| `unauthorized` from `bom.ocir.io` in the agent's log | the `vm-image-puller` auth token (A12): `sudo docker login bom.ocir.io -u <namespace>/vm-image-puller` |
| App will not start ("Invalid configuration") | the listed setting in `/etc/medical-records/app.env` (B7), then `sudo medical-records-compose up -d --force-recreate --wait app` |
| `permission denied` on `/data` in the app's log | the data folder must belong to 10001 (B5) |
| Google says `redirect_uri_mismatch` | the redirect URI in A11 must equal `GOOGLE_REDIRECT_URI` exactly |
| Invited person sees "has no invite" / "different Google account" | they must use the invite link, with the Google account for the invited email |
| `/api/health/backup` red | `journalctl -u medical-records-backup.service -n 50`; then run the backup by hand (B11) |
| Disk alert | **Admin → Server**; `sudo du -sh /srv/medical-records/data/* /var/log/journal`; old images: `sudo docker system df` |

Test the backup scripts without any cloud account: `PYTHON=backend/.venv/bin/python scripts/test-backup.sh` (needs
restic). CI runs this on every push.
