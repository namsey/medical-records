"""Pydantic request / response schemas."""

import re
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator, model_validator


class RecordType(str, Enum):
    doctor_visit = "doctor_visit"
    prescription = "prescription"
    lab_report = "lab_report"
    diagnosis = "diagnosis"
    medical_document = "medical_document"
    scan = "scan"
    other = "other"


RECORD_TYPE_LABELS: dict[str, str] = {
    "doctor_visit": "Doctor Visit",
    "prescription": "Prescription",
    "lab_report": "Lab Report",
    "diagnosis": "Diagnosis",
    "medical_document": "Medical Document",
    "scan": "Scan",
    "other": "Other",
}

# Record types where the user must give a title because nothing else identifies the record.
TITLE_REQUIRED_TYPES = {RecordType.medical_document, RecordType.scan, RecordType.other}


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _required_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


# Optional text (blank -> None), with length limits applied to the text itself (not to None).
def _optional_text(max_length: int):
    return Annotated[Annotated[str, StringConstraints(max_length=max_length)] | None, BeforeValidator(_blank_to_none)]


Text32 = _optional_text(32)
Text50 = _optional_text(50)
Text100 = _optional_text(100)
Text255 = _optional_text(255)
LongText = _optional_text(10000)
# Required text.
Required255 = Annotated[str, BeforeValidator(_required_text), Field(min_length=1, max_length=255)]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: Any) -> Any:
    value = _blank_to_none(value)
    if value is not None and (not isinstance(value, str) or not _EMAIL_RE.match(value)):
        raise ValueError("Enter a valid email address")
    return value


EmailText = Annotated[Annotated[str, StringConstraints(max_length=320)] | None, BeforeValidator(_validate_email)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- doctors / labs


class DoctorIn(BaseModel):
    name: Required255
    specialization: Text255 = None
    hospital: Text255 = None
    phone: Text50 = None
    email: EmailText = None
    address: LongText = None
    notes: LongText = None


class DoctorOut(ORMModel):
    id: str
    name: str
    specialization: str | None
    hospital: str | None
    phone: str | None
    email: str | None
    address: str | None
    notes: str | None
    record_count: int = 0


class LabIn(BaseModel):
    name: Required255
    address: LongText = None
    phone: Text50 = None
    notes: LongText = None


class LabOut(ORMModel):
    id: str
    name: str
    address: str | None
    phone: str | None
    notes: str | None
    record_count: int = 0


# --------------------------------------------------------------------------- records


class MedicineIn(BaseModel):
    name: Required255
    dosage: Text255 = None
    frequency: Text255 = None
    duration: Text255 = None
    start_date: date | None = None
    end_date: date | None = None
    instructions: LongText = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> "MedicineIn":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Medicine end date cannot be before its start date")
        return self


class MedicineOut(ORMModel):
    id: str
    name: str
    dosage: str | None
    frequency: str | None
    duration: str | None
    start_date: date | None
    end_date: date | None
    instructions: str | None


class LabResultIn(BaseModel):
    parameter: Required255
    value: Text100 = None
    unit: Text50 = None
    reference_range: Text100 = None
    flag: Text32 = None


class LabResultOut(ORMModel):
    id: str
    parameter: str
    value: str | None
    unit: str | None
    reference_range: str | None
    flag: str | None


MAX_TAGS = 20
MAX_TAG_LENGTH = 50


def normalize_tags(raw: list[str]) -> list[str]:
    """Trim, collapse whitespace, drop blanks and case-insensitive duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        name = " ".join(str(item).split())
        if not name:
            continue
        if len(name) > MAX_TAG_LENGTH:
            raise ValueError(f"Tags can be at most {MAX_TAG_LENGTH} characters")
        key = name.lower()
        if key not in seen:
            seen.add(key)
            result.append(name)
    if len(result) > MAX_TAGS:
        raise ValueError(f"A record can have at most {MAX_TAGS} tags")
    return result


class RecordIn(BaseModel):
    record_type: RecordType
    title: Text255 = None
    record_date: date
    doctor_id: str | None = None
    lab_id: str | None = None
    hospital: Text255 = None
    specialization: Text255 = None
    reason: LongText = None
    symptoms: LongText = None
    diagnosis: LongText = None
    description: LongText = None
    treatment: LongText = None
    doctor_notes: LongText = None
    summary: LongText = None
    personal_notes: LongText = None
    test_name: Text255 = None
    follow_up_date: date | None = None
    report_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    medicines: list[MedicineIn] = Field(default_factory=list, max_length=100)
    results: list[LabResultIn] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def _check_type_rules(self) -> "RecordIn":
        self.tags = normalize_tags(self.tags)
        if self.medicines and self.record_type != RecordType.prescription:
            raise ValueError("Medicines can only be added to a prescription")
        if self.results and self.record_type != RecordType.lab_report:
            raise ValueError("Test results can only be added to a lab report")
        if self.lab_id and self.record_type != RecordType.lab_report:
            raise ValueError("A laboratory can only be set on a lab report")
        if self.record_type in TITLE_REQUIRED_TYPES and not self.title:
            raise ValueError("A title is required for this record type")
        if self.record_type == RecordType.lab_report and not self.test_name:
            raise ValueError("Test name is required for a lab report")
        if self.record_type == RecordType.diagnosis and not self.diagnosis:
            raise ValueError("Diagnosis is required")
        return self


class DocumentOut(ORMModel):
    id: str
    record_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class RecordOut(ORMModel):
    id: str
    record_type: RecordType
    title: str
    record_date: date
    doctor_id: str | None
    lab_id: str | None
    doctor: DoctorOut | None
    lab: LabOut | None
    hospital: str | None
    specialization: str | None
    reason: str | None
    symptoms: str | None
    diagnosis: str | None
    description: str | None
    treatment: str | None
    doctor_notes: str | None
    summary: str | None
    personal_notes: str | None
    test_name: str | None
    follow_up_date: date | None
    report_date: date | None
    tags: list[str]
    medicines: list[MedicineOut]
    results: list[LabResultOut]
    documents: list[DocumentOut]
    created_at: datetime
    updated_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def _tag_names(cls, value: Any) -> Any:
        # The ORM relationship yields Tag objects; the API exposes plain names.
        return sorted((getattr(tag, "name", tag) for tag in value), key=str.lower)


class RecordSummary(BaseModel):
    id: str
    record_type: RecordType
    title: str
    record_date: date
    doctor_name: str | None
    lab_name: str | None
    hospital: str | None
    tags: list[str]
    document_count: int


class RecordPage(BaseModel):
    items: list[RecordSummary]
    total: int
    limit: int
    offset: int


class TagOut(BaseModel):
    name: str
    record_count: int


class YearCount(BaseModel):
    year: int
    record_count: int


class TimelineItem(BaseModel):
    id: str
    record_type: RecordType
    title: str
    record_date: date
    doctor_name: str | None
    lab_name: str | None
    document_count: int


class UserOut(BaseModel):
    email: str
    name: str | None
