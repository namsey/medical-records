# Monitoring: Grafana Cloud with Grafana Alloy, installed by Ansible

This adds **graphs, logs and alerts** to what UptimeRobot already does (DEPLOY.md B12), without a monitoring
server. Each VM runs one small agent, **Grafana Alloy**, that sends the VM's metrics and the app's logs to
**Grafana Cloud** (free tier). **Ansible**, run from your laptop, installs and configures Alloy on both VMs.

New to these tools? Read section 1 once, then follow steps 2 to 7 in order. Each step says what to check before
going on.

**The plan** is a series of roadmap items, `mon-1` to `mon-8` (section 14, mirrored in ROADMAP.md). **Claude
Code** implements them one item per branch and pull request, following CLAUDE.md; section 15 says what it does,
what stays with you, and the prompt to start each item.

## 1. How the pieces fit

```
                         ┌───────────────────────── GitHub ─────────────────────────┐
  your laptop            │  CI (ci.yml): tests, Terraform validate, image + Trivy   │
  ───────────            │  Ops lint (ops-lint.yml): ansible-lint, alloy validate   │
  git push ─────────────►│  Deliver (deliver.yml): build → OCIR → move tag          │
                         └──────────────────────────────┬───────────────────────────┘
                                                        │ moves the "staging"/"prod" tag in OCIR
                                                        ▼ (never connects to a VM)
  ansible-playbook ── SSH ──►  ┌──────── staging VM / prod VM (Ubuntu, Ampere) ────────┐
  (monitoring.yml)             │  deploy agent (timer): pulls the tag's image, deploys  │
                               │  Docker: app + Caddy  ── logs ──► systemd journal      │
                               │  Alloy: reads VM metrics + journal ─────────────────────┼──► Grafana Cloud
                               └────────────────────────────────────────────────────────┘    metrics, logs,
                                                                                              dashboards, alerts
  UptimeRobot ── checks /api/health, /disk, /backup every 5 min from outside (unchanged)
```

| Tool | Job | Runs where | Changed by |
| --- | --- | --- | --- |
| Terraform (`infra/`) | the VMs, network, volumes, OCIR, bucket | your laptop | `terraform apply` |
| `scripts/host-setup.sh` | Docker, app settings and secrets, deploy agent, backups, ClamAV | on each VM, once | you, over SSH |
| **Ansible (`ansible/`)** | **the monitoring agent (Alloy)**; later, more of the host setup | **your laptop, over SSH** | `ansible-playbook` |
| CI / Deliver (`.github/`) | tests, image, deploys by moving an OCIR tag | GitHub | a merge or a `vX.Y.Z` tag |
| **Alloy** | sends metrics and logs to Grafana Cloud | on each VM, as a systemd service | Ansible |
| **Grafana Cloud** | stores 14 days of metrics and logs; dashboards; alerts | Grafana Labs | the web UI |
| UptimeRobot | "is it up?" from outside OCI, even when the VM is gone | UptimeRobot | the web UI |

Three decisions behind this design:

- **Deliver still never connects to a VM.** Ansible needs SSH, and SSH is open only to your own IP
  (`ssh_allowed_cidrs` in `infra/`). Running Ansible from GitHub Actions would mean opening port 22 to GitHub and
  storing an SSH key in a public repository's settings, which is exactly what docs/CICD.md avoids. So Ansible runs
  from your laptop, and GitHub only **checks** the Ansible and Alloy files (ops-lint.yml) without any credentials.
- **Ansible starts small.** `host-setup.sh` already prepares the VMs well and is safe to re-run. Ansible takes
  over only the new part, the monitoring agent. Moving more of host-setup.sh into Ansible roles later is
  optional (section 11).
- **Alloy only pushes.** It opens no port to the internet, so the security list and iptables stay as they are.
  Its own web page listens on `127.0.0.1:12345` only.

### What Alloy collects

| What | Where it comes from | Examples |
| --- | --- | --- |
| VM metrics | built-in node_exporter | CPU, memory, disk space on `/` and `/srv/medical-records`, disk I/O, network |
| Unit states | systemd | `medical-records-backup.service` failed, `medical-records-deploy.service` failed, `docker` down |
| Logs | the systemd journal, filtered | the app and Caddy containers, deploy agent, backups, Docker, ClamAV, SSH, kernel OOM kills |
| App metrics (later) | the app's `/metrics` on a private port | requests per route, errors, response times (section 8) |

