"""Admin panel: accounts can be listed, disabled, enabled and deleted, and no admin route shows anyone's records."""

from app.config import get_settings
from app.database import SessionLocal
from app.models import Doctor, Document, Invite, MedicalRecord, Tag, User, UserSession
from tests.conftest import PDF_BYTES, PNG_BYTES

SECRET = "Quokkaberry"  # only the second user's records and files contain it


def _seed_second_user(second_client) -> dict:
    doctor = second_client.post("/api/doctors", json={"name": f"Dr. {SECRET}"}).json()
    record = second_client.post(
        "/api/records",
        json={"record_type": "doctor_visit", "record_date": "2026-01-01", "title": f"{SECRET} visit",
              "doctor_id": doctor["id"], "tags": [SECRET]},
    ).json()
    for name, content in ((f"{SECRET}.pdf", PDF_BYTES), (f"{SECRET}.png", PNG_BYTES)):
        second_client.post(f"/api/records/{record['id']}/documents", files={"files": (name, content)})
    return record


def _second_user_id() -> str:
    with SessionLocal() as db:
        return db.query(User).filter_by(email="second@example.com").one().id


def _users(client) -> dict[str, dict]:
    return {u["email"]: u for u in client.get("/api/admin/users").json()}


def test_user_list_shows_storage_but_never_contents(client, second_client):
    _seed_second_user(second_client)
    client.post("/api/admin/invites", json={"email": "new@example.com"})
    users = _users(client)
    assert users["second@example.com"]["file_count"] == 2
    assert users["second@example.com"]["storage_bytes"] == len(PDF_BYTES) + len(PNG_BYTES)
    assert users["second@example.com"]["is_admin"] is False
    assert users["owner@example.com"]["is_admin"] is True
    assert users["owner@example.com"]["storage_bytes"] == 0

    for path in ("/api/admin/users", "/api/admin/invites"):
        response = client.get(path)
        assert response.status_code == 200
        assert SECRET not in response.text, path


def test_me_says_who_is_admin(client, second_client):
    assert client.get("/api/auth/me").json()["is_admin"] is True
    assert second_client.get("/api/auth/me").json()["is_admin"] is False


def test_disable_signs_out_at_once_and_enable_lets_back_in(client, second_client):
    user_id = _second_user_id()
    assert second_client.get("/api/records").status_code == 200
    assert client.post(f"/api/admin/users/{user_id}/disable").status_code == 204
    assert second_client.get("/api/records").status_code == 401
    assert _users(client)["second@example.com"]["disabled"] is True
    with SessionLocal() as db:
        assert db.query(UserSession).filter_by(user_id=user_id).count() == 0

    assert client.post(f"/api/admin/users/{user_id}/enable").status_code == 204
    assert _users(client)["second@example.com"]["disabled"] is False


def test_admin_accounts_cannot_be_disabled_or_deleted(client):
    with SessionLocal() as db:
        owner_id = db.query(User).filter_by(email="owner@example.com").one().id
    assert client.post(f"/api/admin/users/{owner_id}/disable").status_code == 409
    response = client.post(f"/api/admin/users/{owner_id}/delete", json={"confirm_email": "owner@example.com"})
    assert response.status_code == 409
    assert client.post("/api/admin/users/nope/disable").status_code == 404


def test_delete_needs_the_email_typed(client, second_client):
    _seed_second_user(second_client)
    user_id = _second_user_id()
    response = client.post(f"/api/admin/users/{user_id}/delete", json={"confirm_email": "someone@example.com"})
    assert response.status_code == 422
    assert second_client.get("/api/records").json()["total"] == 1


def test_delete_removes_the_account_and_everything_in_it(client, second_client, make_record):
    _seed_second_user(second_client)
    own = make_record(tags=["Mine"])  # the admin's own data must survive
    client.post("/api/admin/invites", json={"email": "later@example.com"})
    user_id = _second_user_id()
    user_files = get_settings().files_path / user_id
    assert len(list(user_files.iterdir())) == 2

    response = client.post(f"/api/admin/users/{user_id}/delete", json={"confirm_email": " Second@Example.com "})
    assert response.status_code == 204

    assert second_client.get("/api/records").status_code == 401
    assert not user_files.exists()
    with SessionLocal() as db:
        assert db.get(User, user_id) is None
        assert db.query(MedicalRecord).filter_by(user_id=user_id).count() == 0
        assert db.query(Doctor).filter_by(user_id=user_id).count() == 0
        assert db.query(Tag).filter_by(user_id=user_id).count() == 0
        assert db.query(UserSession).filter_by(user_id=user_id).count() == 0
        assert db.query(Document).count() == 0
        assert db.query(Invite).count() == 1  # invites made by the admin are kept
    assert client.get(f"/api/records/{own['id']}").status_code == 200
    assert client.get("/api/tags").json() == [{"name": "Mine", "record_count": 1}]
