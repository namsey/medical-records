"""Test helper for test-backup.sh: create real app data, keep writing during a backup, or fingerprint a data folder.

    python app_data.py seed  <data dir>              migrate, then 2 users with records, doctors, tags and files
    python app_data.py write <data dir> <seconds>    keep adding records with files (simulates use during a backup)
    python app_data.py fingerprint <data dir>        print a digest of every table row and file (no sessions)

Needs the backend's requirements (run with the backend's Python).
"""

import asyncio
import hashlib
import io
import os
import sqlite3
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
COMMAND, DATA_DIR = sys.argv[1], Path(sys.argv[2]).resolve()
USERS = ("first@example.com", "second@example.com")


def _setup_app():
    os.environ.update(
        {
            "GOOGLE_CLIENT_ID": "test",
            "GOOGLE_CLIENT_SECRET": "test",
            "GOOGLE_REDIRECT_URI": "http://127.0.0.1/api/auth/callback",
            "ALLOWED_EMAIL": USERS[0],
            "SESSION_SECRET": "backup-test-secret-backup-test-secret",
            "DATABASE_URL": f"sqlite:///{DATA_DIR / 'medical_records.db'}",
            "FILES_DIR": str(DATA_DIR / "files"),
            "UPLOAD_DIR": str(DATA_DIR / "uploads"),
        }
    )
    sys.path.insert(0, str(BACKEND))


def _add_record(store, number: int, with_file: bool) -> None:
    from starlette.datastructures import UploadFile

    from app.schemas import RecordIn

    record = store.create(
        RecordIn.model_validate(
            {
                "record_type": "prescription",
                "title": f"Record {number}",
                "record_date": "2026-01-15",
                "medicines": [{"name": f"Medicine {number}"}],
                "tags": ["Backup test"],
            }
        )
    )
    if with_file:
        content = b"%PDF-1.4\n" + os.urandom(2048) + b"\n%%EOF\n"
        asyncio.run(store.add_documents(record, [UploadFile(file=io.BytesIO(content), filename=f"r{number}.pdf")]))


def seed() -> None:
    _setup_app()
    from app.database import SessionLocal
    from app.migrations import run_migrations
    from app.services import sessions
    from app.services.record_store import SqlRecordStore

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_migrations()
    with SessionLocal() as db:
        for email in USERS:
            user = sessions.get_or_create_user(db, email, None)
            sessions.create_session(db, user)
            store = SqlRecordStore(db, user.id)
            store.create_doctor({"name": f"Dr. {email}"})
            for number in range(5):
                _add_record(store, number, with_file=True)


def write(seconds: float) -> None:
    _setup_app()
    from app.database import SessionLocal
    from app.models import User
    from app.services.record_store import SqlRecordStore

    deadline = time.monotonic() + seconds
    number = 1000
    with SessionLocal() as db:
        store = SqlRecordStore(db, db.query(User).filter_by(email=USERS[0]).one().id)
        while time.monotonic() < deadline:
            _add_record(store, number, with_file=True)
            number += 1


def fingerprint() -> None:
    digest = hashlib.sha256()
    connection = sqlite3.connect(DATA_DIR / "medical_records.db")
    try:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for table in tables:
            if table == "sessions":
                continue
            for row in sorted(repr(row) for row in connection.execute(f"SELECT * FROM {table}")):
                digest.update(f"{table}:{row}".encode())
    finally:
        connection.close()
    for path in sorted((DATA_DIR / "files").rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(DATA_DIR).as_posix().encode() + hashlib.sha256(path.read_bytes()).digest())
    print(digest.hexdigest())


if __name__ == "__main__":
    {"seed": seed, "write": lambda: write(float(sys.argv[3])), "fingerprint": fingerprint}[COMMAND]()
