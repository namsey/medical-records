"""RecordStore: rows are written with their owner, and a store only sees its own user's rows.

(The full HTTP-level isolation tests between two signed-in users come with #39.)
"""

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Doctor, Lab, MedicalRecord, Tag, User
from app.schemas import RecordIn
from app.services.record_store import SqlRecordStore
from app.services.search import RecordFilters
from tests.conftest import PDF_BYTES


def _owner_id() -> str:
    with SessionLocal() as db:
        return db.query(User).filter_by(email="owner@example.com").one().id


def _other_store(db) -> SqlRecordStore:
    other = User(email="other@example.com")
    db.add(other)
    db.commit()
    return SqlRecordStore(db, other.id)


def test_new_rows_belong_to_the_signed_in_user(client, make_record):
    doctor = client.post("/api/doctors", json={"name": "Dr. Rao"}).json()
    lab = client.post("/api/labs", json={"name": "City Lab"}).json()
    record = make_record(doctor_id=doctor["id"], tags=["Thyroid"])
    owner = _owner_id()
    with SessionLocal() as db:
        assert db.get(MedicalRecord, record["id"]).user_id == owner
        assert db.get(Doctor, doctor["id"]).user_id == owner
        assert db.get(Lab, lab["id"]).user_id == owner
        assert db.query(Tag).one().user_id == owner


def test_another_users_store_sees_nothing(client, make_record):
    doctor = client.post("/api/doctors", json={"name": "Dr. Rao"}).json()
    lab = client.post("/api/labs", json={"name": "City Lab"}).json()
    record = make_record(doctor_id=doctor["id"], tags=["Thyroid"])
    document = client.post(
        f"/api/records/{record['id']}/documents", files={"files": ("a.pdf", PDF_BYTES, "application/pdf")}
    ).json()[0]

    with SessionLocal() as db:
        other = _other_store(db)
        assert other.search(RecordFilters(), limit=None) == ([], 0)
        assert other.years() == []
        assert other.tags() == []
        assert other.list_doctors(None) == []
        assert other.list_labs(None) == []
        assert other.storage_used_bytes() == 0
        for lookup in (
            lambda: other.get(record["id"]),
            lambda: other.get_document(document["id"]),
            lambda: other.get_doctor(doctor["id"]),
            lambda: other.get_lab(lab["id"]),
        ):
            with pytest.raises(HTTPException) as error:
                lookup()
            assert error.value.status_code == 404


def test_cannot_link_another_users_doctor_or_lab(client):
    doctor = client.post("/api/doctors", json={"name": "Dr. Rao"}).json()
    lab = client.post("/api/labs", json={"name": "City Lab"}).json()
    with SessionLocal() as db:
        other = _other_store(db)
        for link in (
            {"record_type": "doctor_visit", "doctor_id": doctor["id"]},
            {"record_type": "lab_report", "test_name": "TSH", "lab_id": lab["id"]},
        ):
            payload = RecordIn.model_validate({"record_date": "2026-09-05", **link})
            with pytest.raises(HTTPException) as error:
                other.create(payload)
            assert error.value.status_code == 422


def test_tags_with_the_same_name_stay_separate_per_user(client, make_record):
    make_record(tags=["Thyroid"])
    with SessionLocal() as db:
        other = _other_store(db)
        other.create(RecordIn.model_validate({"record_type": "doctor_visit", "record_date": "2026-09-05", "tags": ["thyroid"]}))
        assert other.tags() == [("thyroid", 1)]
    assert client.get("/api/tags").json() == [{"name": "Thyroid", "record_count": 1}]


def test_storage_used_counts_the_users_files(client, make_record):
    record = make_record()
    client.post(f"/api/records/{record['id']}/documents", files={"files": ("a.pdf", PDF_BYTES, "application/pdf")})
    client.post(f"/api/records/{record['id']}/documents", files={"files": ("b.pdf", PDF_BYTES, "application/pdf")})
    with SessionLocal() as db:
        assert SqlRecordStore(db, _owner_id()).storage_used_bytes() == 2 * len(PDF_BYTES)
