"""#43: privacy notice consent, grievance contact, download my data, delete my account, and the audit log."""

import io
import json
import re
import zipfile
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import AuditEvent, User, utcnow
from app.privacy import PRIVACY_VERSION
from app.services import audit
from tests.conftest import CSRF_HEADERS, PDF_BYTES, PNG_BYTES, make_session_token
from tests.test_route_guards import API_ROUTES, PUBLIC_ROUTES

SECRET = "Pangolinwort"  # only ever in record contents and file names


def _client(email: str, consented: bool = True) -> TestClient:
    test_client = TestClient(app, headers=CSRF_HEADERS)
    test_client.cookies.set("session", make_session_token(email, consented=consented))
    return test_client


def _seed(client) -> dict:
    record = client.post(
        "/api/records",
        json={"record_type": "lab_report", "record_date": "2026-03-04", "title": f"{SECRET} panel", "test_name": "TSH",
              "personal_notes": f"{SECRET} note", "tags": ["Thyroid"]},
    ).json()
    for name, content in (("report.pdf", PDF_BYTES), ("report.pdf", PDF_BYTES), (f"{SECRET}.png", PNG_BYTES)):
        assert client.post(f"/api/records/{record['id']}/documents", files={"files": (name, content)}).status_code == 201
    return record


def _events() -> list[AuditEvent]:
    with SessionLocal() as db:
        return list(db.query(AuditEvent).order_by(AuditEvent.at).all())


# ---------------------------------------------------------------- consent

# Routes that work before the privacy notice is accepted: sign-in, who-am-I, sign-out, and the account's own
# consent / download / delete (so someone who does not agree can still take their data and leave).
BEFORE_CONSENT = {route for route in API_ROUTES if route[1].startswith(("/api/auth/", "/api/account/"))} | PUBLIC_ROUTES


@pytest.mark.parametrize(("method", "path"), sorted(set(API_ROUTES) - BEFORE_CONSENT))
def test_everything_else_waits_for_consent(method, path):
    newcomer = _client("new@example.com", consented=False)
    response = newcomer.request(method, re.sub(r"\{[^}]+\}", "x", path), json={})
    assert (response.status_code, response.json()) == (403, {"detail": "consent_required"})


def test_consent_is_given_once_for_the_current_notice():
    newcomer = _client("new@example.com", consented=False)
    assert newcomer.get("/api/auth/me").json()["needs_consent"] is True
    assert newcomer.post("/api/account/consent", json={"version": "1999-01"}).status_code == 409
    assert newcomer.post("/api/account/consent", json={"version": PRIVACY_VERSION}).status_code == 204
    assert newcomer.get("/api/auth/me").json()["needs_consent"] is False
    assert newcomer.get("/api/records").status_code == 200
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="new@example.com").one()
        assert user.consent_version == PRIVACY_VERSION and user.consented_at is not None
    assert [(e.action, e.detail) for e in _events()] == [("consent_given", PRIVACY_VERSION)]


def test_admin_also_needs_consent():
    admin = _client("owner@example.com", consented=False)
    assert admin.get("/api/admin/users").json() == {"detail": "consent_required"}


def test_privacy_info_is_public_with_the_admin_as_default_contact(anon, monkeypatch):
    assert anon.get("/api/auth/privacy").json() == {
        "version": PRIVACY_VERSION,
        "grievance_name": "The administrator of this app",
        "grievance_email": "owner@example.com",
    }
    monkeypatch.setattr(get_settings(), "grievance_name", "Naman")
    monkeypatch.setattr(get_settings(), "grievance_email", "privacy@example.com")
    assert anon.get("/api/auth/privacy").json()["grievance_email"] == "privacy@example.com"


# ---------------------------------------------------------------- download my data


