# Personal Medical Records

A private, single-user web app for storing and organising your own medical records: doctor visits,
prescriptions, lab reports, diagnoses, scans and documents. It is built mobile-first for an Android phone
and keeps everything on your own machine (SQLite database plus a local files folder, no cloud storage).

**Workflow:** Add → Upload → Organise → Search → View → Download

- Sign-in with **Google only**: the admin, plus people the admin invites. No passwords, no open registration.
- Records: Doctor Visit, Prescription (multiple medicines), Lab Report (optional individual results),
  Diagnosis, Medical Document, Scan, Other. Tags, doctor and laboratory directories.
- Attach PDF / JPG / PNG / HEIC (iPhone photo) files, up to 20 MB each and 100 MB per account by default
  (`DEFAULT_QUOTA_MB`; the admin can change it per account). PDFs and images open **inside the app** (no download
  needed), including on Android where the browser cannot show PDFs by itself. HEIC photos are downloaded instead
  where the browser cannot show them. WEBP files stored before are still shown, but new ones are not accepted.
- Case-insensitive search across doctors, hospitals, labs, diagnoses, medicines, test names, titles, notes and
  tags, with filters for record type, date range and tags. Newest first.
- Chronological timeline, full backup (ZIP) and JSON export.
- No AI, OCR or automatic medical interpretation. Nothing in the app interprets results.

| Layer    | Technology |
|----------|------------|
| Frontend | React, TypeScript (strict), Vite, Tailwind CSS, React Router, TanStack Query, Lucide icons, pdf.js |
| Backend  | Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Database | SQLite (file) |
| Files    | Local filesystem, served only through authenticated API endpoints |

In production one process serves everything: FastAPI serves the API under `/api` and the built React app.

## Requirements

- **Python 3.11 or newer** (developed and tested on 3.13)
- **Node.js 22 LTS** (or 20.19+) with npm, only needed to build the frontend

## Project layout

```text
backend/            FastAPI app (app/), Alembic migrations (alembic/), tests (tests/)
frontend/           React app (src/), built into frontend/dist
data/               Created on first run: medical_records.db and files/<user id>/  (never commit this)
.env                Your configuration (never commit this)  ->  copy from .env.example
```

## Google OAuth setup (required, one time)

The app signs you in with your Google account, so it needs an OAuth client from Google. This takes about five
minutes and is free. You only use the basic `openid email profile` scopes.

1. Open <https://console.cloud.google.com/> and create a project (or pick an existing one).
2. Open **APIs & Services → OAuth consent screen** (shown as *Google Auth Platform* in newer consoles).
   Choose user type **External**, fill in the app name and your email, and under **Audience / Test users** add
   the Gmail account you will sign in with. Leaving the app in *Testing* mode is fine for personal use.
3. Open **Credentials → Create credentials → OAuth client ID**, application type **Web application**.
4. Under **Authorised redirect URIs** add the exact URI(s) you will use (they must match `GOOGLE_REDIRECT_URI`
   in `.env` character for character):
   - `http://localhost:8000/api/auth/callback` for running on your computer (default)
   - `http://localhost:5173/api/auth/callback` only if you use the Vite dev server (see Development)
   - `https://your-domain.example/api/auth/callback` if you host it behind HTTPS (see Using it on your phone)
5. Copy the **Client ID** and **Client secret** into `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).

Google only accepts `http://` redirect URIs for `localhost`; any other address must be `https://`.

## First-time setup

### Windows (PowerShell)

```powershell
cd medical-records

# 1. Configuration
Copy-Item .env.example .env
notepad .env        # fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ADMIN_EMAIL, SESSION_SECRET
# Generate a SESSION_SECRET value with:
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 2. Backend dependencies
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -r backend\requirements.txt

# 3. Build the frontend
cd frontend
npm install
npm run build
cd ..
```

### macOS / Linux

