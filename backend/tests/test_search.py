import pytest

from tests.conftest import record_payload


@pytest.fixture
def seeded(client):
    doctor = client.post(
        "/api/doctors", json={"name": "Dr. Anita Sharma", "specialization": "Endocrinology", "hospital": "Sunrise Clinic"}
    ).json()
    lab = client.post("/api/labs", json={"name": "Pathcare Diagnostics"}).json()

    def post(**kwargs):
        response = client.post("/api/records", json=record_payload(**kwargs))
        assert response.status_code == 201, response.text
        return response.json()

    return {
        "visit": post(record_type="doctor_visit", record_date="2026-09-05", doctor_id=doctor["id"],
                      hospital="Sunrise Clinic", diagnosis="Hypothyroidism", personal_notes="Felt tired",
                      tags=["Thyroid"]),
        "rx": post(record_type="prescription", record_date="2026-09-05", reason="Thyroid follow up",
                   medicines=[{"name": "Thyronorm"}], tags=["Thyroid", "General"]),
        "lab": post(record_type="lab_report", record_date="2026-09-10", lab_id=lab["id"],
                    test_name="Vitamin B12", description="Fasting sample",
                    results=[{"parameter": "Cobalamin", "value": "296"}], tags=["Blood", "B12"]),
        "scan": post(record_type="scan", record_date="2026-08-20", title="Knee MRI report", tags=["Orthopedic"]),
        "old": post(record_type="other", record_date="2025-01-15", title="Dental checkup", description="100% fine_ok"),
    }


def ids(response):
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def test_default_order_is_newest_first(client, seeded):
    result = ids(client.get("/api/records"))
    assert result[0] == seeded["lab"]["id"]
    assert result[-1] == seeded["old"]["id"]
    oldest = ids(client.get("/api/records?sort=oldest"))
    assert oldest[0] == seeded["old"]["id"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("sharma", ["visit"]),  # doctor name, case-insensitive
        ("SHARMA", ["visit"]),
        ("endocrin", ["visit"]),  # doctor specialization
        ("sunrise", ["visit"]),  # hospital
        ("pathcare", ["lab"]),  # laboratory
        ("hypothyroid", ["visit"]),  # diagnosis
        ("thyronorm", ["rx"]),  # medicine
        ("vitamin b12", ["lab"]),  # test name, multiple words
        ("cobalamin", ["lab"]),  # individual result parameter
        ("knee", ["scan"]),  # title
        ("fasting", ["lab"]),  # description
        ("tired", ["visit"]),  # personal notes
        ("orthopedic", ["scan"]),  # tag
        ("thyroid", ["visit", "rx"]),  # tag + reason + diagnosis
        ("thyroid sunrise", ["visit"]),  # every word must match
        ("nothing-matches-this", []),
    ],
)
def test_search_fields(client, seeded, query, expected):
    found = set(ids(client.get("/api/search", params={"q": query})))
    assert found == {seeded[name]["id"] for name in expected}


def test_search_treats_wildcards_literally(client, seeded):
    assert ids(client.get("/api/search", params={"q": "%"})) == [seeded["old"]["id"]]
    assert ids(client.get("/api/search", params={"q": "fine_ok"})) == [seeded["old"]["id"]]
    assert ids(client.get("/api/search", params={"q": "fine_xx"})) == []


def test_filter_by_record_type(client, seeded):
    assert set(ids(client.get("/api/records?record_type=prescription"))) == {seeded["rx"]["id"]}
    both = set(ids(client.get("/api/records?record_type=prescription&record_type=scan")))
    assert both == {seeded["rx"]["id"], seeded["scan"]["id"]}
    assert client.get("/api/records?record_type=nonsense").status_code == 422


def test_filter_by_date_range(client, seeded):
    in_range = set(ids(client.get("/api/records?date_from=2026-09-01&date_to=2026-09-05")))
    assert in_range == {seeded["visit"]["id"], seeded["rx"]["id"]}
    assert ids(client.get("/api/records?date_to=2025-12-31")) == [seeded["old"]["id"]]


def test_filter_by_tags_requires_all(client, seeded):
    assert set(ids(client.get("/api/records?tag=thyroid"))) == {seeded["visit"]["id"], seeded["rx"]["id"]}
    assert ids(client.get("/api/records?tag=Thyroid&tag=General")) == [seeded["rx"]["id"]]
    assert ids(client.get("/api/records?tag=Blood&tag=Thyroid")) == []


def test_filter_by_doctor_and_lab(client, seeded):
    assert ids(client.get(f"/api/records?doctor_id={seeded['visit']['doctor_id']}")) == [seeded["visit"]["id"]]
    assert ids(client.get(f"/api/records?lab_id={seeded['lab']['lab_id']}")) == [seeded["lab"]["id"]]


def test_search_combined_with_filters(client, seeded):
    response = client.get("/api/search", params={"q": "thyroid", "record_type": "prescription"})
    assert ids(response) == [seeded["rx"]["id"]]


def test_pagination(client, seeded):
    first = client.get("/api/records?limit=2&offset=0").json()
    second = client.get("/api/records?limit=2&offset=2").json()
    assert first["total"] == 5 and len(first["items"]) == 2 and len(second["items"]) == 2
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})
    assert client.get("/api/records?limit=0").status_code == 422
    assert client.get("/api/records?limit=1000").status_code == 422


def test_summary_shape(client, seeded):
    item = client.get("/api/records?record_type=lab_report").json()["items"][0]
    assert item["lab_name"] == "Pathcare Diagnostics"
    assert item["tags"] == ["B12", "Blood"]
    assert item["document_count"] == 0
    assert item["record_type"] == "lab_report"


def test_timeline_is_chronological_and_filterable(client, seeded):
    items = client.get("/api/timeline").json()
    dates = [i["record_date"] for i in items]
    assert dates == sorted(dates, reverse=True)
    assert len(items) == 5
    only_labs = client.get("/api/timeline?record_type=lab_report").json()
    assert [i["id"] for i in only_labs] == [seeded["lab"]["id"]]
    assert only_labs[0]["lab_name"] == "Pathcare Diagnostics"


def test_years_lists_each_year_with_records_newest_first(client, seeded):
    response = client.get("/api/years")
    assert response.status_code == 200, response.text
    assert response.json() == [{"year": 2026, "record_count": 4}, {"year": 2025, "record_count": 1}]


def test_years_is_empty_without_records(client):
    assert client.get("/api/years").json() == []
