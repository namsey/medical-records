import asyncio
import io
import json
import re
import sqlite3
import zipfile

from starlette.datastructures import UploadFile

from app.database import SessionLocal
from app.models import User
from app.schemas import RecordIn
from app.services import audit
from app.services.backup import scratch_dir
from app.services.record_store import SqlRecordStore
from tests.conftest import PDF_BYTES, PNG_BYTES

OTHER_PDF = b"%PDF-1.4\nanother user's file\n%%EOF\n"


def _seed(client, make_record):
    doctor = client.post("/api/doctors", json={"name": "Dr. Backup"}).json()
    record = make_record(doctor_id=doctor["id"], reason="Checkup", tags=["General"])
    client.post(f"/api/records/{record['id']}/documents", files={"files": ("a.pdf", PDF_BYTES, "application/pdf")})
    client.post(f"/api/records/{record['id']}/documents", files={"files": ("b.png", PNG_BYTES, "image/png")})
    return record


def test_backup_zip_contains_database_and_files(client, make_record, tmp_path):
    _seed(client, make_record)
    response = client.get("/api/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    disposition = response.headers["content-disposition"]
    assert re.search(r'filename="medical-records-backup-\d{4}-\d{2}-\d{2}\.zip"', disposition)

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert "database/medical_records.db" in names
    assert "backup_info.json" in names
    files = [n for n in names if n.startswith("files/")]
    assert len(files) == 2
    assert {archive.read(n) for n in files} == {PDF_BYTES, PNG_BYTES}

    database = tmp_path / "restored.db"
    database.write_bytes(archive.read("database/medical_records.db"))
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("select count(*) from medical_records").fetchone()[0] == 1
        assert connection.execute("select count(*) from documents").fetchone()[0] == 2
        assert connection.execute("select count(*) from doctors").fetchone()[0] == 1
        # Login sessions never leave the server.
        assert connection.execute("select count(*) from sessions").fetchone()[0] == 0
    finally:
        connection.close()

    manifest = json.loads(archive.read("backup_info.json"))
    assert manifest["uploaded_files"] == 2


def test_backup_leaves_no_temp_files_behind(client, make_record):
    _seed(client, make_record)
    assert client.get("/api/backup").status_code == 200
    assert list(scratch_dir().iterdir()) == []


def test_backup_of_empty_database(client):
    response = client.get("/api/backup")
    assert response.status_code == 200
    assert "database/medical_records.db" in zipfile.ZipFile(io.BytesIO(response.content)).namelist()


def test_json_export(client, make_record):
    record = _seed(client, make_record)
    response = client.get("/api/export/json")
    assert response.status_code == 200
    assert re.search(r"medical-records-export-\d{4}-\d{2}-\d{2}\.json", response.headers["content-disposition"])
    data = json.loads(response.content)
    assert data["counts"]["records"] == 1
    assert data["doctors"][0]["name"] == "Dr. Backup"
    exported = data["records"][0]
    assert exported["id"] == record["id"]
    assert exported["tags"] == ["General"]
    assert exported["reason"] == "Checkup"
    assert [d["original_filename"] for d in exported["documents"]] == ["a.pdf", "b.png"]
    assert "stored_filename" not in exported["documents"][0]


def test_json_export_includes_prescription_and_lab_details(client, make_record):
    make_record(record_type="prescription", medicines=[{"name": "Paracetamol", "dosage": "500 mg"}])
    make_record(
        record_type="lab_report",
        test_name="B12",
        results=[{"parameter": "B12", "value": "296", "unit": "pg/mL", "reference_range": "200-900", "flag": "Normal"}],
    )
    records = json.loads(client.get("/api/export/json").content)["records"]
    by_type = {r["record_type"]: r for r in records}
    assert by_type["prescription"]["medicines"][0]["name"] == "Paracetamol"
    assert by_type["lab_report"]["results"][0]["flag"] == "Normal"


def _seed_other_user() -> None:
    """Another user's doctor, lab, tagged record and file, written straight through their own store."""
    with SessionLocal() as db:
        other = User(email="other@example.com")
        db.add(other)
        db.commit()
        store = SqlRecordStore(db, other.id)
        doctor = store.create_doctor({"name": "Dr. OtherSecret"})
        store.create_lab({"name": "OtherSecret Lab"})
        record = store.create(
            RecordIn.model_validate(
                {
                    "record_type": "doctor_visit",
                    "record_date": "2026-09-05",
                    "doctor_id": doctor.id,
                    "reason": "OtherSecret reason",
                    "tags": ["OtherSecretTag"],
                }
            )
        )
        upload = UploadFile(file=io.BytesIO(OTHER_PDF), filename="other.pdf")
        asyncio.run(store.add_documents(record, [upload]))


def test_backup_holds_only_the_signed_in_users_data(client, make_record, tmp_path):
    _seed(client, make_record)
    _seed_other_user()
    # Server-wide metadata about other people: a pending invite, and audit entries naming another account.
    assert client.post("/api/admin/invites", json={"email": "pending@example.com"}).status_code == 201
    with SessionLocal() as db:
        other = db.query(User).filter_by(email="other@example.com").one()
        audit.record(db, "account_disabled", target=other)

    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/backup").content))
    files = [n for n in archive.namelist() if n.startswith("files/")]
    assert {archive.read(n) for n in files} == {PDF_BYTES, PNG_BYTES}
    assert json.loads(archive.read("backup_info.json"))["uploaded_files"] == 2

    raw = archive.read("database/medical_records.db")
    assert b"OtherSecret" not in raw  # not even in free pages
    assert b"other@example.com" not in raw
    assert b"pending@example.com" not in raw
    database = tmp_path / "restored.db"
    database.write_bytes(raw)
    connection = sqlite3.connect(database)
    try:
        for table, expected in (("users", 1), ("medical_records", 1), ("doctors", 1), ("labs", 0), ("tags", 1),
                                ("documents", 2), ("record_tags", 1)):
            assert connection.execute(f"select count(*) from {table}").fetchone()[0] == expected, table
        assert connection.execute("select email from users").fetchone()[0] == "owner@example.com"
        assert connection.execute("pragma foreign_key_check").fetchall() == []
        # Only the account's own tables keep rows: no sessions, invites or audit log.
        for table in ("sessions", "invites", "audit_events"):
            assert connection.execute(f"select count(*) from {table}").fetchone()[0] == 0, table
    finally:
        connection.close()


def test_json_export_holds_only_the_signed_in_users_data(client, make_record):
    _seed(client, make_record)
    _seed_other_user()
    response = client.get("/api/export/json")
    assert b"OtherSecret" not in response.content
    data = json.loads(response.content)
    assert data["counts"] == {"records": 1, "doctors": 1, "laboratories": 0, "tags": 1}