```bash
cd medical-records
cp .env.example .env
nano .env           # fill in the values; generate SESSION_SECRET with the command below
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt

(cd frontend && npm install && npm run build)
```

## Run

```powershell
# Windows (PowerShell), from the project root
backend\.venv\Scripts\Activate.ps1
cd backend
python -m app
```

```bash
# macOS / Linux
source backend/.venv/bin/activate
cd backend && python -m app
```

Open <http://localhost:8000> and choose **Sign in with Google**. The database and upload folders are created
and migrated automatically on start-up. Use `python -m app --help` for `--host` / `--port`.

Use `python -m app` rather than calling `uvicorn` directly: it switches off the per-request access log, because
request URLs can contain your search terms.

## Using it on your Android phone

Google sign-in only works on `localhost` or over HTTPS, so opening `http://192.168.x.x:8000` from the phone will
**not** work. Two practical options:

- **Quick test over USB:** enable USB debugging, plug the phone in, run `adb reverse tcp:8000 tcp:8000`, then open
  `http://localhost:8000` in Chrome on the phone. Keep the default `GOOGLE_REDIRECT_URI`.
- **Everyday use:** host the app somewhere with HTTPS (a small VPS behind Caddy or nginx, or your own computer
  behind a Cloudflare Tunnel / similar). Set `GOOGLE_REDIRECT_URI=https://your-domain.example/api/auth/callback`,
  add the same URI in the Google console, and run `python -m app --host 127.0.0.1` behind the reverse proxy.
  Then use Chrome's menu → *Add to Home screen* for an app-like shortcut.

The app is only as private as where you host it. Keep the machine patched, keep `.env` and `data/` readable only
by you, and keep backups somewhere safe.

## Development

Run two terminals for hot reload. Set `GOOGLE_REDIRECT_URI=http://localhost:5173/api/auth/callback` in `.env`
and add that URI in the Google console.

```bash
# terminal 1: API on :8000 (reloads on code changes)
cd backend && python -m app --reload

# terminal 2: React dev server on :5173 (proxies /api to :8000)
cd frontend && npm run dev
```

Open <http://localhost:5173>.

