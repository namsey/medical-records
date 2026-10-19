"""RecordStore: everything the API reads or writes about one user's records, doctors, laboratories and tags.

Every store is bound to one user, so a query can only ever see that user's rows. Something that belongs to
another user looks exactly like something that does not exist (404). The only implementation is SQLite.
"""

import asyncio
from pathlib import Path
from typing import Any, Protocol, TypeVar

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.database import get_db
from app.models import Doctor, Document, Lab, MedicalRecord, Tag, User, record_tags
from app.schemas import RecordIn
from app.security import get_current_user
from app.services import backup, storage
from app.services import records as record_service
from app.services.search import RecordFilters, search_records
from app.services.storage import FileStore, get_file_store

Owned = TypeVar("Owned", Doctor, Lab)

_upload_locks: dict[str, asyncio.Lock] = {}


def _upload_lock(user_id: str) -> asyncio.Lock:
    return _upload_locks.setdefault(user_id, asyncio.Lock())


def formatted_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class RecordStore(Protocol):
    user_id: str

    def search(self, filters: RecordFilters, limit: int | None, offset: int = 0) -> tuple[list[MedicalRecord], int]: ...
    def years(self) -> list[tuple[int, int]]: ...
    def tags(self) -> list[tuple[str, int]]: ...
    def get(self, record_id: str, *, full: bool = True) -> MedicalRecord: ...
    def create(self, payload: RecordIn) -> MedicalRecord: ...
    def update(self, record: MedicalRecord, payload: RecordIn) -> MedicalRecord: ...
    def delete(self, record: MedicalRecord) -> None: ...
    def get_document(self, document_id: str) -> Document: ...
    def document_path(self, document: Document) -> Path: ...
    async def add_documents(self, record: MedicalRecord, uploads: list[UploadFile]) -> list[Document]: ...
    def delete_document(self, document: Document) -> None: ...
    def storage_used_bytes(self) -> int: ...
    def quota_bytes(self) -> int: ...
    def backup_zip(self) -> Path: ...
    def export_json(self) -> str: ...
    def list_doctors(self, q: str | None) -> list[Doctor]: ...
    def list_labs(self, q: str | None) -> list[Lab]: ...
    def get_doctor(self, doctor_id: str) -> Doctor: ...
    def get_lab(self, lab_id: str) -> Lab: ...
    def create_doctor(self, values: dict[str, Any]) -> Doctor: ...
    def create_lab(self, values: dict[str, Any]) -> Lab: ...
    def update_item(self, item: Owned, values: dict[str, Any]) -> Owned: ...
    def delete_item(self, item: Doctor | Lab) -> None: ...
    def doctor_record_counts(self) -> dict[str, int]: ...
    def lab_record_counts(self) -> dict[str, int]: ...


