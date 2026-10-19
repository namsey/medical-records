"""Database models."""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Stores naive UTC in SQLite and always returns timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # type: ignore[no-untyped-def]
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


record_tags = Table(
    "record_tags",
    Base.metadata,
    Column("record_id", String(36), ForeignKey("medical_records.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_record_tags_tag_id", "tag_id"),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")  # "admin" or "user"
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    disabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    quota_bytes: Mapped[int | None] = mapped_column(Integer)  # None: DEFAULT_QUOTA_MB
    consent_version: Mapped[str | None] = mapped_column(String(32))  # privacy notice version agreed to
    consented_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuditEvent(Base):
    """Who did what to which account, and when. Never record contents, file names or IP addresses.

    Emails are copied in, so an entry still says who it was about after that account is deleted (kept 1 year).
    """

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    action: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[str | None] = mapped_column(String(320))
    target_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_email: Mapped[str | None] = mapped_column(String(320))
    detail: Mapped[str | None] = mapped_column(String(100))  # a reason code or a setting, never personal content


class Invite(Base):
    """A single-use invite for one email address. `token_hash` is an HMAC of the link's secret, never the secret."""

    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    used_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class UserSession(Base):
    """Server-side login session. `id` is an HMAC of the random cookie token, never the token itself."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)

    user: Mapped[User] = relationship()


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    specialization: Mapped[str | None] = mapped_column(String(255))
    hospital: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name_key", name="uq_tags_user_id_name_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64))
    name_key: Mapped[str] = mapped_column(String(64))  # lower-cased name; unique per user, case-insensitive


class MedicalRecord(Base):
    """One medical record, owned by one user. Which columns are used depends on `record_type`."""

    __tablename__ = "medical_records"
    __table_args__ = (
        Index("ix_medical_records_date", "record_date", "created_at"),
        Index("ix_medical_records_type", "record_type"),
        Index("ix_medical_records_user_date", "user_id", "record_date", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    record_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    record_date: Mapped[date] = mapped_column(Date)
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.id", ondelete="RESTRICT"), index=True)
    lab_id: Mapped[str | None] = mapped_column(ForeignKey("labs.id", ondelete="RESTRICT"), index=True)
    hospital: Mapped[str | None] = mapped_column(String(255))
    specialization: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    symptoms: Mapped[str | None] = mapped_column(Text)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    treatment: Mapped[str | None] = mapped_column(Text)
    doctor_notes: Mapped[str | None] = mapped_column(Text)  # visit notes / prescription instructions
    summary: Mapped[str | None] = mapped_column(Text)
    personal_notes: Mapped[str | None] = mapped_column(Text)
    test_name: Mapped[str | None] = mapped_column(String(255))
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    doctor: Mapped[Doctor | None] = relationship()
    lab: Mapped[Lab | None] = relationship()
    medicines: Mapped[list["PrescriptionMedicine"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="PrescriptionMedicine.position",
    )
    results: Mapped[list["LabResult"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="LabResult.position",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="Document.created_at",
    )
    tags: Mapped[list[Tag]] = relationship(secondary=record_tags, order_by="Tag.name")


class PrescriptionMedicine(Base):
    __tablename__ = "prescription_medicines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    record_id: Mapped[str] = mapped_column(ForeignKey("medical_records.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(255))
    dosage: Mapped[str | None] = mapped_column(String(255))
    frequency: Mapped[str | None] = mapped_column(String(255))
    duration: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    instructions: Mapped[str | None] = mapped_column(Text)

    record: Mapped[MedicalRecord] = relationship(back_populates="medicines")


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    record_id: Mapped[str] = mapped_column(ForeignKey("medical_records.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    parameter: Mapped[str] = mapped_column(String(255))
    value: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str | None] = mapped_column(String(50))
    reference_range: Mapped[str | None] = mapped_column(String(100))
    flag: Mapped[str | None] = mapped_column(String(32))

    record: Mapped[MedicalRecord] = relationship(back_populates="results")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    record_id: Mapped[str] = mapped_column(ForeignKey("medical_records.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(64), unique=True)
    # Type folder under the old UPLOAD_DIR layout; "" once the file lives under FILES_DIR/<user_id>/.
    storage_folder: Mapped[str] = mapped_column(String(32), default="")
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    record: Mapped[MedicalRecord] = relationship(back_populates="documents")