def test_download_my_data_has_records_and_original_files_only_mine(client, second_client):
    record = _seed(second_client)
    client.post("/api/records", json={"record_type": "doctor_visit", "record_date": "2026-01-01", "title": "Owner only"})

    response = second_client.get("/api/account/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert re.search(r'filename="my-medical-records-\d{4}-\d{2}-\d{2}\.zip"', response.headers["content-disposition"])
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    folder = f"files/2026-03-04 {SECRET} panel"
    assert sorted(archive.namelist()) == sorted(
        ["records.json", "README.txt", f"{folder}/report.pdf", f"{folder}/report (2).pdf", f"{folder}/{SECRET}.png"]
    )
    assert archive.read(f"{folder}/report (2).pdf") == PDF_BYTES
    data = json.loads(archive.read("records.json"))
    assert [r["id"] for r in data["records"]] == [record["id"]]
    assert b"Owner only" not in archive.read("records.json")
    assert [e.action for e in _events()][-1] == "data_downloaded"


def test_download_works_before_consent_and_is_rate_limited():
    newcomer = _client("new@example.com", consented=False)
    for _ in range(5):
        assert newcomer.get("/api/account/export").status_code == 200
    assert newcomer.get("/api/account/export").status_code == 429


# ---------------------------------------------------------------- delete my account


def test_delete_my_account_removes_everything_and_signs_out(client, second_client):
    _seed(second_client)
    own = client.post("/api/records", json={"record_type": "doctor_visit", "record_date": "2026-01-01", "title": "Mine"}).json()
    with SessionLocal() as db:
        user_id = db.query(User).filter_by(email="second@example.com").one().id
    assert second_client.post("/api/account/delete", json={"confirm_email": "wrong@example.com"}).status_code == 422

    response = second_client.post("/api/account/delete", json={"confirm_email": "SECOND@example.com"})
    assert response.status_code == 200
    assert "session=" in response.headers["set-cookie"]
    assert second_client.get("/api/auth/me").status_code == 401
    assert not (get_settings().files_path / user_id).exists()
    with SessionLocal() as db:
        assert db.get(User, user_id) is None
    assert client.get(f"/api/records/{own['id']}").status_code == 200
    deleted = [e for e in _events() if e.action == "account_deleted"]
    assert [(e.target_email, e.detail) for e in deleted] == [("second@example.com", "by the account owner")]


def test_the_admin_cannot_delete_their_own_account(client):
    response = client.post("/api/account/delete", json={"confirm_email": "owner@example.com"})
    assert response.status_code == 409
    assert client.get("/api/auth/me").status_code == 200


# ---------------------------------------------------------------- audit log


def _sign_in(anon, monkeypatch, email: str, invite: str | None = None) -> str:
    profile = {"email": email, "email_verified": True, "name": "Someone"}
    monkeypatch.setattr("app.routers.auth.fetch_user_profile", lambda code, verifier: profile)
    start = anon.get(f"/api/auth/login{'?invite=' + invite if invite else ''}", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return anon.get(f"/api/auth/callback?code=c&state={state}", follow_redirects=False).headers["location"]


def test_account_events_are_logged_without_any_contents(client, anon, monkeypatch):
    invite = client.post("/api/admin/invites", json={"email": "friend@example.com"}).json()
    token = invite["link"].rsplit("/", 1)[1]
    assert _sign_in(anon, monkeypatch, "stranger@example.com") == "/login?error=not_invited"
    assert _sign_in(anon, monkeypatch, "friend@example.com", token) == "/"
    friend = TestClient(app, headers=CSRF_HEADERS, cookies=anon.cookies)
    friend.post("/api/account/consent", json={"version": PRIVACY_VERSION})
    _seed(friend)
    with SessionLocal() as db:
        friend_id = db.query(User).filter_by(email="friend@example.com").one().id
    client.put(f"/api/admin/users/{friend_id}/quota", json={"quota_mb": 250})
    client.post(f"/api/admin/users/{friend_id}/disable")
    client.post(f"/api/admin/users/{friend_id}/enable")
    second_invite = client.post("/api/admin/invites", json={"email": "later@example.com"}).json()
    client.post(f"/api/admin/invites/{second_invite['id']}/revoke")
    client.post("/api/auth/logout-all")
    client.cookies.set("session", make_session_token())
    client.post(f"/api/admin/users/{friend_id}/delete", json={"confirm_email": "friend@example.com"})

    log = client.get("/api/admin/audit").json()
    actions = [(e["action"], e["actor_email"], e["target_email"], e["detail"]) for e in reversed(log)]
    assert actions == [
        ("invite_created", "owner@example.com", "friend@example.com", None),
        ("sign_in_refused", None, None, "not_invited"),
        ("invite_used", "friend@example.com", "friend@example.com", None),
        ("sign_in", "friend@example.com", "friend@example.com", None),
        ("consent_given", "friend@example.com", "friend@example.com", PRIVACY_VERSION),
        ("quota_changed", "owner@example.com", "friend@example.com", "250 MB"),
        ("account_disabled", "owner@example.com", "friend@example.com", None),
        ("account_enabled", "owner@example.com", "friend@example.com", None),
        ("invite_created", "owner@example.com", "later@example.com", None),
        ("invite_revoked", "owner@example.com", "later@example.com", None),
        ("signed_out_everywhere", "owner@example.com", "owner@example.com", None),
        ("account_deleted", "owner@example.com", "friend@example.com", None),
    ]
    assert log[0]["label"] == "Account deleted"
    raw = client.get("/api/admin/audit").text
    assert SECRET not in raw and "stranger@example.com" not in raw


def test_audit_log_pages_and_old_entries_are_purged(client):
    with SessionLocal() as db:
        for days in (1, 2, 3, 400):
            db.add(AuditEvent(action="sign_in", at=utcnow() - timedelta(days=days), actor_email=f"d{days}@example.com"))
        db.commit()
    first = client.get("/api/admin/audit?limit=2").json()
    assert [e["actor_email"] for e in first] == ["d1@example.com", "d2@example.com"]
    rest = client.get("/api/admin/audit", params={"before": first[-1]["at"], "limit": 10}).json()
    assert [e["actor_email"] for e in rest] == ["d3@example.com", "d400@example.com"]
    with SessionLocal() as db:
        audit.purge_old(db)
    assert [e["actor_email"] for e in client.get("/api/admin/audit").json()] == [
        "d1@example.com", "d2@example.com", "d3@example.com"
    ]


def test_every_audit_action_has_a_label():
    assert all(label for label in audit.ACTIONS.values())
    with pytest.raises(ValueError):
        with SessionLocal() as db:
            audit.record(db, "made_up_action")

