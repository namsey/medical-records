"""Start the real backend for the end-to-end tests, signed in, against a fresh throwaway database.

Run by Playwright's webServer (see playwright.config.ts); it serves the production build from frontend/dist.

1. Wipes E2E_DATA_DIR and points the app's database and files folder at it (never at your real data/).
2. Runs the migrations and creates a login session for the allowed account, the same way the backend tests do,
   and writes it as a Playwright storage state file (E2E_STATE_FILE). The app's Google-only sign-in is unchanged:
   no test-only login route exists in the app.
3. Serves the app on 127.0.0.1:E2E_PORT.
"""

import json
import os
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
DATA_DIR = Path(os.environ["E2E_DATA_DIR"]).resolve()
STATE_FILE = Path(os.environ["E2E_STATE_FILE"]).resolve()
PORT = int(os.environ.get("E2E_PORT", "8765"))
EMAIL = "e2e@example.com"

# Refuse to wipe anything that looks like the real data folder.
if DATA_DIR == (BACKEND.parent / "data").resolve() or not DATA_DIR.name.startswith("medical-records-e2e"):
    sys.exit(f"Refusing to use {DATA_DIR} as the end-to-end data folder")

shutil.rmtree(DATA_DIR, ignore_errors=True)
DATA_DIR.mkdir(parents=True)

# Settings are read from the environment when the app is imported, so set them first.
os.environ.update(
    {
        "GOOGLE_CLIENT_ID": "e2e-client-id",
        "GOOGLE_CLIENT_SECRET": "e2e-client-secret",
        "GOOGLE_REDIRECT_URI": f"http://127.0.0.1:{PORT}/api/auth/callback",
        "ALLOWED_EMAIL": EMAIL,
        "SESSION_SECRET": "e2e-session-secret-e2e-session-secret-1234",
        "DATABASE_URL": f"sqlite:///{DATA_DIR / 'e2e.db'}",
        "FILES_DIR": str(DATA_DIR / "files"),
        "UPLOAD_DIR": str(DATA_DIR / "uploads"),
    }
)
sys.path.insert(0, str(BACKEND))

import uvicorn  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.migrations import run_migrations  # noqa: E402
from app.services import sessions  # noqa: E402

run_migrations()
with SessionLocal() as db:
    token = sessions.create_session(db, sessions.get_or_create_user(db, EMAIL, "E2E"))

STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.write_text(
    json.dumps(
        {
            "cookies": [
                {
                    "name": "session",
                    "value": token,
                    "domain": "127.0.0.1",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ],
            "origins": [],
        }
    )
)

uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, access_log=False)
