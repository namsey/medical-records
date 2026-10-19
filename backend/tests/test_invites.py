"""Invites: made by the admin, single-use, bound to one email, 7 days, revocable."""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import update

from app.database import SessionLocal
from app.models import Invite, User, utcnow

INVITED = "friend@example.com"


def _invite(client, email: str = INVITED) -> tuple[dict, str]:
    response = client.post("/api/admin/invites", json={"email": email})
    assert response.status_code == 201, response.text
    body = response.json()
    return body, body["link"].rsplit("/", 1)[1]


def _sign_in(anon, monkeypatch, email: str, invite_token: str | None = None) -> str:
    """Go through the sign-in flow as `email` (Google is faked); returns where the app sends the browser."""
    profile = {"email": email, "email_verified": True, "name": "Friend"}
    monkeypatch.setattr("app.routers.auth.fetch_user_profile", lambda code, verifier: profile)
    query = f"?invite={invite_token}" if invite_token else ""
    response = anon.get(f"/api/auth/login{query}", follow_redirects=False)
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    return anon.get(f"/api/auth/callback?code=abc&state={state}", follow_redirects=False).headers["location"]


def _set(invite_id: str, **values) -> None:
    with SessionLocal() as db:
        db.execute(update(Invite).where(Invite.id == invite_id).values(**values))
        db.commit()


def test_admin_creates_an_invite_link_shown_once(client):
    invite, token = _invite(client, "  Friend@Example.com ")
    assert invite["email"] == INVITED
    assert invite["status"] == "pending"
    assert invite["link"] == f"http://localhost:8000/invite/{token}"
    assert len(token) >= 40
    expires = invite["expires_at"][:10]
    assert expires == (utcnow() + timedelta(days=7)).date().isoformat()
    with SessionLocal() as db:
        row = db.get(Invite, invite["id"])
        assert token not in (row.token_hash, row.email)  # only a hash of the secret is stored
    listed = client.get("/api/admin/invites").json()
    assert [(i["email"], i["status"]) for i in listed] == [(INVITED, "pending")]
    assert "link" not in listed[0]


def test_new_invite_for_the_same_email_revokes_the_old_one(client, anon):
    first, first_token = _invite(client)
    _invite(client)
    statuses = {i["id"]: i["status"] for i in client.get("/api/admin/invites").json()}
    assert statuses[first["id"]] == "revoked"
    assert anon.get(f"/api/auth/invite/{first_token}").json() == {"valid": False}


@pytest.mark.parametrize("email", ["", "not-an-email", "a@b", "two@@example.com"])
def test_invalid_email_is_refused(client, email):
    assert client.post("/api/admin/invites", json={"email": email}).status_code == 422


def test_cannot_invite_an_existing_account(client, second_client):
    response = client.post("/api/admin/invites", json={"email": "second@example.com"})
    assert response.status_code == 409


def test_invite_check_says_only_valid_or_not(client, anon):
    invite, token = _invite(client)
    assert anon.get(f"/api/auth/invite/{token}").json() == {"valid": True}
    assert INVITED not in anon.get(f"/api/auth/invite/{token}").text
    assert anon.get("/api/auth/invite/made-up-token").json() == {"valid": False}
    _set(invite["id"], expires_at=utcnow() - timedelta(minutes=1))
    assert anon.get(f"/api/auth/invite/{token}").json() == {"valid": False}


def test_invited_person_signs_in_once(client, anon, monkeypatch):
    invite, token = _invite(client)
    assert _sign_in(anon, monkeypatch, INVITED, token) == "/"
    me = anon.get("/api/auth/me").json()
    assert me == {"email": INVITED, "name": "Friend", "is_admin": False}
    statuses = {i["id"]: i["status"] for i in client.get("/api/admin/invites").json()}
    assert statuses[invite["id"]] == "used"
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=INVITED).one()
        assert user.role == "user" and user.disabled_at is None
        assert db.get(Invite, invite["id"]).used_by_id == user.id

    # Signing in again later needs no invite; the used link does nothing more.
    anon.cookies.clear()
    assert _sign_in(anon, monkeypatch, INVITED) == "/"
    anon.cookies.clear()
    assert _sign_in(anon, monkeypatch, "someone-else@example.com", token) == "/login?error=invite_invalid"


def test_invite_for_another_email_is_refused_and_stays_usable(client, anon, monkeypatch):
    _, token = _invite(client)
    assert _sign_in(anon, monkeypatch, "wrong@example.com", token) == "/login?error=invite_wrong_account"
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.get(f"/api/auth/invite/{token}").json() == {"valid": True}
    assert _sign_in(anon, monkeypatch, INVITED.upper(), token) == "/"


@pytest.mark.parametrize("change", ["expired", "revoked"])
def test_expired_or_revoked_invite_does_not_work(client, anon, monkeypatch, change):
    invite, token = _invite(client)
    if change == "expired":
        _set(invite["id"], expires_at=utcnow() - timedelta(seconds=1))
    else:
        assert client.post(f"/api/admin/invites/{invite['id']}/revoke").json()["status"] == "revoked"
    assert _sign_in(anon, monkeypatch, INVITED, token) == "/login?error=invite_invalid"
    with SessionLocal() as db:
        assert db.query(User).filter_by(email=INVITED).count() == 0


def test_only_pending_invites_can_be_revoked(client, anon, monkeypatch):
    invite, token = _invite(client)
    _sign_in(anon, monkeypatch, INVITED, token)
    assert client.post(f"/api/admin/invites/{invite['id']}/revoke").status_code == 409
    assert client.post("/api/admin/invites/nope/revoke").status_code == 404


def test_no_invite_no_account(anon, monkeypatch):
    assert _sign_in(anon, monkeypatch, "stranger@example.com") == "/login?error=not_invited"
    assert _sign_in(anon, monkeypatch, "stranger@example.com", "made-up") == "/login?error=invite_invalid"
    with SessionLocal() as db:
        assert db.query(User).filter_by(email="stranger@example.com").count() == 0


def test_disabled_account_cannot_sign_in_even_with_an_invite(client, second_client, anon, monkeypatch):
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == "second@example.com").values(disabled_at=utcnow()))
        db.commit()
    assert _sign_in(anon, monkeypatch, "second@example.com") == "/login?error=disabled"


def test_bootstrap_admin_always_signs_in_as_an_enabled_admin(anon, monkeypatch):
    assert _sign_in(anon, monkeypatch, "owner@example.com") == "/"
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == "owner@example.com").values(role="user", disabled_at=utcnow()))
        db.commit()
    anon.cookies.clear()
    assert _sign_in(anon, monkeypatch, "Owner@example.com") == "/"
    assert anon.get("/api/auth/me").json()["is_admin"] is True
    with SessionLocal() as db:
        owner = db.query(User).filter_by(email="owner@example.com").one()
        assert (owner.role, owner.disabled_at) == ("admin", None)


def test_the_old_setting_name_still_works(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.setenv("ALLOWED_EMAIL", "legacy@example.com")
    assert Settings().admin_email_normalized == "legacy@example.com"
