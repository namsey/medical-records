"""Record persistence helpers: applying payloads, tags, titles, summaries and deletion."""

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Doctor,
    Lab,
    LabResult,
    MedicalRecord,
    PrescriptionMedicine,
    Tag,
    record_tags,
)
from app.schemas import RECORD_TYPE_LABELS, RecordIn, RecordSummary, RecordType, TimelineItem
from app.services import storage

SCALAR_FIELDS = (
    "hospital",
    "specialization",
    "reason",
    "symptoms",
    "diagnosis",
    "description",
    "treatment",
    "doctor_notes",
    "summary",
    "personal_notes",
    "test_name",
    "follow_up_date",
    "report_date",
)

# Eager loading used whenever a full record is serialised.
FULL_LOAD = (
    selectinload(MedicalRecord.doctor),
    selectinload(MedicalRecord.lab),
    selectinload(MedicalRecord.medicines),
    selectinload(MedicalRecord.results),
    selectinload(MedicalRecord.documents),
    selectinload(MedicalRecord.tags),
)

LIST_LOAD = (
    selectinload(MedicalRecord.doctor),
    selectinload(MedicalRecord.lab),
    selectinload(MedicalRecord.documents),
    selectinload(MedicalRecord.tags),
)


def get_record_or_404(db: Session, record_id: str, *, full: bool = True) -> MedicalRecord:
    options = FULL_LOAD if full else LIST_LOAD
    record = db.scalar(select(MedicalRecord).where(MedicalRecord.id == record_id).options(*options))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return record


def _default_title(payload: RecordIn, doctor: Doctor | None) -> str:
    label = RECORD_TYPE_LABELS[payload.record_type.value]
    detail: str | None = None
    if payload.record_type == RecordType.lab_report:
        detail = payload.test_name
    elif payload.record_type == RecordType.diagnosis:
        detail = payload.diagnosis
    elif payload.record_type in (RecordType.doctor_visit, RecordType.prescription):
        detail = doctor.name if doctor else payload.reason
    if detail:
        first_line = detail.strip().splitlines()[0]
        if len(first_line) > 80:
            first_line = first_line[:77].rstrip() + "..."
        return f"{label} - {first_line}"
    return label


def _sync_tags(db: Session, record: MedicalRecord, names: list[str]) -> None:
    tags: list[Tag] = []
    for name in names:
        key = name.lower()
        tag = db.scalar(select(Tag).where(Tag.name_key == key))
        if tag is None:
            tag = Tag(name=name, name_key=key)
            db.add(tag)
            db.flush()
        tags.append(tag)
    record.tags = tags


def remove_orphan_tags(db: Session) -> None:
    used = select(record_tags.c.tag_id)
    db.execute(delete(Tag).where(Tag.id.not_in(used)))


def apply_payload(db: Session, record: MedicalRecord, payload: RecordIn) -> None:
    """Copy a validated payload onto a record (creating or replacing children and tags)."""
    doctor = None
    if payload.doctor_id:
        doctor = db.get(Doctor, payload.doctor_id)
        if doctor is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Selected doctor does not exist")
    if payload.lab_id and db.get(Lab, payload.lab_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Selected laboratory does not exist")

    record.record_type = payload.record_type.value
    record.record_date = payload.record_date
    record.doctor_id = payload.doctor_id
    record.lab_id = payload.lab_id
    for field in SCALAR_FIELDS:
        setattr(record, field, getattr(payload, field))
    record.title = payload.title or _default_title(payload, doctor)

    record.medicines = [
        PrescriptionMedicine(position=index, **medicine.model_dump())
        for index, medicine in enumerate(payload.medicines)
    ]
    record.results = [
        LabResult(position=index, **result.model_dump()) for index, result in enumerate(payload.results)
    ]
    _sync_tags(db, record, payload.tags)


def create_record(db: Session, payload: RecordIn) -> MedicalRecord:
    record = MedicalRecord()
    apply_payload(db, record, payload)
    db.add(record)
    db.flush()
    db.commit()
    return get_record_or_404(db, record.id)


def update_record(db: Session, record: MedicalRecord, payload: RecordIn) -> MedicalRecord:
    apply_payload(db, record, payload)
    db.flush()
    remove_orphan_tags(db)
    db.commit()
    return get_record_or_404(db, record.id)


def delete_record(db: Session, record: MedicalRecord) -> None:
    files = [storage.stored_path(document) for document in record.documents]
    db.delete(record)
    db.flush()
    remove_orphan_tags(db)
    db.commit()
    for path in files:
        storage.remove_file(path)


def to_summary(record: MedicalRecord) -> RecordSummary:
    return RecordSummary(
        id=record.id,
        record_type=RecordType(record.record_type),
        title=record.title,
        record_date=record.record_date,
        doctor_name=record.doctor.name if record.doctor else None,
        lab_name=record.lab.name if record.lab else None,
        hospital=record.hospital,
        tags=sorted((tag.name for tag in record.tags), key=str.lower),
        document_count=len(record.documents),
    )


def to_timeline_item(record: MedicalRecord) -> TimelineItem:
    return TimelineItem(
        id=record.id,
        record_type=RecordType(record.record_type),
        title=record.title,
        record_date=record.record_date,
        doctor_name=record.doctor.name if record.doctor else None,
        lab_name=record.lab.name if record.lab else None,
        document_count=len(record.documents),
    )
