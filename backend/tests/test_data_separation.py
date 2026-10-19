"""Two signed-in users: neither can see, change or download the other's data, by ID, search, list or file URL.

Every test runs both ways round. "Victim" owns the data; "intruder" tries to reach it.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest

from app.config import get_settings
from tests.conftest import PDF_BYTES

MISSING_ID = "00000000-0000-4000-8000-000000000000"
# A word that only the victim's data contains, in every searchable place.
SECRET = "Zebrafinch"


@pytest.fixture(params=["owner-is-victim", "second-is-victim"])
def users(request, client, second_client):
    """(victim, intruder) clients."""
    return (client, second_client) if request.param == "owner-is-victim" else (second_client, client)


@pytest.fixture
def victim_data(users):
    victim, _ = users
    doctor = victim.post("/api/doctors", json={"name": f"Dr. {SECRET}", "hospital": f"{SECRET} Hospital"}).json()
    lab = victim.post("/api/labs", json={"name": f"{SECRET} Lab"}).json()

    def create(payload):
        response = victim.post("/api/records", json={"record_date": "2024-06-01", **payload})
        assert response.status_code == 201, response.text
        return response.json()

    prescription = create(
        {
            "record_type": "prescription",
            "title": f"{SECRET} prescription",
            "doctor_id": doctor["id"],
            "medicines": [{"name": f"{SECRET}mycin"}],
            "tags": [f"{SECRET}Tag"],
        }
    )
    lab_report = create(
        {
            "record_type": "lab_report",
            "test_name": "Panel",
            "lab_id": lab["id"],
            "results": [{"parameter": f"{SECRET} level", "value": "1"}],
            "personal_notes": f"{SECRET} notes",
        }
    )
    upload = victim.post(
        f"/api/records/{lab_report['id']}/documents",
        files={"files": (f"{SECRET}.pdf", PDF_BYTES, "application/pdf")},
    )
    assert upload.status_code == 201
    return {
        "doctor": doctor,
        "lab": lab,
        "records": [prescription, lab_report],
        "document": upload.json()[0],
        "snapshot": _snapshot(victim),
    }


def _snapshot(client) -> dict:
    """Everything the user can see, to check that nothing changed."""
    return {
        "records": client.get("/api/records").json(),
        "doctors": client.get("/api/doctors").json(),
        "labs": client.get("/api/labs").json(),
        "tags": client.get("/api/tags").json(),
    }


def _same_as_missing(intruder, method: str, path: str, real_id: str, **kwargs) -> None:
    """Someone else's ID answers exactly like an ID that does not exist: 404, same body."""
    response = getattr(intruder, method)(path.format(id=real_id), **kwargs)
    missing = getattr(intruder, method)(path.format(id=MISSING_ID), **kwargs)
    assert response.status_code == 404, (method, path, response.status_code)
    assert (response.status_code, response.json()) == (missing.status_code, missing.json()), (method, path)


def _all_stored_files() -> list[Path]:
    return [p for p in get_settings().files_path.rglob("*") if p.is_file()]


def test_records_by_id(users, victim_data):
    victim, intruder = users
    edit = {"record_type": "other", "title": "Hijacked", "record_date": "2024-06-01"}
    for record in victim_data["records"]:
        _same_as_missing(intruder, "get", "/api/records/{id}", record["id"])
        _same_as_missing(intruder, "put", "/api/records/{id}", record["id"], json=edit)
        _same_as_missing(intruder, "delete", "/api/records/{id}", record["id"])
    assert _snapshot(victim) == victim_data["snapshot"]


def test_upload_to_someone_elses_record(users, victim_data):
    victim, intruder = users
    before = _all_stored_files()
    _same_as_missing(
        intruder,
        "post",
        "/api/records/{id}/documents",
        victim_data["records"][0]["id"],
        files={"files": ("x.pdf", PDF_BYTES, "application/pdf")},
    )
    assert _all_stored_files() == before
    assert _snapshot(victim) == victim_data["snapshot"]


