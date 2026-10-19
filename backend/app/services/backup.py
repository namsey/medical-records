"""Backup (ZIP of database + uploaded files) and structured JSON export of one user's data."""

import json
import logging
import os
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Doctor, Lab, MedicalRecord, Tag
from app.schemas import DoctorOut, LabOut, RecordOut
from app.services.records import FULL_LOAD
from app.services.storage import get_file_store

logger = logging.getLogger(__name__)

APP_VERSION = "1.0"

# Building an archive reads and compresses every file of an account: at most two at a time, server-wide.
ARCHIVE_SLOTS = threading.BoundedSemaphore(2)
ARCHIVE_WAIT_SECONDS = 5


@contextmanager
def archive_slot() -> Iterator[None]:
    """Hold one of the archive-building slots, or answer 503 if none frees up within a few seconds."""
    if not ARCHIVE_SLOTS.acquire(timeout=ARCHIVE_WAIT_SECONDS):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Busy, try again in a minute")
    try:
        yield
    finally:
        ARCHIVE_SLOTS.release()


def scratch_dir() -> Path:
    """Temporary archives and database copies: on the data disk next to the database, never the boot disk."""
    folder = get_settings().sqlite_path.parent / "tmp"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder


def prepare_scratch_dir() -> None:
    """At startup: create the scratch folder (owner only) and remove anything an earlier run left in it."""
    folder = scratch_dir()
    os.chmod(folder, 0o700)
    removed = 0
    for item in folder.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)
        removed += 1
    if removed:
        logger.info("Removed %d leftover temporary files", removed)


def backup_filename(today: date | None = None) -> str:
    return f"medical-records-backup-{(today or date.today()).isoformat()}.zip"


def export_filename(today: date | None = None) -> str:
    return f"medical-records-export-{(today or date.today()).isoformat()}.json"


# The only tables the per-user copy keeps rows of. Every other table (login sessions, invites, the audit log and
# any table added later) is emptied, so nothing about other accounts or the server leaves with it.
KEPT_TABLES = {
    "alembic_version",
    "users",
    "medical_records",
    "doctors",
    "labs",
    "tags",
    "record_tags",
    "prescription_medicines",
    "lab_results",
    "documents",
}

# Within the kept tables, other users' rows go. Deleting the records first cascades to their documents, medicines,
# lab results and tag links, and leaves no record pointing at a doctor or laboratory that is about to go.
OTHER_USERS_ROWS = (
    "DELETE FROM medical_records WHERE user_id != :user",
    "DELETE FROM doctors WHERE user_id != :user",
    "DELETE FROM labs WHERE user_id != :user",
    "DELETE FROM tags WHERE user_id != :user",
    "DELETE FROM users WHERE id != :user",
)


def _snapshot_database(destination: Path, user_id: str) -> None:
    """Write a consistent copy of the live database holding only this user's data (safe while the app runs)."""
    source = sqlite3.connect(get_settings().sqlite_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        target.execute("PRAGMA foreign_keys=ON")
        tables = [row[0] for row in target.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            if table not in KEPT_TABLES and not table.startswith("sqlite_"):
                target.execute(f'DELETE FROM "{table}"')
        for statement in OTHER_USERS_ROWS:
            target.execute(statement, {"user": user_id})
        target.commit()
        # Rewrite the file so deleted rows do not linger in free pages.
        target.execute("VACUUM")
    finally:
        target.close()
        source.close()


def create_backup_zip(user_id: str) -> Path:
    """Build the user's backup archive in a temporary file and return its path (caller deletes it)."""
    with archive_slot():
        return _build_backup_zip(user_id)


def _build_backup_zip(user_id: str) -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="medical-backup-", suffix=".zip", delete=False, dir=scratch_dir())
    handle.close()
    archive_path = Path(handle.name)
    try:
        # The copy briefly holds every account's data before the others are removed: keep it on the data disk.
        with tempfile.TemporaryDirectory(prefix="medical-backup-db-", dir=scratch_dir()) as workdir:
            snapshot = Path(workdir) / "medical_records.db"
            _snapshot_database(snapshot, user_id)
            file_count = 0
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "database/medical_records.db")
                for absolute, relative in get_file_store().iter_files(user_id):
                    archive.write(absolute, f"files/{relative}")
                    file_count += 1
                manifest = {
                    "app": "personal-medical-records",
                    "version": APP_VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "uploaded_files": file_count,
                    "restore": "Stop the app, put database/medical_records.db at data/medical_records.db "
                    "and the files/ folder at data/files/, then start the app again.",
                }
                archive.writestr("backup_info.json", json.dumps(manifest, indent=2))
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise
    return archive_path


def build_json_export(db: Session, user_id: str) -> str:
    records = db.scalars(
        select(MedicalRecord)
        .where(MedicalRecord.user_id == user_id)
        .options(*FULL_LOAD)
        .order_by(MedicalRecord.record_date.desc(), MedicalRecord.created_at.desc())
    ).all()
    doctors = db.scalars(select(Doctor).where(Doctor.user_id == user_id).order_by(Doctor.name)).all()
    labs = db.scalars(select(Lab).where(Lab.user_id == user_id).order_by(Lab.name)).all()
    tag_count = db.scalar(select(func.count()).select_from(Tag).where(Tag.user_id == user_id)) or 0
    payload = {
        "app": "personal-medical-records",
        "version": APP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "records": len(records),
            "doctors": len(doctors),
            "laboratories": len(labs),
            "tags": tag_count,
        },
        "doctors": [DoctorOut.model_validate(d).model_dump(mode="json", exclude={"record_count"}) for d in doctors],
        "laboratories": [LabOut.model_validate(x).model_dump(mode="json", exclude={"record_count"}) for x in labs],
        "records": [RecordOut.model_validate(r).model_dump(mode="json") for r in records],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)