Everything else in the journal stays on the VM. Before a log line leaves, anything that looks like an email
address or an Indian mobile number is replaced with `<email>` or `<phone>`. The app already never logs record
contents, search terms or file names (`deploy/journald/medical-records.conf`); the masking is a second safety net.

## 2. Install Ansible on your laptop

Ansible runs on Linux or macOS. On Windows, use WSL (Ubuntu), and keep the SSH key inside WSL (`~/.ssh`).

```bash
python3 -m pip install --user pipx && python3 -m pipx ensurepath   # once; open a new terminal afterwards
pipx install ansible-core
ansible --version                                                  # 2.16 or newer
```

Check you can reach both VMs with the key from DEPLOY.md A5:

```bash
ssh -i ~/.ssh/oracle-medical-records ubuntu@<staging IP> true && echo staging ok
ssh -i ~/.ssh/oracle-medical-records ubuntu@<prod IP> true && echo prod ok
```

If that fails, Ansible will too: check your current public IP is still in `ssh_allowed_cidrs`.

## 3. Create the Grafana Cloud stack

1. Sign up at <https://grafana.com> (free, no card). Name the stack, e.g. `namsey-medical`, and pick the region
   closest to India that is offered. The region is where your metrics and logs are stored.
2. **My Account → your stack → Prometheus → Details**: note the *Remote Write Endpoint* (ends in
   `/api/prom/push`) and the *Username / Instance ID* (a number).
3. **Loki → Details**: note the *URL* and the *User* (another number). The push URL is that URL followed by
   `/loki/api/v1/push`.
4. **Access Policies** (Administration → Users and access → Cloud access policies) → *Create access policy*:
   name `alloy-vms`, realm your stack, scopes **metrics:write** and **logs:write** only. Then *Add token*, name
   `alloy-vms`, no expiry or one year. Copy the token (starts with `glc_`): it is shown once.

A write-only token is the right kind: if it ever leaked, someone could send junk data, but could not read your
logs or dashboards.

Put the endpoints (not secret) in `ansible/inventory/group_vars/all/main.yml`, and the VM IPs
(`cd infra && terraform output`) in `ansible/inventory/hosts.yml`.

## 4. Put the token in the Ansible vault

The repository is public, so the token goes into a file encrypted with **ansible-vault**:

```bash
cd ansible/inventory/group_vars/all
cp vault.yml.example vault.yml
nano vault.yml                     # paste the glc_ token
ansible-vault encrypt vault.yml    # choose a long password; save it in your password manager
head -1 vault.yml                  # must start with $ANSIBLE_VAULT;1.1;AES256 before you commit it
```

Commit only the encrypted `vault.yml`. To change it later: `ansible-vault edit vault.yml`. The vault password
never goes into the repo or GitHub.

## 5. Preview, then install on staging

From the `ansible/` folder:

```bash
ansible all -m ping --ask-vault-pass                                   # "pong" from both VMs
ansible-playbook monitoring.yml --limit staging --check --diff --ask-vault-pass
```

`--check --diff` changes nothing; it shows what would change. On a VM without Alloy it stops previewing after
the install step (it says why). Then run it for real:

```bash
ansible-playbook monitoring.yml --limit staging --ask-vault-pass
```

What the playbook does (`roles/alloy/tasks/main.yml`): checks your settings are filled in, adds Grafana's apt
repository, installs the pinned Alloy version, lets Alloy read the journal, writes `/etc/default/alloy` (the
token, mode 640) and `/etc/alloy/config.alloy` (checked with `alloy validate` before it replaces the old one),
starts Alloy, and waits until it reports ready. Run it a second time: it should report `changed=0`. That is
Ansible's idempotency, and it is how you will spot drift later.

**Check on the VM:**

```bash
ssh -i ~/.ssh/oracle-medical-records ubuntu@<staging IP>
systemctl status alloy --no-pager          # active (running)
journalctl -u alloy -n 30 --no-pager       # no repeated "error" lines (a 401 means a wrong user or token)
```

To see Alloy's own page (a graph of the components and their health), from your laptop:
`ssh -i ~/.ssh/oracle-medical-records -L 12345:127.0.0.1:12345 ubuntu@<staging IP>`, then open
<http://localhost:12345>.

**Check in Grafana Cloud** (Explore, a minute after the start):