class SqlRecordStore:
    def __init__(self, db: Session, user_id: str, files: FileStore | None = None) -> None:
        self.db = db
        self.user_id = user_id
        self.files = files or get_file_store()

    # ------------------------------------------------------------ records

    def search(self, filters: RecordFilters, limit: int | None, offset: int = 0) -> tuple[list[MedicalRecord], int]:
        return search_records(self.db, self.user_id, filters, limit, offset)

    def years(self) -> list[tuple[int, int]]:
        """Every year that has records, newest first, with its record count."""
        year = func.strftime("%Y", MedicalRecord.record_date)
        rows = self.db.execute(
            select(year, func.count(MedicalRecord.id))
            .where(MedicalRecord.user_id == self.user_id)
            .group_by(year)
            .order_by(year.desc())
        ).all()
        return [(int(value), count) for value, count in rows]

    def tags(self) -> list[tuple[str, int]]:
        """Every tag in use, alphabetically, with its record count."""
        rows = self.db.execute(
            select(Tag.name, func.count(record_tags.c.record_id))
            .join(record_tags, record_tags.c.tag_id == Tag.id)
            .where(Tag.user_id == self.user_id)
            .group_by(Tag.id)
            .order_by(func.lower(Tag.name))
        ).all()
        return [(name, count) for name, count in rows]

    def get(self, record_id: str, *, full: bool = True) -> MedicalRecord:
        return record_service.get_record_or_404(self.db, self.user_id, record_id, full=full)

    def create(self, payload: RecordIn) -> MedicalRecord:
        return record_service.create_record(self.db, self.user_id, payload)

    def update(self, record: MedicalRecord, payload: RecordIn) -> MedicalRecord:
        return record_service.update_record(self.db, record, payload)

    def delete(self, record: MedicalRecord) -> None:
        for stored_name in record_service.delete_record(self.db, record):
            self.files.delete(self.user_id, stored_name)

    # ------------------------------------------------------------ documents

    def get_document(self, document_id: str) -> Document:
        document = self.db.scalar(
            select(Document)
            .join(MedicalRecord, Document.record_id == MedicalRecord.id)
            .where(Document.id == document_id, MedicalRecord.user_id == self.user_id)
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return document

    def document_path(self, document: Document) -> Path:
        """Where the document's file is (it may be missing)."""
        return self.files.path(self.user_id, document.stored_filename)

    def quota_bytes(self) -> int:
        user = self.db.get(User, self.user_id)
        return storage.quota_bytes(user.quota_bytes if user else None)

    async def add_documents(self, record: MedicalRecord, uploads: list[UploadFile]) -> list[Document]:
        """Store the files and their rows on the user's record, within the account's storage limit.
        All are stored or none are."""
        # One upload at a time per account, so two at once cannot both fit into the same free space.
        async with _upload_lock(self.user_id):
            return await self._add_documents(record, uploads)

    async def _add_documents(self, record: MedicalRecord, uploads: list[UploadFile]) -> list[Document]:
        quota = self.quota_bytes()
        used = self.storage_used_bytes()
        saved: list[Document] = []
        try:
            for upload in uploads:
                space_left = quota - used - sum(document.size_bytes for document in saved)
                try:
                    if space_left <= 0:
                        raise storage.NotEnoughSpace(storage.sanitize_filename(upload.filename))
                    stored = await self.files.save(self.user_id, upload, space_left=space_left)
                except storage.NotEnoughSpace as error:
                    free = formatted_size(max(quota - used, 0))
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Not enough storage left for '{error.display_name}': {free} free of "
                        f"{formatted_size(quota)}.",
                    ) from error
                saved.append(
                    Document(
                        record_id=record.id,
                        original_filename=stored.display_name,
                        stored_filename=stored.stored_name,
                        content_type=stored.content_type,
                        size_bytes=stored.size_bytes,
                    )
                )
            self.db.add_all(saved)
            self.db.commit()
        except BaseException:
            self.db.rollback()
            for document in saved:
                self.files.delete(self.user_id, document.stored_filename)
            raise
        return saved

    def delete_document(self, document: Document) -> None:
        stored_name = document.stored_filename
        self.db.delete(document)
        self.db.commit()
        self.files.delete(self.user_id, stored_name)

    def storage_used_bytes(self) -> int:
        """Total size of the user's stored files, from the database (no walk over the disk)."""
        total = self.db.scalar(
            select(func.sum(Document.size_bytes))
            .join(MedicalRecord, Document.record_id == MedicalRecord.id)
            .where(MedicalRecord.user_id == self.user_id)
        )
        return total or 0

    # ------------------------------------------------------------ backup and export

    def backup_zip(self) -> Path:
        """ZIP of a database copy holding only this user's data, plus their files (caller deletes it)."""
        return backup.create_backup_zip(self.user_id)

    def export_json(self) -> str:
        return backup.build_json_export(self.db, self.user_id)

    # ------------------------------------------------------------ doctors and laboratories

    def list_doctors(self, q: str | None) -> list[Doctor]:
        stmt = select(Doctor).where(Doctor.user_id == self.user_id).order_by(func.lower(Doctor.name))
        if q and q.strip():
            term = q.strip()
            stmt = stmt.where(
                Doctor.name.icontains(term, autoescape=True)
                | Doctor.specialization.icontains(term, autoescape=True)
                | Doctor.hospital.icontains(term, autoescape=True)
            )
        return list(self.db.scalars(stmt).all())

    def list_labs(self, q: str | None) -> list[Lab]:
        stmt = select(Lab).where(Lab.user_id == self.user_id).order_by(func.lower(Lab.name))
        if q and q.strip():
            stmt = stmt.where(Lab.name.icontains(q.strip(), autoescape=True))
        return list(self.db.scalars(stmt).all())

    def _owned_or_404(self, model: type[Owned], item_id: str, label: str) -> Owned:
        item = self.db.get(model, item_id)
        if item is None or item.user_id != self.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
        return item

    def get_doctor(self, doctor_id: str) -> Doctor:
        return self._owned_or_404(Doctor, doctor_id, "Doctor")

    def get_lab(self, lab_id: str) -> Lab:
        return self._owned_or_404(Lab, lab_id, "Laboratory")

    def create_doctor(self, values: dict[str, Any]) -> Doctor:
        doctor = Doctor(**values, user_id=self.user_id)
        self.db.add(doctor)
        self.db.commit()
        return doctor

    def create_lab(self, values: dict[str, Any]) -> Lab:
        lab = Lab(**values, user_id=self.user_id)
        self.db.add(lab)
        self.db.commit()
        return lab

    def update_item(self, item: Owned, values: dict[str, Any]) -> Owned:
        for key, value in values.items():
            setattr(item, key, value)
        self.db.commit()
        return item

    def delete_item(self, item: Doctor | Lab) -> None:
        self.db.delete(item)
        self.db.commit()

    def _record_counts(self, column) -> dict[str, int]:
        rows = self.db.execute(
            select(column, func.count())
            .where(column.is_not(None), MedicalRecord.user_id == self.user_id)
            .group_by(column)
        ).all()
        return {key: count for key, count in rows}

    def doctor_record_counts(self) -> dict[str, int]:
        return self._record_counts(MedicalRecord.doctor_id)

    def lab_record_counts(self) -> dict[str, int]:
        return self._record_counts(MedicalRecord.lab_id)


def get_record_store(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RecordStore:
    """FastAPI dependency: the signed-in user's store (the session lookup is shared with the auth check)."""
    return SqlRecordStore(db, user.id)
