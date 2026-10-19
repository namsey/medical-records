"""Account-level actions shared by the admin panel and the account owner: deleting an account and exporting
everything in it ("Download my data")."""

import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, MedicalRecord, User, utcnow
from app.privacy import PRIVACY_VERSION
from app.security import get_current_user
from app.services import audit, invites, sessions
from app.services.backup import archive_slot, build_json_export, scratch_dir
from app.services.storage import FileStore, get_file_store

_UNSAFE_PATH_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def delete_account(db: Session, user: User, files: FileStore) -> None:
    """Delete the account and everything in it: records, doctors, laboratories, tags, files and sessions."""
    user_id = user.id
    # Records first (their documents, medicines, results and tag links go with them), so no record still points
    # at a doctor or laboratory when the account's other rows are removed with it.
    db.execute(delete(MedicalRecord).where(MedicalRecord.user_id == user_id))
    db.execute(delete(User).where(User.id == user_id))
    db.commit()
    files.delete_user_files(user_id)


def _folder_name(record: MedicalRecord) -> str:
    title = _UNSAFE_PATH_CHARS.sub("_", record.title).strip(" .") or "Record"
    return f"{record.record_date.isoformat()} {title[:80]}"


def _unique(name: str, taken: set[str]) -> str:
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    candidate, number = name, 2
    while candidate.lower() in taken:
        candidate = f"{stem} ({number}){dot}{extension}"
        number += 1
    taken.add(candidate.lower())
    return candidate


def build_data_export(db: Session, user_id: str, files: FileStore) -> Path:
    """ZIP with records.json and every attached file under its original name, one folder per record.
    Written to a temporary file on the data disk; the caller deletes it."""
    with archive_slot():
        return _build_data_export(db, user_id, files)


def _build_data_export(db: Session, user_id: str, files: FileStore) -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="medical-export-", suffix=".zip", delete=False, dir=scratch_dir())
    handle.close()
    archive_path = Path(handle.name)
    rows = db.execute(
        select(Document, MedicalRecord)
        .join(MedicalRecord, Document.record_id == MedicalRecord.id)
        .where(MedicalRecord.user_id == user_id)
        .order_by(MedicalRecord.record_date, Document.created_at)
    ).all()
    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("records.json", build_json_export(db, user_id))
            taken: set[str] = set()
            missing = 0
            for document, record in rows:
                path = files.path(user_id, document.stored_filename)
                if not path.is_file():
                    missing += 1
                    continue
                folder = _folder_name(record)
                archive.write(path, f"files/{_unique(f'{folder}/{document.original_filename}', taken)}")
            readme = [
                "Your medical records, as downloaded from the app.",
                f"Made: {datetime.now(timezone.utc).isoformat()}",
                "records.json: every record, doctor and laboratory, with medicines, lab results, tags and the list",
                "of attached files. files/: the attached files, one folder per record (date and title).",
            ]
            if missing:
                readme.append(f"{missing} attached file(s) were missing on the server and are not included.")
            archive.writestr("README.txt", "\n".join(readme) + "\n")
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise
    return archive_path


class Account:
    """The signed-in person's own account (consent, data download, deletion), for the account router."""

    def __init__(self, db: Session, user: User, files: FileStore | None = None) -> None:
        self.db = db
        self.user = user
        self.files = files or get_file_store()

    def give_consent(self, version: str) -> None:
        if version != PRIVACY_VERSION:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The privacy notice has changed. Reload the page.")
        self.user.consent_version = PRIVACY_VERSION
        self.user.consented_at = utcnow()
        self.db.commit()
        audit.record(self.db, "consent_given", actor=self.user, target=self.user, detail=PRIVACY_VERSION)

    def data_export(self) -> Path:
        archive = build_data_export(self.db, self.user.id, self.files)
        audit.record(self.db, "data_downloaded", actor=self.user, target=self.user)
        return archive

    def delete(self, confirm_email: str) -> None:
        if sessions.is_admin(self.user):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The admin account cannot be deleted, so the app always has an admin.",
            )
        if invites.normalize_email(confirm_email) != self.user.email.lower():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Type your email to confirm")
        email = self.user.email
        delete_account(self.db, self.user, self.files)
        audit.record(self.db, "account_deleted", target_email=email, detail="by the account owner")


def get_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Account:
    return Account(db, user)