- Prometheus data source: `up{env="staging"}` shows 1.
- Loki data source: `{env="staging", syslog_identifier="medical-records-app"}` shows the app's lines.

## 6. Then prod

When staging has looked right for a day:

```bash
ansible-playbook monitoring.yml --limit prod --check --diff --ask-vault-pass
ansible-playbook monitoring.yml --limit prod --ask-vault-pass
```

Same checks with `env="prod"`. Alloy uses little memory (typically a couple of hundred MB); confirm with
`systemctl status alloy` on prod, where the app container has `APP_MEMORY_LIMIT`.

## 7. Dashboards and alerts

**Dashboards.** Connections → Add new connection → **Linux Server** → *Install dashboards and alerts*. Skip its
"install Alloy" instructions: Ansible did that, with the same job and instance names, so the dashboards work as
they are. Use the `instance` drop-down to switch between the staging and prod VMs.

**Alerts, as code (mon-4).** `infra/grafana/` (Terraform, its own state, never shared with `infra/`) makes a
"HealthKitab" folder, an email contact point, the notification policy, one rule group with the rows below on the
prod data (`env="prod"`), and the "HealthKitab" dashboard (VM, failed units, log counts; request panels come with
mon-3). Change alerts there, not in the UI: an apply puts back what the code says. Start with these; add more only
when one would have told you something.

1. **Service account** (once): Administration → Users and access → Service accounts → Add, role **Editor**, then
   Add service account token. If the apply is refused on the notification policy, give the account **Admin**.
2. **Settings**, on your laptop:
   ```bash
   cd infra/grafana
   cp terraform.tfvars.example terraform.tfvars     # then set alert_email to the inbox you read
   export GRAFANA_URL=https://<stack>.grafana.net
   read -rs GRAFANA_AUTH && export GRAFANA_AUTH       # paste the token; it is not shown or saved
   ```
3. **Apply:** `terraform init`, `terraform plan` (expect 5 to add: folder, contact point, policy, rule group,
   dashboard), then `terraform apply`. The notification policy is the stack's **whole** routing tree: it replaces
   any policy made by hand.
4. **Duplicates:** if you installed the Linux Server integration's alert rules, pause them (Alerting → Alert rules →
   the integration's folder) so each problem emails you once.
5. **Test alert:** the rules watch prod only, so point them at staging for a few minutes instead of stopping
   anything on prod: `terraform apply -var alert_env=staging`, then on staging `sudo systemctl stop alloy`. Within
   about 12 minutes "VM silent" emails you. `sudo systemctl start alloy`, wait for the "Resolved" email, then
   `terraform apply` again to put the rules back on prod (prod is unwatched only during the test).

| Alert | Query | Fires when |
| --- | --- | --- |
| VM silent | `absent_over_time(up{job="integrations/node_exporter", env="prod"}[10m])` | no metrics for 10 min (VM down, or Alloy stopped) |
| Disk filling | `100 * (1 - node_filesystem_avail_bytes{env="prod", mountpoint=~"/\|/srv/medical-records"} / node_filesystem_size_bytes{env="prod", mountpoint=~"/\|/srv/medical-records"})` | above 80 |
| Memory | `100 * (1 - node_memory_MemAvailable_bytes{env="prod"} / node_memory_MemTotal_bytes{env="prod"})` | above 90 for 10 min |
| Backup failed | `node_systemd_unit_state{env="prod", name="medical-records-backup.service", state="failed"}` | equals 1 |
| Deploy agent failing | `node_systemd_unit_state{env="prod", name="medical-records-deploy.service", state="failed"}` | equals 1 for 10 min |
| App errors (logs) | `sum(count_over_time({env="prod", syslog_identifier="medical-records-app"} \|= "Unhandled" [15m]))` | above 0 |
| Virus scanner down (logs) | `sum(count_over_time({env="prod", syslog_identifier="medical-records-app"} \|= "Virus scanner unavailable" [15m]))` | above 0 |
| Sign-in attempts spike (logs) | `sum(count_over_time({env="prod", syslog_identifier="medical-records-app"} \|= "Sign-in rejected" [15m]))` | above 20 |

