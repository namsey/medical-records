import pytest

from tests.conftest import record_payload


def test_create_doctor_visit(client):
    doctor = client.post("/api/doctors", json={"name": "Dr. Rao", "specialization": "Cardiology"}).json()
    response = client.post(
        "/api/records",
        json=record_payload(
            doctor_id=doctor["id"],
            hospital="City Hospital",
            reason="Chest pain",
            symptoms="Tightness",
            diagnosis="Stress",
            doctor_notes="Rest",
            follow_up_date="2026-10-05",
            personal_notes="Felt fine after",
            tags=["Heart", "heart", " General "],
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["record_type"] == "doctor_visit"
    assert body["doctor"]["name"] == "Dr. Rao"
    assert body["title"] == "Doctor Visit - Dr. Rao"
    assert body["tags"] == ["General", "Heart"]  # de-duplicated case-insensitively, sorted by name
    assert body["follow_up_date"] == "2026-10-05"
    assert body["documents"] == []


def test_create_prescription_with_multiple_medicines(client):
    response = client.post(
        "/api/records",
        json=record_payload(
            record_type="prescription",
            reason="Fever",
            doctor_notes="Drink water",
            medicines=[
                {"name": "Paracetamol", "dosage": "500 mg", "frequency": "twice daily", "duration": "5 days",
                 "start_date": "2026-09-05", "end_date": "2026-09-10", "instructions": "After food"},
                {"name": "Vitamin C"},
            ],
        ),
    )
    assert response.status_code == 201
    medicines = response.json()["medicines"]
    assert [m["name"] for m in medicines] == ["Paracetamol", "Vitamin C"]
    assert medicines[0]["dosage"] == "500 mg"
    assert medicines[0]["end_date"] == "2026-09-10"


def test_create_lab_report_with_results(client):
    lab = client.post("/api/labs", json={"name": "Metro Labs"}).json()
    response = client.post(
        "/api/records",
        json=record_payload(
            record_type="lab_report",
            lab_id=lab["id"],
            test_name="Vitamin B12",
            report_date="2026-09-06",
            summary="Within range",
            results=[
                {"parameter": "Vitamin B12", "value": "296", "unit": "pg/mL", "reference_range": "200-900", "flag": "Normal"}
            ],
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["lab"]["name"] == "Metro Labs"
    assert body["report_date"] == "2026-09-06"
    assert body["results"][0] == {
        "id": body["results"][0]["id"],
        "parameter": "Vitamin B12",
        "value": "296",
        "unit": "pg/mL",
        "reference_range": "200-900",
        "flag": "Normal",
    }
    assert body["title"] == "Lab Report - Vitamin B12"


@pytest.mark.parametrize("record_type", ["diagnosis", "medical_document", "scan", "other"])
def test_other_record_types(client, record_type):
    payload = record_payload(record_type=record_type, title="Thing", diagnosis="Gastritis", description="d")
    response = client.post("/api/records", json=payload)
    assert response.status_code == 201
    assert response.json()["record_type"] == record_type


@pytest.mark.parametrize(
    "payload",
    [
        {"record_type": "bogus", "record_date": "2026-01-01"},
        {"record_type": "doctor_visit"},  # no date
        {"record_type": "doctor_visit", "record_date": "not-a-date"},
        {"record_type": "scan", "record_date": "2026-01-01"},  # title required
        {"record_type": "lab_report", "record_date": "2026-01-01"},  # test name required
        {"record_type": "diagnosis", "record_date": "2026-01-01"},  # diagnosis required
        {"record_type": "doctor_visit", "record_date": "2026-01-01", "medicines": [{"name": "X"}]},
        {"record_type": "doctor_visit", "record_date": "2026-01-01", "results": [{"parameter": "X"}]},
        {"record_type": "prescription", "record_date": "2026-01-01", "medicines": [{"name": " "}]},
        {"record_type": "prescription", "record_date": "2026-01-01",
         "medicines": [{"name": "X", "start_date": "2026-02-01", "end_date": "2026-01-01"}]},
        {"record_type": "doctor_visit", "record_date": "2026-01-01", "tags": ["x" * 80]},
        {"record_type": "doctor_visit", "record_date": "2026-01-01", "title": "x" * 300},
    ],
)
def test_validation_errors(client, payload):
    assert client.post("/api/records", json=payload).status_code == 422


def test_unknown_doctor_or_lab_is_rejected(client):
    assert client.post("/api/records", json=record_payload(doctor_id="nope")).status_code == 422
    payload = record_payload(record_type="lab_report", test_name="CBC", lab_id="nope")
    assert client.post("/api/records", json=payload).status_code == 422


def test_blank_strings_are_stored_as_null(client, make_record):
    record = make_record(reason="   ", hospital="")
    assert record["reason"] is None and record["hospital"] is None


def test_get_update_delete_record(client, make_record):
    record = make_record(reason="Cough", tags=["Old"])
    fetched = client.get(f"/api/records/{record['id']}").json()
    assert fetched["reason"] == "Cough"

    updated = client.put(
        f"/api/records/{record['id']}",
        json=record_payload(reason="Cold", tags=["New"], record_date="2026-09-07", title="Renamed"),
    )
    assert updated.status_code == 200
    body = updated.json()
    assert (body["reason"], body["tags"], body["record_date"], body["title"]) == ("Cold", ["New"], "2026-09-07", "Renamed")

    # Tag "Old" is no longer used by any record and disappears from the tag list.
    assert [t["name"] for t in client.get("/api/tags").json()] == ["New"]

    assert client.delete(f"/api/records/{record['id']}").status_code == 204
    assert client.get(f"/api/records/{record['id']}").status_code == 404
    assert client.get("/api/tags").json() == []


def test_update_replaces_medicines(client, make_record):
    record = make_record(
        record_type="prescription", medicines=[{"name": "A"}, {"name": "B"}]
    )
    updated = client.put(
        f"/api/records/{record['id']}",
        json=record_payload(record_type="prescription", medicines=[{"name": "C"}]),
    ).json()
    assert [m["name"] for m in updated["medicines"]] == ["C"]


def test_missing_record_returns_404(client):
    assert client.get("/api/records/does-not-exist").status_code == 404
    assert client.put("/api/records/does-not-exist", json=record_payload()).status_code == 404
    assert client.delete("/api/records/does-not-exist").status_code == 404


def test_tags_endpoint_counts(client, make_record):
    make_record(tags=["Blood", "B12"])
    make_record(tags=["blood"])
    tags = {t["name"]: t["record_count"] for t in client.get("/api/tags").json()}
    assert tags == {"B12": 1, "Blood": 2}


# --------------------------------------------------------------------------- directories


def test_doctor_crud(client):
    created = client.post(
        "/api/doctors",
        json={"name": "Dr. Mehta", "specialization": "ENT", "hospital": "Apollo", "phone": "123",
              "email": "mehta@example.com", "address": "Street 1", "notes": "Good"},
    )
    assert created.status_code == 201
    doctor_id = created.json()["id"]
    assert client.get(f"/api/doctors/{doctor_id}").json()["email"] == "mehta@example.com"
    updated = client.put(f"/api/doctors/{doctor_id}", json={"name": "Dr. A. Mehta"})
    assert updated.json()["name"] == "Dr. A. Mehta"
    assert updated.json()["specialization"] is None  # PUT replaces the whole doctor
    assert [d["name"] for d in client.get("/api/doctors?q=mehta").json()] == ["Dr. A. Mehta"]
    assert client.get("/api/doctors?q=zzz").json() == []
    assert client.delete(f"/api/doctors/{doctor_id}").status_code == 204
    assert client.get(f"/api/doctors/{doctor_id}").status_code == 404


def test_doctor_validation(client):
    assert client.post("/api/doctors", json={"name": ""}).status_code == 422
    assert client.post("/api/doctors", json={"name": "X", "email": "not-an-email"}).status_code == 422


def test_doctor_in_use_cannot_be_deleted(client, make_record):
    doctor = client.post("/api/doctors", json={"name": "Dr. Used"}).json()
    make_record(doctor_id=doctor["id"])
    response = client.delete(f"/api/doctors/{doctor['id']}")
    assert response.status_code == 409
    assert "1 record" in response.json()["detail"]
    assert client.get("/api/doctors").json()[0]["record_count"] == 1


def test_lab_crud_and_in_use_protection(client, make_record):
    lab = client.post("/api/labs", json={"name": "Lab One", "address": "Road", "phone": "9"}).json()
    assert client.put(f"/api/labs/{lab['id']}", json={"name": "Lab Uno"}).json()["name"] == "Lab Uno"
    make_record(record_type="lab_report", test_name="CBC", lab_id=lab["id"])
    assert client.delete(f"/api/labs/{lab['id']}").status_code == 409
    assert client.get("/api/labs").json()[0]["record_count"] == 1
    assert client.post("/api/labs", json={"name": ""}).status_code == 422


def test_lab_only_allowed_on_lab_reports(client):
    lab = client.post("/api/labs", json={"name": "Lab"}).json()
    assert client.post("/api/records", json=record_payload(lab_id=lab["id"])).status_code == 422


def test_app_config_exposes_upload_limit(client, anon):
    assert client.get("/api/config").json()["max_upload_mb"] == 20
    assert anon.get("/api/config").status_code == 401
