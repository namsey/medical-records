# Monitoring: Grafana Cloud with Grafana Alloy, installed by Ansible

This adds **graphs, logs and alerts** to what UptimeRobot already does (DEPLOY.md B12), without a monitoring
server. Each VM runs one small agent, **Grafana Alloy**, that sends the VM's metrics and the app's logs to
**Grafana Cloud** (free tier). **Ansible**, run from your laptop, installs and configures Alloy on both VMs.

New to these tools? Read section 1 once, then follow steps 2 to 7 in order. Each step says what to check before
going on.

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

**Where alerts go.** Alerting → Contact points → add your email. Then Alerting → Alert rules → New, for each row
below, on the prod data (`env="prod"`). Start with these; add more only when one would have told you something.

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

UptimeRobot stays: it checks from outside OCI, so it still alerts when the whole VM, region or Alloy is gone.
The two overlap a little on purpose.

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
