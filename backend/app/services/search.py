"""Record search and filtering."""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Doctor,
    Document,
    Lab,
    LabResult,
    MedicalRecord,
    PrescriptionMedicine,
    Tag,
    record_tags,
)
from app.schemas import RecordType
from app.services.records import LIST_LOAD

MAX_TERMS = 8

TEXT_COLUMNS = (
    MedicalRecord.title,
    MedicalRecord.hospital,
    MedicalRecord.specialization,
    MedicalRecord.reason,
    MedicalRecord.symptoms,
    MedicalRecord.diagnosis,
    MedicalRecord.description,
    MedicalRecord.treatment,
    MedicalRecord.doctor_notes,
    MedicalRecord.summary,
    MedicalRecord.personal_notes,
    MedicalRecord.test_name,
)


@dataclass
class RecordFilters:
    q: str | None = None
    record_types: list[RecordType] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    doctor_id: str | None = None
    lab_id: str | None = None
    sort: Literal["newest", "oldest"] = "newest"


def _term_condition(term: str):
    """One search word must appear in any searchable field of the record (case-insensitive)."""
    conditions = [column.icontains(term, autoescape=True) for column in TEXT_COLUMNS]
    conditions += [
        Doctor.name.icontains(term, autoescape=True),
        Doctor.specialization.icontains(term, autoescape=True),
        Doctor.hospital.icontains(term, autoescape=True),
        Lab.name.icontains(term, autoescape=True),
        exists().where(
            PrescriptionMedicine.record_id == MedicalRecord.id,
            or_(
                PrescriptionMedicine.name.icontains(term, autoescape=True),
                PrescriptionMedicine.instructions.icontains(term, autoescape=True),
            ),
        ),
        exists().where(
            LabResult.record_id == MedicalRecord.id,
            LabResult.parameter.icontains(term, autoescape=True),
        ),
        exists().where(
            record_tags.c.record_id == MedicalRecord.id,
            record_tags.c.tag_id == Tag.id,
            Tag.name.icontains(term, autoescape=True),
        ),
        exists().where(
            Document.record_id == MedicalRecord.id,
            Document.original_filename.icontains(term, autoescape=True),
        ),
    ]
    return or_(*conditions)


def build_query(user_id: str, filters: RecordFilters) -> Select:
    stmt = (
        select(MedicalRecord)
        .outerjoin(Doctor, MedicalRecord.doctor_id == Doctor.id)
        .outerjoin(Lab, MedicalRecord.lab_id == Lab.id)
        .where(MedicalRecord.user_id == user_id)
    )
    if filters.q:
        for term in filters.q.split()[:MAX_TERMS]:
            stmt = stmt.where(_term_condition(term))
    if filters.record_types:
        stmt = stmt.where(MedicalRecord.record_type.in_([t.value for t in filters.record_types]))
    for tag in filters.tags:
        stmt = stmt.where(MedicalRecord.tags.any(Tag.name_key == tag.strip().lower()))
    if filters.date_from:
        stmt = stmt.where(MedicalRecord.record_date >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(MedicalRecord.record_date <= filters.date_to)
    if filters.doctor_id:
        stmt = stmt.where(MedicalRecord.doctor_id == filters.doctor_id)
    if filters.lab_id:
        stmt = stmt.where(MedicalRecord.lab_id == filters.lab_id)
    return stmt


def _ordering(filters: RecordFilters):
    if filters.sort == "oldest":
        return (MedicalRecord.record_date.asc(), MedicalRecord.created_at.asc())
    return (MedicalRecord.record_date.desc(), MedicalRecord.created_at.desc())


def search_records(
    db: Session, user_id: str, filters: RecordFilters, limit: int | None, offset: int = 0
) -> tuple[list[MedicalRecord], int]:
    """The user's records matching the filters (one page of them) and the total number of matches."""
    stmt = build_query(user_id, filters)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    stmt = stmt.options(*LIST_LOAD).order_by(*_ordering(filters)).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all()), total