### Tests and checks

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest      # API, auth, uploads, search, backup tests
cd backend && ruff check .                                         # lint (Python)
cd frontend && npm test                                            # component / flow tests
cd frontend && npm run lint                                        # lint (TypeScript/React, oxlint)
cd frontend && npm run build                                       # strict TypeScript check + production build
cd frontend && npx playwright install chromium                     # once, for the end-to-end tests
cd frontend && E2E_PYTHON=../backend/.venv/bin/python npm run test:e2e   # end-to-end tests in a real browser
```

The backend tests use a temporary database and files folder and never touch your real data. Google is not
contacted: the sign-in tests replace the Google call.

The end-to-end tests (`frontend/e2e/`) build the app, start the real server against a throwaway database in your
temp folder, and drive Chromium at phone size (390px): adding a record of every type with an attachment, viewing,
editing, deleting, search, filters and the List/Timeline switch. `E2E_PYTHON` is the Python that has the backend's
requirements installed (on Windows: `..\backend\.venv\Scripts\python.exe`).

GitHub Actions (`.github/workflows/ci.yml`) runs all of the above on every pull request to `main`.

### Database migrations

Migrations run automatically on start-up. After changing `backend/app/models.py`:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Inviting people

`ADMIN_EMAIL` is the admin account (the old setting name `ALLOWED_EMAIL` still works). Nobody else can sign in
without an invite:

1. Open **Profile → Admin**, type the person's email and choose **Create invite link**.
2. Copy the link (it is shown only once) and send it yourself, for example by message. It works once, for 7 days,
   and only with the Google account for that email.
3. They open the link and choose **Sign in with Google**. After that they sign in normally.

In the same place you can revoke a pending invite, see each account's storage, and disable, enable or delete an
account. Deleting an account removes all of its records and files.

## Privacy and your data

- After signing in for the first time, everyone (the admin too) reads the privacy notice and agrees before using the
  app. The server refuses records until then. The notice is at `/privacy` and is linked from the login page. When
  its meaning changes, change `PRIVACY_VERSION` in `backend/app/privacy.py`, and everyone is asked again.
- **Profile → Download my data** gives a ZIP with `records.json` and every attached file under its original name.
- **Profile → Delete my account** permanently deletes the account, its records and files. Copies in the encrypted
  server backups expire within 6 months. The admin account cannot delete itself.
- The grievance contact shown in the app comes from `GRIEVANCE_NAME` and `GRIEVANCE_EMAIL` (default: the admin's
  email).
- **Admin → Activity** lists sign-ins, invites and account changes for one year. It never holds record contents,
  file names or IP addresses.
- If something goes wrong, follow [docs/BREACH_RUNBOOK.md](docs/BREACH_RUNBOOK.md).
- Monitoring: `/api/health`, `/api/health/disk` and `/api/health/backup` answer only ok or problem for an uptime
  monitor, and **Admin → Server** shows disk use and the last backup (DEPLOY.md section 8).

The notice and the runbook are plain-language drafts, not legal advice. Have them checked before inviting anyone.

## Backup and restore

On a server, nightly encrypted backups of all data go to Oracle Object Storage in Mumbai, with a weekly copy to
a disk at home and a monthly restore drill: see [DEPLOY.md](DEPLOY.md). The downloads below are your own copy of
your own data.

In the app open **Profile → Your data**:

- **Download my data (ZIP)** → `records.json` plus every attached file under its original name, one folder per
  record.
- **Export records (JSON)** → your structured data (doctors, laboratories, records, medicines, results, tags and
  attachment metadata) without the files.

For restoring a single-person install, `GET /api/backup` still gives `medical-records-backup-YYYY-MM-DD.zip`: a
copy of the SQLite database holding only the signed-in account's data (other accounts and login sessions removed,
then compacted) plus that account's files.

Backups contain your private medical data. Store them somewhere safe (they are not encrypted).

To restore: stop the app, unzip the backup, copy `database/medical_records.db` to `data/medical_records.db`
(delete any `medical_records.db-wal` / `-shm` files next to it) and copy the `files/` folder to
`data/files/`, then start the app again. (Older backups have an `uploads/` folder instead: copy it to
`data/uploads/` and the app moves the files into `data/files/` when it starts.)

## Where data is stored

| What | Where | Setting |
| --- | --- | --- |
| Records, doctors, labs, tags (SQLite, WAL mode) | `data/medical_records.db` | `DATABASE_URL` |
| Attached files | `data/files/<user id>/<random uuid>.<ext>` | `FILES_DIR` |
| Copy of the database taken before an upgrade changes it | `data/backups/pre-<revision>-<time>.db` | (next to the database) |

Every record, doctor, laboratory and tag belongs to one user. Upgrades run by themselves when the app starts:
existing data is given to the `ADMIN_EMAIL` account, and files from the old `data/uploads/<type>/` layout
(`UPLOAD_DIR`) are moved into `data/files/<user id>/`. If anything goes wrong, stop the app, put the `pre-…` copy
back as `data/medical_records.db` and move the files back.

On a server, keep the database and the files folder on the same local disk (for example one attached block volume).
SQLite must not live on a network file system (NFS).

## Security notes

- Google OAuth (authorisation-code flow with PKCE and a state check). Only the admin (`ADMIN_EMAIL`) and
  accounts created from an invite get a session; anyone else is refused. A disabled account is signed out on its
  next request.
- Invites are single-use, bound to one email and valid for 7 days. The database keeps only an HMAC of each invite
  link's secret. The admin panel shows accounts, invites and storage used, never anyone's records or files.
- Server-side sessions: the browser holds only a random token in an HTTP-only, `SameSite=Lax` cookie (Secure when
  you use HTTPS). The database stores an HMAC of the token, never the token. Sessions expire after 14 days.
- Every record, doctor, laboratory, tag and file belongs to one user, and every query is limited to the signed-in
  user. Someone else's item answers exactly like one that does not exist (404), in lists, search, the timeline,
  file downloads, backup and export alike. Tests sign in two users and check this both ways round.
- Every `/api` route except sign-in and `/api/health` requires a valid session. State-changing requests also need
  a custom header and are refused when their `Origin` is another site, which blocks cross-site request forgery.
  No CORS is enabled. Tests check this for every route the app has.
- On a server, `GOOGLE_REDIRECT_URI` must be `https://` (the app will not start otherwise), so session cookies are
  always `Secure` and HSTS is on. Plain `http://` only works for `localhost`.
