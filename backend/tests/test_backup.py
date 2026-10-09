import io
import json
import re
import sqlite3
import zipfile

from tests.conftest import PDF_BYTES, PNG_BYTES


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
    uploads = [n for n in names if n.startswith("uploads/")]
    assert len(uploads) == 2
    assert {archive.read(n) for n in uploads} == {PDF_BYTES, PNG_BYTES}

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
    import glob
    import tempfile

    before = set(glob.glob(f"{tempfile.gettempdir()}/medical-backup-*"))
    client.get("/api/backup")
    after = set(glob.glob(f"{tempfile.gettempdir()}/medical-backup-*"))
    assert after <= before


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
