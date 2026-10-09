"""Backup (ZIP of database + uploaded files) and structured JSON export."""

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
from app.services.storage import iter_stored_files

APP_VERSION = "1.0"


def backup_filename(today: date | None = None) -> str:
    return f"medical-records-backup-{(today or date.today()).isoformat()}.zip"


def export_filename(today: date | None = None) -> str:
    return f"medical-records-export-{(today or date.today()).isoformat()}.json"


def _snapshot_database(destination: Path) -> None:
    """Write a consistent copy of the live SQLite database (safe while the app is running)."""
    source = sqlite3.connect(get_settings().sqlite_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        # Login sessions are not part of the medical data and must not leave the server.
        target.execute("DELETE FROM sessions")
        target.commit()
    finally:
        target.close()
        source.close()


def create_backup_zip() -> Path:
    """Build the backup archive in a temporary file and return its path (caller deletes it)."""
    settings = get_settings()
    handle = tempfile.NamedTemporaryFile(prefix="medical-backup-", suffix=".zip", delete=False)
    handle.close()
    archive_path = Path(handle.name)
    try:
        with tempfile.TemporaryDirectory(prefix="medical-backup-db-") as workdir:
            snapshot = Path(workdir) / "medical_records.db"
            _snapshot_database(snapshot)
            file_count = 0
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "database/medical_records.db")
                for absolute, relative in iter_stored_files(settings.upload_path):
                    archive.write(absolute, f"uploads/{relative}")
                    file_count += 1
                manifest = {
                    "app": "personal-medical-records",
                    "version": APP_VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "uploaded_files": file_count,
                    "restore": "Stop the app, put database/medical_records.db at data/medical_records.db "
                    "and the uploads/ folder at data/uploads/, then start the app again.",
                }
                archive.writestr("backup_info.json", json.dumps(manifest, indent=2))
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise
    return archive_path


def build_json_export(db: Session) -> str:
    records = db.scalars(
        select(MedicalRecord)
        .options(*FULL_LOAD)
        .order_by(MedicalRecord.record_date.desc(), MedicalRecord.created_at.desc())
    ).all()
    doctors = db.scalars(select(Doctor).order_by(Doctor.name)).all()
    labs = db.scalars(select(Lab).order_by(Lab.name)).all()
    tag_count = db.scalar(select(func.count()).select_from(Tag)) or 0
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

