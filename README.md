# Personal Medical Records

A private, single-user web app for storing and organising your own medical records: doctor visits,
prescriptions, lab reports, diagnoses, scans and documents. It is built mobile-first for an Android phone
and keeps everything on your own machine (SQLite database plus a local uploads folder, no cloud storage).

**Workflow:** Add → Upload → Organise → Search → View → Download

- Sign-in with **Google only**, restricted to one allowed Gmail account. No passwords, no registration.
- Records: Doctor Visit, Prescription (multiple medicines), Lab Report (optional individual results),
  Diagnosis, Medical Document, Scan, Other. Tags, doctor and laboratory directories.
- Attach PDF / JPG / PNG / WEBP files. PDFs and images open **inside the app** (no download needed),
  including on Android where the browser cannot show PDFs by itself.
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
data/               Created on first run: medical_records.db and uploads/  (never commit this)
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
notepad .env        # fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ALLOWED_EMAIL, SESSION_SECRET
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
cd frontend && npm test                                            # component / flow tests
cd frontend && npm run build                                       # strict TypeScript check + production build
```

The backend tests use a temporary database and upload folder and never touch your real data. Google is not
contacted: the sign-in tests replace the Google call.

### Database migrations

Migrations run automatically on start-up. After changing `backend/app/models.py`:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Backup and restore

In the app open **Home → menu (top right) → Backup and export**:

- **Full backup (ZIP)** → `medical-records-backup-YYYY-MM-DD.zip` containing the SQLite database and every
  uploaded file. Login sessions are left out.
- **Export records (JSON)** → structured data (doctors, laboratories, records, medicines, results, tags and
  attachment metadata) without the files.

Backups contain your private medical data. Store them somewhere safe (they are not encrypted).

To restore: stop the app, unzip the backup, copy `database/medical_records.db` to `data/medical_records.db`
(delete any `medical_records.db-wal` / `-shm` files next to it) and copy the `uploads/` folder to
`data/uploads/`, then start the app again.

## Security notes

- Google OAuth (authorisation-code flow with PKCE and a state check). Only the verified account matching
  `ALLOWED_EMAIL` gets a session; anyone else is refused.
- Server-side sessions: the browser holds only a random token in an HTTP-only, `SameSite=Lax` cookie (Secure when
  you use HTTPS). The database stores an HMAC of the token, never the token. Sessions expire after 14 days.
- Every `/api` route except sign-in and `/api/health` requires a valid session. State-changing requests also need
  a custom header, which blocks cross-site request forgery. No CORS is enabled.
- Uploaded files live outside any public folder and are only served through authenticated endpoints. Stored names are
  random UUIDs, paths are checked to stay inside the upload folder, and the file type is verified from the file's
  actual contents (not its name or the browser's claim). Size is limited by `MAX_UPLOAD_SIZE_MB`.
- Security headers (CSP, `nosniff`, frame protection, no referrer, `no-store` for API responses). The interactive
  API docs are disabled.
- All database access goes through SQLAlchemy with bound parameters. Error messages and logs never include record
  contents or search terms.
- `.env`, `data/` and backups are excluded from Git. There are no credentials in the source code.

## Limitations

- Single user by design. Changing `ALLOWED_EMAIL` locks out the previous account.
- Backups are plain (unencrypted) ZIP files, and there is no in-app restore button (see the steps above).
- Search is a case-insensitive substring match on the text you entered; it does not understand synonyms.
- Case-insensitive matching in SQLite covers English letters; accented characters match case-sensitively.
- Uploads are limited to PDF, JPG, JPEG, PNG and WEBP (for example, iPhone HEIC photos must be converted first).
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