UptimeRobot (DEPLOY.md B12) is not set up on these VMs (owner's choice, 2026-10-30): "VM silent" is the only
alert when the whole VM, region or Alloy is gone, so keep it. No data counts as healthy for every rule; "VM silent"
uses `absent_over_time`, which returns 1 only when the metrics stop.

**Logs you will search most** (Explore → Loki):

```logql
{env="prod", syslog_identifier="medical-records-app"}                    # the app
{env="prod", syslog_identifier="medical-records-caddy"} |= "error"        # Caddy problems, certificates
{env="prod", unit="medical-records-deploy.service"}                       # what the deploy agent did
{env="prod", unit="medical-records-backup.service"}                       # last night's backup
{env="prod", syslog_identifier="kernel"} |= "Out of memory"               # OOM kills
```

## 8. Later: app metrics (requests, errors, response times)

Today Alloy sees the VM, not the app's requests. To add them, the app serves Prometheus metrics on a **separate
port, 8001**, inside its container:

- Caddy proxies only `app:8000` (Caddyfile), and compose does not publish 8001, so the internet cannot reach it.
  Only the VM can, over Docker's bridge network at `172.30.0.20:8001` (compose.yaml).
- Label requests by **route template** (`/api/records/{record_id}`), never by the real path, user, email or
  record ID. That keeps the number of series small and keeps identifiers out of Grafana Cloud.

A prompt you can give Claude Code for the app change:

> Add Prometheus metrics to the backend. Use prometheus-fastapi-instrumentator (pinned in requirements.txt) to
> instrument the app, grouping by route template and ignoring /api/health*. Do not mount /metrics on the main app.
> Instead, in the lifespan, start prometheus_client's HTTP server on 0.0.0.0:METRICS_PORT (setting, default 8001,
> 0 disables it). Add a test that the main app returns 404 for /metrics. Update README's settings table.

Then set `alloy_scrape_app: true` in `ansible/inventory/group_vars/all/main.yml` and run the playbook on staging,
then prod. Useful queries afterwards:

```promql
sum by (handler) (rate(http_requests_total{env="prod", status=~"5.."}[5m]))          # 5xx per route
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{env="prod"}[5m])))  # p95 latency
```

## 9. Later: mark deploys on the graphs

So that a spike can be lined up with a release, Deliver can add an **annotation** in Grafana after each deploy.
This talks to Grafana Cloud, not to a VM, so it keeps the "never connects to a VM" rule. Create a Grafana service
account (Administration → Service accounts) with the narrowest role that can write annotations (Editor if
there is no annotations-only role), store its token as an **environment secret** `GRAFANA_TOKEN` in
`staging` and `production`, and add after "Move the ... tag, wait for the VM, smoke test":

```yaml
      - name: Annotate the deploy in Grafana
        if: success()
        continue-on-error: true # a Grafana problem must never fail a deploy
        env:
          GRAFANA_URL: ${{ vars.GRAFANA_URL }}   # https://<stack>.grafana.net
          GRAFANA_TOKEN: ${{ secrets.GRAFANA_TOKEN }}
          TEXT: "Deployed ${{ github.sha }} to staging" # "production" in deploy-production
        run: |
          jq -n --arg text "$TEXT" '{text: $text, tags: ["deploy"]}' |
            curl -sSf -X POST -H "Authorization: Bearer $GRAFANA_TOKEN" -H 'Content-Type: application/json' \
              --data @- "$GRAFANA_URL/api/annotations" >/dev/null
```

## 10. Everyday use

| Task | How |
| --- | --- |
| Change what Alloy collects | edit `ansible/roles/alloy/templates/config.alloy.j2`, open a PR (Ops lint validates it), merge, run the playbook on staging, then prod |
| Upgrade Alloy | change `alloy_version` in `roles/alloy/defaults/main.yml`, same flow |
| See what differs from the repo | `ansible-playbook monitoring.yml --check --diff --ask-vault-pass` (`changed=0` means none) |
| Rotate the token | new token in Grafana Cloud → `ansible-vault edit inventory/group_vars/all/vault.yml` → run the playbook → delete the old token |
| A rebuilt VM | `terraform apply` → `host-setup.sh` (DEPLOY.md Part B) → new IP in `hosts.yml` → `ansible-playbook monitoring.yml --limit <vm>` |
| Pause sending | `sudo systemctl stop alloy` on the VM (start it again the same way) |
| Remove it | `sudo apt-get remove --purge alloy` on the VM, and delete the stack in Grafana Cloud |

### Free tier limits

