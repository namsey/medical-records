from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.database import SessionLocal
from app.main import app
from app.models import UserSession, utcnow
from app.services.oauth import OAuthError
from tests.conftest import CSRF_HEADERS, make_session_token

PRIVATE_GET_PATHS = [
    "/api/records",
    "/api/records/abc",
    "/api/search?q=x",
    "/api/timeline",
    "/api/doctors",
    "/api/labs",
    "/api/tags",
    "/api/years",
    "/api/documents/abc",
    "/api/documents/abc/view",
    "/api/documents/abc/download",
    "/api/backup",
    "/api/export/json",
]


def test_health_is_public(anon):
    assert anon.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", PRIVATE_GET_PATHS)
def test_private_endpoints_require_login(anon, path):
    assert anon.get(path).status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/records"),
        ("put", "/api/records/abc"),
        ("delete", "/api/records/abc"),
        ("post", "/api/records/abc/documents"),
        ("delete", "/api/documents/abc"),
        ("post", "/api/doctors"),
        ("post", "/api/labs"),
    ],
)
def test_private_writes_require_login(anon, method, path):
    assert getattr(anon, method)(path).status_code == 401


def test_me_returns_current_user(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"


def test_state_changing_requests_need_csrf_header(client):
    no_header = TestClient(app)
    no_header.cookies.set("session", make_session_token())
    assert no_header.post("/api/doctors", json={"name": "Dr X"}).status_code == 403
    assert no_header.post("/api/auth/logout").status_code == 403
    # Reads are fine without it.
    assert no_header.get("/api/doctors").status_code == 200


def test_login_redirects_to_google_with_pkce_and_state_cookie(anon):
    response = anon.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 302
    target = urlparse(response.headers["location"])
    query = parse_qs(target.query)
    assert target.netloc == "accounts.google.com"
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == ["http://localhost:8000/api/auth/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"][0]
    cookie = response.headers["set-cookie"].lower()
    assert "oauth_state=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def _start_login(anon) -> str:
    response = anon.get("/api/auth/login", follow_redirects=False)
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def _fake_profile(monkeypatch, **profile):
    data = {"email": "owner@example.com", "email_verified": True, "name": "Owner", **profile}
    monkeypatch.setattr("app.routers.auth.fetch_user_profile", lambda code, verifier: data)


def test_callback_success_creates_httponly_session(anon, monkeypatch):
    _fake_profile(monkeypatch)
    state = _start_login(anon)
    response = anon.get(f"/api/auth/callback?code=abc&state={state}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"
    cookies = [value.lower() for key, value in response.headers.multi_items() if key == "set-cookie"]
    session_cookie = next(c for c in cookies if c.startswith("session="))
    assert "httponly" in session_cookie and "samesite=lax" in session_cookie
    assert anon.get("/api/auth/me").json()["email"] == "owner@example.com"


def test_callback_email_match_is_case_insensitive(anon, monkeypatch):
    _fake_profile(monkeypatch, email="Owner@Example.com")
    state = _start_login(anon)
    response = anon.get(f"/api/auth/callback?code=abc&state={state}", follow_redirects=False)
    assert response.headers["location"] == "/"


def test_callback_rejects_other_google_accounts(anon, monkeypatch):
    _fake_profile(monkeypatch, email="intruder@example.com")
    state = _start_login(anon)
    response = anon.get(f"/api/auth/callback?code=abc&state={state}", follow_redirects=False)
    assert response.headers["location"] == "/login?error=not_allowed"
    assert "session=" not in response.headers.get("set-cookie", "").replace("oauth_state", "")
    assert anon.get("/api/auth/me").status_code == 401


def test_callback_rejects_unverified_email(anon, monkeypatch):
    _fake_profile(monkeypatch, email_verified=False)
    state = _start_login(anon)
    response = anon.get(f"/api/auth/callback?code=abc&state={state}", follow_redirects=False)
    assert response.headers["location"] == "/login?error=not_allowed"


def test_callback_rejects_wrong_state(anon, monkeypatch):
    _fake_profile(monkeypatch)
    _start_login(anon)
    response = anon.get("/api/auth/callback?code=abc&state=forged", follow_redirects=False)
    assert response.headers["location"] == "/login?error=failed"
    assert anon.get("/api/auth/me").status_code == 401


def test_callback_without_state_cookie_fails(anon, monkeypatch):
    _fake_profile(monkeypatch)
    response = anon.get("/api/auth/callback?code=abc&state=whatever", follow_redirects=False)
    assert response.headers["location"] == "/login?error=failed"


def test_callback_handles_google_errors(anon, monkeypatch):
    def boom(code, verifier):
        raise OAuthError("nope")

    monkeypatch.setattr("app.routers.auth.fetch_user_profile", boom)
    state = _start_login(anon)
    response = anon.get(f"/api/auth/callback?code=abc&state={state}", follow_redirects=False)
    assert response.headers["location"] == "/login?error=failed"
    response = anon.get("/api/auth/callback?error=access_denied", follow_redirects=False)
    assert response.headers["location"] == "/login?error=denied"


def test_logout_ends_session(client):
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_logout_invalidates_token_server_side(client):
    token = client.cookies.get("session")
    client.post("/api/auth/logout")
    client.cookies.set("session", token)  # replay the old cookie
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client):
    with SessionLocal() as db:
        db.execute(update(UserSession).values(expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    assert client.get("/api/records").status_code == 401


def test_session_for_a_non_allowed_account_is_rejected():
    other = TestClient(app, headers=CSRF_HEADERS)
    other.cookies.set("session", make_session_token("someone-else@example.com"))
    assert other.get("/api/records").status_code == 401


def test_garbage_session_cookie_is_rejected(anon):
    anon.cookies.set("session", "x" * 500)
    assert anon.get("/api/records").status_code == 401
    anon.cookies.set("session", "not-a-real-token")
    assert anon.get("/api/records").status_code == 401


def test_session_table_stores_only_a_hash(client):
    token = client.cookies.get("session")
    with SessionLocal() as db:
        ids = [row.id for row in db.query(UserSession).all()]
    assert ids and token not in ids
    assert all(len(i) == 64 for i in ids)


def test_security_headers_present(client):
    response = client.get("/api/records")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_api_docs_are_disabled(client):
    # Depending on whether the frontend is built, these either 404 or fall through to the web app's HTML page;
    # in neither case is an API schema or Swagger UI served.
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)
        assert "swagger" not in response.text.lower()
        assert '"openapi"' not in response.text
        assert not response.headers["content-type"].startswith("application/json") or response.status_code == 404


def test_unknown_api_path_is_404_json(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
