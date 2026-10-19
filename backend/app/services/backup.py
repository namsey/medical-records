"""Backup (ZIP of database + uploaded files) and structured JSON export of one user's data."""

import json
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Doctor, Lab, MedicalRecord, Tag
from app.schemas import DoctorOut, LabOut, RecordOut
from app.services.records import FULL_LOAD
from app.services.storage import get_file_store

APP_VERSION = "1.0"


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
    handle = tempfile.NamedTemporaryFile(prefix="medical-backup-", suffix=".zip", delete=False)
    handle.close()
    archive_path = Path(handle.name)
    try:
        with tempfile.TemporaryDirectory(prefix="medical-backup-db-") as workdir:
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