Grafana Cloud's free tier allows about 10,000 active metric series and 50 GB of logs a month, kept 14 days.
Two VMs with this configuration use a small fraction of both. Data above the free limits is dropped, not
billed. Usage: Administration → Cost management (or *Usage insights*).

## 11. Optional: more of the host setup in Ansible

`host-setup.sh` works, so there is no need to rewrite it. If you want Ansible to own more over time, move one
step at a time into a role, run it with `--check --diff` against a VM that host-setup.sh already prepared, and
delete the step from the script only when the role reports `changed=0`. Good first candidates: the journald
limits (B8), unattended upgrades (B1) and the iptables rule (B2). Leave the interactive secrets (B7) and the data
volume formatting (B4) in the script until last.

## 12. Privacy and DEPLOY.md

Add to DEPLOY.md B12, next to the UptimeRobot note: *Grafana Cloud (Grafana Labs) receives the VMs' resource
metrics and the log lines of the app, Caddy, the deploy agent, the backups, Docker, ClamAV, SSH and kernel OOM
messages. The app never logs record contents, search terms or file names; Alloy masks email addresses and phone
numbers before sending. Data is kept 14 days in the region chosen for the stack.* If the privacy notice lists
service providers, add Grafana Labs there as well.

## 13. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Playbook: "Fill in alloy_env ..." | a placeholder is still in `group_vars/all/main.yml`, or `vault.yml` is missing or not decrypted (`--ask-vault-pass`) |
| Playbook: `UNREACHABLE` | your IP is not in `ssh_allowed_cidrs`, or the wrong IP in `hosts.yml` |
| `journalctl -u alloy`: 401 / 403 | wrong Prometheus or Loki *user number*, or the token lacks metrics:write / logs:write |
| Metrics arrive, logs do not | the Loki URL is missing `/loki/api/v1/push`; or `alloy` is not in `systemd-journal` (re-run the playbook) |
| No app lines in Loki | the app's journald tag changed in compose.yaml; update `alloy_log_identifiers_regex` |
| `alloy validate` failed in the playbook | the template has a mistake; the old config is still in place and Alloy keeps running it |
| Ops lint fails on a PR | read the job log: ansible-lint names the file and rule; `alloy validate` prints the line |

## 14. The plan: mon-1 to mon-8

Each item is one branch and one pull request (CLAUDE.md "How to implement a roadmap item"). ROADMAP.md holds the
checkboxes; this section holds the details. **Claude Code** writes, tests and opens the PR; **you** review and
merge it, and run every step that touches a server or a cloud account. Work top to bottom.

### mon-1 Monitoring agent as code (done)

`ansible/` (inventory, `monitoring.yml`, the `alloy` role), the Alloy config template, `ansible/tests/render.yml`,
`.github/workflows/ops-lint.yml` and this file. Checked: `alloy validate` on every rendered combination, a test of
the log filter and masking, ansible-lint (production profile). Not yet run on a VM.

### mon-2 Agent live on staging, then prod

- **You:** steps 2 to 6 of this file: Ansible on the laptop, the Grafana Cloud stack and write-only token, the
  encrypted `vault.yml`, the VM IPs in `hosts.yml`, then the playbook on staging and, a day later, prod.
- **Claude Code:** fills in the non-secret values you give it (`group_vars/all/main.yml`, `hosts.yml`) in a PR,
  and fixes the role if the playbook output you paste shows a bug. It never runs the playbook itself.
- **Done when:** `up{job="integrations/node_exporter", env="staging"}` and `env="prod"` are 1;
  `{env="prod", syslog_identifier="medical-records-app"}` shows lines; a second playbook run reports `changed=0`.

### mon-3 App metrics

- **Claude Code:** in `backend/`, instrument the app with `prometheus-fastapi-instrumentator` and serve the metrics
  with `prometheus_client`'s HTTP server on `METRICS_PORT` (new setting, default 8001, 0 disables), started in the
  lifespan. Never mount `/metrics` on the main app: Caddy proxies all of `app:8000` to the internet. Group by route
  template (`/api/records/{record_id}`), exclude `/api/health*`, no user, email, record ID or raw path in any label.
  Pin both packages in `requirements.txt` (pip-audit must pass). Tests: the metrics server answers with
  `http_requests_total` labelled by template; the **public** app's `/metrics` never returns Prometheus metrics
  (the frontend fallback may answer it, but without metric text). README settings table. Then
  `alloy_scrape_app: true` in `group_vars/all/main.yml`, and the panels/queries in section 8.