- Rate limits (in memory, cleared on restart): sign-in and invite-link checks 20 per 10 minutes per IP address,
  invite creation 30 per hour per admin, uploads 100 files per hour per account. Run the app behind a reverse proxy
  on the same machine (for example Caddy), so the app sees each visitor's real IP address.
- **Profile → Sign out of all devices** ends every session of your account, for a lost phone or a shared computer.
- Uploaded files live outside any public folder and are only served through authenticated endpoints. Stored names are
  random UUIDs, paths are checked to stay inside the user's files folder, and the file type is verified from the file's
  actual contents (not its name or the browser's claim). Size is limited by `MAX_UPLOAD_SIZE_MB` per file and by
  each account's storage limit, checked while the file streams in. Files are served with their real type, `nosniff`,
  a download/inline `Content-Disposition` and `Content-Security-Policy: default-src 'none'; sandbox`, so even a
  disguised HTML or SVG file could never run.
- Optional virus scan: set `CLAMAV_SOCKET` to clamd's socket and every upload is scanned first. If the scanner is
  switched on but not answering, uploads are refused rather than let through (see DEPLOY.md).
- Security headers (CSP, `nosniff`, frame protection, no referrer, `no-store` for API responses). The interactive
  API docs are disabled.
- All database access goes through SQLAlchemy with bound parameters. Error messages and logs never include record
  contents or search terms.
- `.env`, `data/` and backups are excluded from Git. There are no credentials in the source code.

## Limitations

- Invite links are copied and sent by hand; the app does not send email.
- Backups are plain (unencrypted) ZIP files, and there is no in-app restore button (see the steps above).
- Search is a case-insensitive substring match on the text you entered; it does not understand synonyms.
- Case-insensitive matching in SQLite covers English letters; accented characters match case-sensitively.
- Uploads are limited to PDF, JPG, JPEG, PNG and HEIC. Chrome and most Android browsers cannot display HEIC, so those
  photos are offered as a download.
- Not built in the MVP, by design: OCR, AI summaries, natural-language search, result graphs, medication history,
  PWA/offline mode and encrypted backups.

## API overview

All paths are under `/api` and need a session cookie unless noted.

| Area | Endpoints |
|------|-----------|
| Auth | `GET /auth/login`, `GET /auth/callback` (Google), `GET /auth/me`, `POST /auth/logout` |
| Records | `GET/POST /records`, `GET/PUT/DELETE /records/{id}` |
| Search / timeline | `GET /search?q=…`, `GET /records?record_type=…&date_from=…&date_to=…&tag=…`, `GET /timeline`, `GET /tags` |
| Doctors / labs | `GET/POST /doctors`, `GET/PUT/DELETE /doctors/{id}`, same for `/labs` |
| Documents | `POST /records/{id}/documents`, `GET /documents/{id}`, `GET /documents/{id}/view`, `GET /documents/{id}/download`, `DELETE /documents/{id}` |
| Backup | `GET /backup` (ZIP), `GET /export/json` |
| Misc | `GET /health` (public), `GET /config` |
