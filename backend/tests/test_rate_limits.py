"""Rate limits (#41): sign-in and invite checks per IP address, invite creation and uploads per account."""

import pytest

from app.services import rate_limit
from app.services.rate_limit import RateLimiter
from tests.conftest import PDF_BYTES


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_sliding_window_allows_the_limit_then_waits_for_the_oldest_hit():
    clock = FakeClock()
    limiter = RateLimiter("test", limit=3, window_seconds=60, clock=clock)
    for _ in range(3):
        assert limiter.hit("a") is None
        clock.now += 10
    assert limiter.hit("a") == pytest.approx(30)  # the first hit expires 60s after it, 30s from now
    assert limiter.hit("b") is None  # other keys are counted separately
    clock.now += 30
    assert limiter.hit("a") is None


def test_a_batch_counts_every_item_and_is_refused_whole():
    clock = FakeClock()
    limiter = RateLimiter("test", limit=5, window_seconds=60, clock=clock)
    assert limiter.hit("a", cost=4) is None
    assert limiter.hit("a", cost=2) is not None  # 6 > 5: nothing is counted
    assert limiter.hit("a", cost=1) is None
    assert limiter.hit("a", cost=1) is not None


def test_sign_in_is_limited_per_ip(anon):
    for _ in range(rate_limit.SIGN_IN_STARTS.limit):
        assert anon.get("/api/auth/login", follow_redirects=False).headers["location"].startswith("https://accounts.google.com")
    response = anon.get("/api/auth/login", follow_redirects=False)
    assert response.headers["location"] == "/login?error=rate_limited"


def test_sign_in_callbacks_are_limited_per_ip(anon):
    for _ in range(rate_limit.SIGN_IN_CALLBACKS.limit):
        assert anon.get("/api/auth/callback?code=x&state=y", follow_redirects=False).headers["location"] == "/login?error=failed"
    response = anon.get("/api/auth/callback?code=x&state=y", follow_redirects=False)
    assert response.headers["location"] == "/login?error=rate_limited"


def test_invite_checks_are_limited_per_ip(anon):
    for _ in range(rate_limit.INVITE_CHECKS.limit):
        assert anon.get("/api/auth/invite/guess").status_code == 200
    response = anon.get("/api/auth/invite/guess")
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert response.json()["detail"].startswith("Too many invite checks. Try again in ")


def test_invite_creation_is_limited_per_admin(client):
    for number in range(rate_limit.INVITE_CREATES.limit):
        assert client.post("/api/admin/invites", json={"email": f"p{number}@example.com"}).status_code == 201
    response = client.post("/api/admin/invites", json={"email": "one-more@example.com"})
    assert response.status_code == 429
    assert "Too many invites in the last hour" in response.json()["detail"]


def test_uploads_are_limited_per_account_by_file_count(client, second_client, make_record):
    record = make_record()
    rate_limit.UPLOADED_FILES.hit(_owner_id(client), cost=rate_limit.UPLOADED_FILES.limit - 1)
    two_files = [("files", ("a.pdf", PDF_BYTES, "application/pdf")), ("files", ("b.pdf", PDF_BYTES, "application/pdf"))]
    response = client.post(f"/api/records/{record['id']}/documents", files=two_files)
    assert response.status_code == 429
    assert "Too many files uploaded" in response.json()["detail"]
    assert client.get(f"/api/records/{record['id']}").json()["documents"] == []
    one = client.post(f"/api/records/{record['id']}/documents", files=two_files[:1])
    assert one.status_code == 201
    # Another account has its own allowance.
    other = second_client.post("/api/records", json={"record_type": "doctor_visit", "record_date": "2026-01-01"}).json()
    assert second_client.post(f"/api/records/{other['id']}/documents", files=two_files).status_code == 201


def _owner_id(client) -> str:
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        return db.query(User).filter_by(email=client.get("/api/auth/me").json()["email"]).one().id