- **You:** merge, let Deliver take it to staging, run the playbook on staging; release to prod with a `vX.Y.Z` tag,
  then the playbook on prod.
- **Done when:** `up{job="medical-records-app", env="staging"}` is 1 and `https://<staging domain>/metrics` shows no
  metrics; the same on prod after the release.

### mon-4 Dashboards and alerts as code

- **Claude Code** (touches `infra/` and `.github/workflows/`: needs your approval of the plan first): a separate
  Terraform root `infra/grafana/`, so it never shares state with the OCI resources. Provider `grafana/grafana`
  pinned like `oracle/oci`; state local and git-ignored like `infra/`; credentials only from the environment
  (`GRAFANA_URL`, `GRAFANA_AUTH` = a service account token you create) and the alert email from a git-ignored
  `terraform.tfvars` with a `.example` file. Resources: a "HealthKitab" folder, an email contact point, a
  notification policy, rule groups for the table in section 7 (and the app's 5xx rate and p95 latency once mon-3
  is done), and an app dashboard from a JSON file. Extend CI's Terraform job (or Ops lint) with
  `terraform fmt -check` and `terraform validate` for `infra/grafana`, without credentials.
- **You:** create the service account (Administration → Service accounts, role Editor or narrower) and token,
  `terraform init && terraform plan && terraform apply` in `infra/grafana`, then test one alert: on staging,
  `sudo systemctl stop alloy` until the "VM silent" alert emails you, then start it again. If the Linux Server
  integration's own alert rules duplicate these, turn those off in Grafana so each problem emails you once.
- **Done when:** every alert in section 7 exists from code and the test alert arrived.

### mon-5 Deploy annotations

- **Claude Code** (touches `.github/workflows/`: needs your approval first): the step in section 9 in
  `deploy-staging`, `deploy-production` and `rollback` of `deliver.yml`, after the smoke test, with
  `continue-on-error: true`. Reads `GRAFANA_URL` (environment variable) and `GRAFANA_TOKEN` (environment secret)
  from the `staging` and `production` environments only. Updates docs/CICD.md "One-time setup".
- **You:** a Grafana service account token with the narrowest role that can write annotations; the variable and
  secret in both GitHub environments.
- **Done when:** the next staging deploy shows as a marker on the dashboards.

### mon-6 Alert runbook

- **Claude Code:** a section "When an alert fires" here: for each alert, what it means, what to look at first in
  Grafana (a ready LogQL/PromQL query), the commands **you** run on the VM, and links to the matching DEPLOY.md
  Part C step or BREACH_RUNBOOK.md (sign-in spikes, unexpected SSH logins). Each alert's description in
  `infra/grafana/` links to its runbook entry.
- **Done when:** every alert has an entry and a link.

### mon-7 Privacy and docs

- **Claude Code:** DEPLOY.md B12 gets the Grafana Cloud paragraph from section 12 and a checklist line; README's
  monitoring paragraph mentions Grafana Cloud and links here; if the in-app privacy notice lists service
  providers, add Grafana Labs in the same style (a UI text change: check 360px and 430px).
- **Done when:** a reader of DEPLOY.md and the privacy notice can tell what leaves the VMs and where it goes.

### mon-8 (optional) More of the host setup in Ansible

- **Claude Code:** one step of `scripts/host-setup.sh` per PR becomes a role, in the order of section 11, with
  ansible-lint passing; the script keeps the step until you confirm the role.
- **You:** `ansible-playbook <playbook> --check --diff` against both VMs; paste the output into the PR.
- **Done when:** the role shows `changed=0` on a VM that host-setup.sh prepared, and the step is removed from the
  script in the same PR.

## 15. Working with Claude Code

CLAUDE.md applies to all of this. In particular, Claude Code never SSHes into a server, never changes staging or
production, never deploys, merges or approves, and asks before touching `.github/workflows/` or `infra/`.

