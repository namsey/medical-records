# Medical Records

A private, invite-only web app where each person keeps their own medical records: doctor visits, prescriptions,
lab reports, diagnoses, scans and documents. It is built mobile-first for phones, runs on one small server (made
for Oracle Cloud's free tier in India, see [DEPLOY.md](DEPLOY.md)), and keeps every account's data separate.

**Workflow:** Add → Upload → Organise → Search → View → Download

## Features

**For everyone**

- Sign in with **Google only**. No passwords. There is no open registration: the admin invites each person.
- Records: Doctor Visit, Prescription (several medicines), Lab Report (optional individual results), Diagnosis,
  Medical Document, Scan, Other. Tags, and your own doctor and laboratory lists.
- Attach PDF, JPG, PNG and HEIC (iPhone) files, up to 20 MB each, within your account's storage limit (100 MB by
  default). PDFs and images open **inside the app**, also on Android where the browser cannot show PDFs by itself.
- Case-insensitive search across titles, doctors, hospitals, labs, diagnoses, medicines, test names, notes, tags
  and file names, with filters for record type, year, date range and tags. List and timeline views.
- **Your data is yours:** download everything (records and original files) as one ZIP, delete your account, and
  sign out of all devices from Profile. A privacy notice explains what is kept, where and why.
- No AI, OCR or automatic medical interpretation. Nothing in the app reads or interprets results.

**For the admin**

- **Profile → Admin**: create single-use invite links (bound to one email, valid 7 days) and revoke them; see each
  account's storage and change its limit; disable, enable or delete accounts; see the account activity log and the
  server's disk and backup status.
- The admin can **never** see anyone else's records or files, in the app or through its API.

**On the server**

- Nightly encrypted backups to Oracle Object Storage in Mumbai, a weekly copy to a disk at home, and a restore
  script with a monthly drill. Health checks for an uptime monitor (app, disk space, backups).

| Layer    | Technology |
|----------|------------|
| Frontend | React, TypeScript (strict), Vite, Tailwind CSS, React Router, TanStack Query, Lucide icons, pdf.js |
| Backend  | Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Database | SQLite (one file, WAL mode) |
| Files    | Local disk, one folder per account, served only through authenticated API endpoints |
| Server   | One VM: Caddy (HTTPS) in front of the app (systemd); restic backups; see [DEPLOY.md](DEPLOY.md) |

In production one process serves everything: FastAPI serves the API under `/api` and the built React app.

## Deploying for real users

Follow **[DEPLOY.md](DEPLOY.md)**: a step-by-step guide to Oracle Cloud's Always Free tier in Mumbai (account,
network, VM, data disk, backup bucket, DNS, Google sign-in, HTTPS, backups, monitoring, updates and recovery).