def test_documents_by_id(users, victim_data):
    victim, intruder = users
    document_id = victim_data["document"]["id"]
    for path in ("/api/documents/{id}", "/api/documents/{id}/view", "/api/documents/{id}/download"):
        _same_as_missing(intruder, "get", path, document_id)
    _same_as_missing(intruder, "delete", "/api/documents/{id}", document_id)
    download = victim.get(f"/api/documents/{document_id}/download")
    assert download.status_code == 200 and download.content == PDF_BYTES


def test_doctors_and_labs_by_id(users, victim_data):
    victim, intruder = users
    for kind, item in (("doctors", victim_data["doctor"]), ("labs", victim_data["lab"])):
        _same_as_missing(intruder, "get", f"/api/{kind}/{{id}}", item["id"])
        _same_as_missing(intruder, "put", f"/api/{kind}/{{id}}", item["id"], json={"name": "Hijacked"})
        _same_as_missing(intruder, "delete", f"/api/{kind}/{{id}}", item["id"])
    assert _snapshot(victim) == victim_data["snapshot"]


def test_cannot_link_someone_elses_doctor_or_lab(users, victim_data):
    victim, intruder = users
    own = intruder.post("/api/records", json={"record_type": "doctor_visit", "record_date": "2024-06-01"}).json()
    for payload, real_id in (
        ({"record_type": "doctor_visit"}, {"doctor_id": victim_data["doctor"]["id"]}),
        ({"record_type": "lab_report", "test_name": "T"}, {"lab_id": victim_data["lab"]["id"]}),
    ):
        missing_id = {key: MISSING_ID for key in real_id}
        for method, path in (("post", "/api/records"), ("put", f"/api/records/{own['id']}")):
            body = {"record_date": "2024-06-01", **payload}
            response = getattr(intruder, method)(path, json={**body, **real_id})
            missing = getattr(intruder, method)(path, json={**body, **missing_id})
            assert response.status_code == 422
            assert response.json() == missing.json()
    assert _snapshot(victim) == victim_data["snapshot"]


def test_search_and_lists_show_nothing_of_the_other_user(users, victim_data):
    _, intruder = users
    doctor_id, lab_id = victim_data["doctor"]["id"], victim_data["lab"]["id"]
    queries = [
        "/api/records",
        "/api/timeline",
        "/api/years",
        "/api/tags",
        "/api/doctors",
        "/api/labs",
        f"/api/doctors?q={SECRET}",
        f"/api/labs?q={SECRET}",
        f"/api/search?q={SECRET}",
        f"/api/search?q={SECRET}mycin",
        f"/api/search?q={SECRET}%20level",
        f"/api/search?q={SECRET}.pdf",
        f"/api/search?tag={SECRET}Tag",
        f"/api/search?doctor_id={doctor_id}",
        f"/api/search?lab_id={lab_id}",
        f"/api/timeline?doctor_id={doctor_id}",
        f"/api/timeline?q={SECRET}",
    ]
    for path in queries:
        response = intruder.get(path)
        assert response.status_code == 200, path
        assert SECRET not in response.text, path
        body = response.json()
        if isinstance(body, dict):  # a page of records
            assert body["total"] == 0 and body["items"] == [], path
        else:
            assert body == [], path


def test_backup_and_export_hold_nothing_of_the_other_user(users, victim_data):
    _, intruder = users
    export = intruder.get("/api/export/json")
    assert SECRET not in export.text
    assert json.loads(export.content)["counts"] == {"records": 0, "doctors": 0, "laboratories": 0, "tags": 0}

    archive = zipfile.ZipFile(io.BytesIO(intruder.get("/api/backup").content))
    assert [n for n in archive.namelist() if n.startswith("files/")] == []
    assert SECRET.encode() not in archive.read("database/medical_records.db")


def test_direct_file_urls_never_serve_the_file(users, victim_data):
    _, intruder = users
    (stored,) = _all_stored_files()
    owner_folder, name = stored.parent.name, stored.name
    for path in (
        f"/files/{owner_folder}/{name}",
        f"/data/files/{owner_folder}/{name}",
        f"/{owner_folder}/{name}",
        f"/{name}",
        f"/api/files/{owner_folder}/{name}",
        f"/api/documents/{name}/view",
        f"/api/documents/{stored.stem}/download",
    ):
        response = intruder.get(path)
        assert PDF_BYTES not in response.content, path