| Claude Code does | You do |
| --- | --- |
| Writes and changes the Ansible role, the Alloy config, app code, Terraform for Grafana, workflows (after your OK), docs | Create the Grafana Cloud stack, tokens and service accounts (web UI, sign-ups) |
| Runs every check locally: ansible-lint, playbook syntax, `alloy validate` on rendered configs, `terraform validate`, backend and frontend tests | Hold the secrets: the vault password, Grafana tokens, GitHub secrets |
| Explains output you paste (playbook runs, `journalctl -u alloy`, Grafana errors) and fixes the cause in a PR | Run `ansible-playbook` and `terraform apply`, and anything else on the VMs |
| Writes PromQL/LogQL queries, alert rules and dashboards as code | Review and merge PRs; approve production deploys |
| Opens PRs with the template filled in and fixes CI failures on them | Check Grafana: data arrives, an alert test email arrives |

### Guardrails for every mon-* item

- Never run `ansible-playbook`, `ssh`, `scp` or `terraform apply` against anything; give me the commands.
- Never read, print or commit a secret: Grafana tokens, the vault password, `app.env`, `vault.yml` unencrypted
  (a committed `vault.yml` starts with `$ANSIBLE_VAULT;1.1;AES256`).
- Deliver never connects to a VM; nothing needs SSH from GitHub.
- No user, email, account ID, record ID, file name or raw URL path in a metric label or a new log line. Keep the
  masking stages in the Alloy config.
- Pin everything the way the repo already does: package versions, Terraform providers, Alloy, actions by SHA.
- Stay well inside the free tier: once-a-minute scrapes, few labels, and a rough series count in the PR
  description for any new metric (well under 10,000 in total for both VMs).
- Staging first, prod after the owner has checked staging.

### Prompts

**Status** (start of a session, changes nothing):

```text
Read CLAUDE.md, docs/MONITORING.md and the Monitoring section of ROADMAP.md. Tell me which mon-* items are done,
which one is next, what it needs from me before you can start, and anything in the repo that has drifted from the
plan. Don't change anything.
```

**Implement an item** (replace mon-N):

```text
Implement roadmap item mon-N (monitoring).

Context: read CLAUDE.md, then docs/MONITORING.md in full: section 14 has mon-N's scope and "done when", section 15
the guardrails. Then read the files the item touches. The design is settled: Grafana Alloy on each VM pushes
metrics and logs to Grafana Cloud; Ansible (ansible/), run only by me from my laptop, installs it; Deliver never
connects to a VM; UptimeRobot stays as the outside check. Don't redesign it. If something in the plan looks wrong
or out of date, tell me before changing course.

1. Follow CLAUDE.md "How to implement a roadmap item". If mon-N's "Depends on" items aren't ticked in ROADMAP.md,
   stop and tell me. Show a short plan first (files, new settings, tests, and any change to .github/workflows/ or
   infra/, which need my approval) and wait for my OK.
2. Branch chore/mon-N-<short-name> from an up-to-date main.
3. Implement only mon-N, in the repo's style: pinned versions and action SHAs, comments that explain why.
4. Verify locally everything that applies, and show me the results:
   - backend: ruff check . and python -m pytest; frontend: npm run lint, npm run build, npm test
   - cd ansible && ansible-lint --offline --profile production && ansible-playbook monitoring.yml --syntax-check
   - render with ansible/tests/render.yml for staging and prod, then alloy validate on each file (the pinned
     Alloy binary and sha256 from .github/workflows/ops-lint.yml)
   - terraform fmt -check and terraform validate for any Terraform you touched (no credentials needed)
5. Update docs/MONITORING.md wherever the item changes how things work. Tick mon-N in ROADMAP.md with one Notes
   line. Commit "feat(mon-N): <title>" (or docs/fix).
6. Push and open the PR with gh pr create, filling in the template; list every change to .github/workflows/ and
   infra/.
7. End with: what changed; the exact commands and console steps I must do myself, in order (ansible-playbook,
   terraform apply, Grafana Cloud, GitHub settings); how to confirm each one worked in Grafana; the PR link. Stop.

Never: SSH or run ansible-playbook or terraform apply against anything; read, print or commit secrets (Grafana
tokens, the vault password, app.env) or an unencrypted vault; put user IDs, emails, record IDs or raw paths in
metric labels or log lines; weaken CI, lint or tests.
```

**After a failed run on a VM** (paste the output below the prompt):

```text
I ran the command below for mon-N and it failed. Read docs/MONITORING.md (sections 5, 13 and 14) and the files
involved, explain the cause in plain words, and fix it on a branch with a PR if the repo is wrong. If the fix is on
my side (a setting, a token, a firewall rule), tell me exactly what to change. Don't run anything on the VMs.
<paste the command and its output, with any token removed>
```