Before inviting anyone, complete its security checklist (B14), including a restore drill, and have the privacy
notice and the breach runbook reviewed (see [Privacy](#privacy-and-your-data)).

## Running it on your computer

### Requirements

- **Python 3.11 or newer** (tested on 3.12 and 3.13)
- **Node.js 22 LTS** (or 20.19+) with npm, to build the frontend

### Project layout

```text
backend/            FastAPI app (app/), Alembic migrations (alembic/), tests (tests/)
frontend/           React app (src/), built into frontend/dist; end-to-end tests (e2e/)
scripts/            Backup, restore and home-copy scripts, and their tests
deploy/             systemd units and journald settings for the server
docs/               BREACH_RUNBOOK.md
data/               Created on first run: medical_records.db, files/<account id>/, backups/  (never commit this)
.env                Your configuration (never commit this)  ->  copy from .env.example
```

### Google sign-in (one time)

The app signs people in with Google, so it needs an OAuth client. It is free and uses only the basic `openid email
profile` scopes.

1. Open <https://console.cloud.google.com/> and create a project.
2. **APIs & Services → OAuth consent screen** (*Google Auth Platform* in newer consoles): user type **External**,
   app name, your email. For local testing you can stay in *Testing* mode and add your Gmail under *Test users*;
   for real users set the publishing status to **In production** (DEPLOY.md, A11).
3. **Credentials → Create credentials → OAuth client ID**, type **Web application**, with these redirect URIs
   (they must match `GOOGLE_REDIRECT_URI` exactly):
   - `http://localhost:8000/api/auth/callback` for running on your computer
   - `http://localhost:5173/api/auth/callback` only if you use the Vite dev server (see Development)
   - `https://your-domain/api/auth/callback` on a server
4. Copy the **Client ID** and **Client secret** into `.env`.

Plain `http://` only works for `localhost`; the app refuses to start with an `http://` redirect URI for any other
host, so session cookies are always `Secure` on a server.

### First-time setup

```bash
cd medical-records
cp .env.example .env           # Windows: Copy-Item .env.example .env
# Fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ADMIN_EMAIL (your Gmail: the admin) and SESSION_SECRET:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"      # a value for SESSION_SECRET

python3 -m venv backend/.venv
source backend/.venv/bin/activate     # Windows: backend\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

(cd frontend && npm install && npm run build)
```

### Run

```bash
source backend/.venv/bin/activate     # Windows: backend\.venv\Scripts\Activate.ps1
cd backend && python -m app
```

Open <http://localhost:8000>, choose **Sign in with Google** with the `ADMIN_EMAIL` account, and accept the privacy
notice. The database and folders are created and migrated automatically on start-up. Use
`python -m app --help` for `--host` / `--port`.

Use `python -m app` rather than calling `uvicorn` directly: it switches off the per-request access log, because
request URLs can contain search terms.

To try it on an Android phone without a server: enable USB debugging, run `adb reverse tcp:8000 tcp:8000`, then
open `http://localhost:8000` in Chrome on the phone.

### Settings

All settings are environment variables (or lines in `.env`); see `.env.example`.

| Setting | Default | What it is |
| --- | --- | --- |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | – | Google sign-in (required) |
| `ADMIN_EMAIL` | – | The admin's Google email (required). The old name `ALLOWED_EMAIL` still works. |
| `SESSION_SECRET` | – | At least 32 random characters (required) |
| `DATABASE_URL` | `sqlite:///data/medical_records.db` | The SQLite file |
| `FILES_DIR` | `data/files` | Uploaded files, one folder per account |
| `MAX_UPLOAD_SIZE_MB` | `20` | Largest single file |
| `DEFAULT_QUOTA_MB` | `100` | Storage per account, unless the admin sets another |
| `GRIEVANCE_NAME`, `GRIEVANCE_EMAIL` | the admin's email | Privacy contact shown in the app |
| `CLAMAV_SOCKET` | off | clamd socket: scan every upload for viruses (DEPLOY.md, C6) |
| `BACKUP_STATUS_DIR` | off | Where the backup writes its status, for `/api/health/backup` (DEPLOY.md, B12) |
| `DISK_ALERT_PERCENT`, `BACKUP_MAX_AGE_HOURS` | `80`, `26` | Thresholds of the disk and backup health checks |
| `SESSION_MAX_AGE_DAYS` | `14` | How long a sign-in lasts |
| `SESSION_IDLE_HOURS` | `24` | A sign-in unused this long ends sooner (1–720) |

## Inviting people

`ADMIN_EMAIL` is the admin account. Nobody else can sign in without an invite:

1. Open **Profile → Admin**, type the person's email and choose **Create invite link**.
2. Copy the link (it is shown only once) and send it yourself, for example by message. It works once, for 7 days,
   and only with the Google account for that email.
3. They open the link, choose **Sign in with Google**, and accept the privacy notice. After that they sign in
   normally.

In the same place you can revoke a pending invite, change an account's storage limit, and disable, enable or delete
an account. Disabling signs the person out at once; deleting removes all of their records and files.

## Privacy and your data

- After signing in for the first time, everyone (the admin too) reads the privacy notice and agrees before using the
  app. The server refuses records until then. The notice is at `/privacy`, linked from the login page and Profile.
  When its meaning changes, change `PRIVACY_VERSION` in `backend/app/privacy.py` and everyone is asked again.
- **Profile → Download my data** gives a ZIP with `records.json` and every attached file under its original name,
  one folder per record. **Export records (JSON)** gives the records without the files.
- **Profile → Delete my account** permanently deletes the account, its records and files. Copies inside the
  encrypted server backups expire within 6 months. The admin account cannot delete itself.
- The grievance contact shown in the app comes from `GRIEVANCE_NAME` and `GRIEVANCE_EMAIL`.
- **Admin → Activity** lists sign-ins, invites and account changes for one year. It never holds record contents,
  file names or IP addresses.
- If something goes wrong, follow [docs/BREACH_RUNBOOK.md](docs/BREACH_RUNBOOK.md).

The privacy notice (`frontend/src/components/privacy/PrivacyNotice.tsx`) and the runbook are plain-language drafts,
not legal advice. Have them checked against India's DPDP Act and Rules before inviting anyone.

## Where data is stored

| What | Where | Setting |
| --- | --- | --- |
| Records, doctors, labs, tags, accounts, invites, activity log (SQLite, WAL mode) | `data/medical_records.db` | `DATABASE_URL` |
| Attached files | `data/files/<account id>/<random uuid>.<ext>` | `FILES_DIR` |
| Copy of the database taken before an upgrade changes it | `data/backups/pre-<revision>-<time>.db` | (next to the database) |
| Server backups (encrypted) | Oracle Object Storage, Mumbai, and a disk at home | DEPLOY.md, B11 and B13 |

Every record, doctor, laboratory, tag and file belongs to one account. Upgrades run by themselves when the app
starts. Upgrading a single-user install gives the existing data to the `ADMIN_EMAIL` account and moves files from
the old `data/uploads/<type>/` layout into `data/files/<account id>/`. If anything goes wrong, stop the app, put the
`pre-…` copy back as `data/medical_records.db` and move the files back.

Keep the database and the files folder on the same local disk. SQLite must not live on a network file system (NFS).

## Security notes

- Google OAuth (authorisation-code flow with PKCE and a state check). Only the admin and accounts created from an
  invite get a session. Invites are single-use, bound to one email and valid for 7 days; the database keeps only an
  HMAC of each invite link's secret.
- Server-side sessions: the browser holds only a random token in an HTTP-only, `SameSite=Lax`, `Secure` cookie. The
  database stores an HMAC of the token, never the token. Sessions expire after 14 days. A disabled account is
  signed out on its next request, and **Sign out of all devices** ends every session of an account.
- **Data separation:** every query is limited to the signed-in account. Someone else's record, file, doctor or lab
  answers exactly like one that does not exist (404): by ID, in search and lists, on the timeline, in downloads,
  backup and export. Tests sign in two accounts and check this both ways round, and a guard test stops routers from
  querying the database directly.
- Every `/api` route except sign-in, the invite check, the privacy contact and the health checks needs a session,
  and all but sign-in and the account's own consent, download and delete need the privacy notice accepted.
  State-changing requests also need a custom header and are refused from another site's `Origin` (no CORS). Guard
  tests check this for every route the app has.
- Rate limits (in memory): sign-in and invite checks 20 per 10 minutes per IP address, invite creation 30 per hour,
  uploads 100 files per hour per account, data downloads 5 per hour. Run the app behind a reverse proxy on the same
  machine (Caddy in DEPLOY.md) so it sees visitors' real IP addresses.
- Uploads: the type is checked from the file's contents (PDF, JPEG, PNG, HEIC only), names on disk are random, and
  size is limited per file and per account while the file streams in. Files are served only through authenticated
  endpoints with their real type, `nosniff`, `Content-Disposition` and a `sandbox` Content-Security-Policy, so even a
  disguised HTML or SVG file could never run. Optional virus scan with ClamAV.
- Security headers (CSP, `nosniff`, frame protection, no referrer, HSTS on HTTPS, `no-store` for API responses). The
  interactive API docs are disabled.
- All database access goes through SQLAlchemy with bound parameters. Error messages and logs never include record
  contents, search terms or file names.
- `.env`, `data/` and backups are excluded from Git. There are no credentials in the source code.

## Development

Run two terminals for hot reload. Set `GOOGLE_REDIRECT_URI=http://localhost:5173/api/auth/callback` in `.env`
and add that URI in the Google console.

```bash
cd backend && python -m app --reload          # terminal 1: API on :8000, reloads on code changes
cd frontend && npm run dev                     # terminal 2: React on :5173, proxies /api to :8000
```

Open <http://localhost:5173>.

### Tests and checks

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest   # API, accounts, separation, uploads, privacy
cd backend && ruff check .                                         # lint (Python)
cd frontend && npm test                                            # component and flow tests
cd frontend && npm run lint                                        # lint (TypeScript/React, oxlint)
cd frontend && npm run build                                       # strict TypeScript check + production build
cd frontend && npx playwright install chromium                     # once, for the end-to-end tests
cd frontend && E2E_PYTHON=../backend/.venv/bin/python npm run test:e2e   # end-to-end tests in a real browser
PYTHON=backend/.venv/bin/python scripts/test-backup.sh             # backup/restore scripts (needs restic)
```

The backend tests use a temporary database and files folder and never touch real data. Google is not contacted:
the sign-in tests replace the Google call. The end-to-end tests build the app, start the real server against a
throwaway database and drive Chromium at phone size (390px). The backup tests use local restic repositories, no
cloud account.

GitHub Actions (`.github/workflows/ci.yml`) runs all of the above on every pull request to `main`.

### Database migrations

Migrations run automatically on start-up (after saving a copy of the database). After changing
`backend/app/models.py`:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

Any change to existing data needs a migration that keeps every record, with defaults for existing rows, and a test
that upgrades a database from the previous version.

## Limitations

- Invite links are copied and sent by hand; the app does not send email.
- Rate limits and the upload lock live in memory, so the app runs as **one** process.
- Search is a case-insensitive substring match on the text you entered; it does not understand synonyms. Matching
  covers English letters; accented characters match case-sensitively.
- Chrome and most Android browsers cannot display HEIC photos, so those are offered as a download.
- No OCR, AI summaries, result graphs, reminders or offline mode (see ROADMAP.md, "Parked").

## API overview

All paths are under `/api`. They need a session cookie (and an accepted privacy notice) unless noted.

| Area | Endpoints |
|------|-----------|
| Sign-in (public) | `GET /auth/login[?invite=…]`, `GET /auth/callback` (Google), `GET /auth/invite/{token}`, `GET /auth/privacy` |
| Session | `GET /auth/me`, `POST /auth/logout`, `POST /auth/logout-all` |
| Own account (before consent too) | `POST /account/consent`, `GET /account/export` (ZIP), `POST /account/delete` |
| Records | `GET/POST /records`, `GET/PUT/DELETE /records/{id}` |
| Search / timeline | `GET /search?q=…`, `GET /records?record_type=…&date_from=…&date_to=…&tag=…`, `GET /timeline`, `GET /tags`, `GET /years` |
| Doctors / labs | `GET/POST /doctors`, `GET/PUT/DELETE /doctors/{id}`, same for `/labs` |
| Documents | `POST /records/{id}/documents`, `GET /documents/{id}`, `GET /documents/{id}/view`, `GET /documents/{id}/download`, `DELETE /documents/{id}` |
| Storage and export | `GET /storage`, `GET /export/json`, `GET /backup` (ZIP of your own data), `GET /config` |
| Admin (admin only; 404 for others) | `GET/POST /admin/invites`, `POST /admin/invites/{id}/revoke`, `GET /admin/users`, `PUT /admin/users/{id}/quota`, `POST /admin/users/{id}/disable` / `enable` / `delete`, `GET /admin/audit`, `GET /admin/system` |
| Health (public) | `GET /health`, `GET /health/disk`, `GET /health/backup` |
