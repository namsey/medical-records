"""sec-5: a sign-in ends after SESSION_IDLE_HOURS unused, and SESSION_MAX_AGE_DAYS after it began in any case."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.main import app
from app.models import UserSession, utcnow
from app.services import sessions
from tests.conftest import make_session_token
from tests.test_migration_0002 import _migrate, _rows, _seed_0001


def _session(token: str) -> UserSession | None:
    with SessionLocal() as db:
        return db.get(UserSession, sessions.hash_token(token))


def _set(token: str, **values: datetime) -> None:
    with SessionLocal() as db:
        session = db.get(UserSession, sessions.hash_token(token))
        for name, value in values.items():
            setattr(session, name, value)
        db.commit()


def _me(token: str) -> int:
    client = TestClient(app)
    client.cookies.set("session", token)
    return client.get("/api/auth/me").status_code


def test_a_new_session_starts_as_just_used():
    token = make_session_token()
    session = _session(token)
    assert utcnow() - session.last_seen_at < timedelta(seconds=10)
    assert abs(session.expires_at - session.created_at - timedelta(days=14)) < timedelta(seconds=1)


def test_session_idle_longer_than_the_limit_is_rejected_and_deleted():
    token = make_session_token()
    _set(token, last_seen_at=utcnow() - timedelta(hours=24, minutes=1))
    assert _me(token) == 401
    assert _session(token) is None


def test_session_used_within_the_limit_stays_and_its_time_is_refreshed():
    token = make_session_token()
    _set(token, last_seen_at=utcnow() - timedelta(hours=23))
    assert _me(token) == 200
    assert utcnow() - _session(token).last_seen_at < timedelta(seconds=10)


def test_last_seen_is_written_at_most_every_five_minutes():
    token = make_session_token()
    recent = utcnow() - timedelta(minutes=4)
    _set(token, last_seen_at=recent)
    assert _me(token) == 200
    assert _session(token).last_seen_at == recent
    older = utcnow() - timedelta(minutes=6)
    _set(token, last_seen_at=older)
    assert _me(token) == 200
    assert _session(token).last_seen_at > older


def test_idle_limit_follows_the_setting(monkeypatch):
    monkeypatch.setattr(get_settings(), "session_idle_hours", 1)
    token = make_session_token()
    _set(token, last_seen_at=utcnow() - timedelta(minutes=61))
    assert _me(token) == 401


def test_absolute_expiry_holds_even_for_a_session_in_constant_use():
    token = make_session_token()
    _set(
        token,
        created_at=utcnow() - timedelta(days=14, minutes=1),
        expires_at=utcnow() - timedelta(minutes=1),
        last_seen_at=utcnow() - timedelta(minutes=1),
    )
    assert _me(token) == 401
    assert _session(token) is None


def test_purge_removes_idle_and_expired_sessions_only():
    idle, expired, active = make_session_token(), make_session_token(), make_session_token()
    _set(idle, last_seen_at=utcnow() - timedelta(hours=25))
    _set(expired, expires_at=utcnow() - timedelta(seconds=1))
    with SessionLocal() as db:
        sessions.purge_expired(db)
    assert _session(idle) is None and _session(expired) is None
    assert _session(active) is not None


@pytest.mark.parametrize("hours", [0, 721])
def test_idle_hours_must_be_between_1_and_720(monkeypatch, hours):
    monkeypatch.setenv("SESSION_IDLE_HOURS", str(hours))
    with pytest.raises(ValidationError):
        Settings()


def test_migration_0006_marks_existing_sessions_as_used_now(tmp_path):
    database = tmp_path / "old.db"
    _seed_0001(database, users=[("u-owner", "owner@example.com")])
    _migrate(database, "0005")
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "INSERT INTO sessions (id, user_id, created_at, expires_at) VALUES "
            "('s1', 'u-owner', '2026-10-10 09:00:00.000000', '2026-10-24 09:00:00.000000')"
        )
    connection.close()
    before = _rows(database)
    started = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)  # stored values are naive UTC

    _migrate(database, "0006")

    assert _rows(database) == before
    connection = sqlite3.connect(database)
    try:
        row = connection.execute("SELECT id, created_at, expires_at, last_seen_at FROM sessions").fetchone()
        nullable = {r[1]: r[3] for r in connection.execute("PRAGMA table_info(sessions)")}
    finally:
        connection.close()
    assert row[:3] == ("s1", "2026-10-10 09:00:00.000000", "2026-10-24 09:00:00.000000")
    assert datetime.fromisoformat(row[3]) >= started
    assert nullable["last_seen_at"] == 1  # NOT NULL
