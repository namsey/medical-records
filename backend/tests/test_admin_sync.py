"""sec-4: at startup, only the ADMIN_EMAIL account keeps admin rights; every other admin is demoted and audited."""

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AuditEvent, User
from app.services import audit, sessions
from tests.conftest import make_session_token

ADMIN = "owner@example.com"  # ADMIN_EMAIL in conftest


def _add_users() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                User(email=ADMIN, role="admin"),
                User(email="former-admin@example.com", role="admin"),
                User(email="other@example.com", role="admin"),
                User(email="member@example.com", role="user"),
            ]
        )
        db.commit()


def _roles() -> dict[str, str]:
    with SessionLocal() as db:
        return {user.email: user.role for user in db.query(User)}


def _demotions() -> list[tuple[str | None, str | None, str | None]]:
    with SessionLocal() as db:
        return sorted(
            (e.actor_email, e.target_email, e.detail) for e in db.query(AuditEvent).filter_by(action="admin_demoted")
        )


def test_admins_other_than_admin_email_are_demoted_and_audited():
    _add_users()
    with SessionLocal() as db:
        assert sessions.demote_stale_admins(db) == 2
    assert _roles() == {
        ADMIN: "admin",
        "former-admin@example.com": "user",
        "other@example.com": "user",
        "member@example.com": "user",
    }
    assert _demotions() == [
        (None, "former-admin@example.com", "not ADMIN_EMAIL"),
        (None, "other@example.com", "not ADMIN_EMAIL"),
    ]
    assert audit.ACTIONS["admin_demoted"] == "Admin rights removed"
    with SessionLocal() as db:
        assert sessions.demote_stale_admins(db) == 0  # nothing left to do, nothing more logged
    assert len(_demotions()) == 2


def test_admin_email_matches_case_insensitively():
    with SessionLocal() as db:
        db.add(User(email="Owner@Example.com", role="admin"))
        db.commit()
        assert sessions.demote_stale_admins(db) == 0
    assert _roles() == {"Owner@Example.com": "admin"}


def test_startup_demotes_and_the_old_admin_loses_the_admin_pages():
    _add_users()
    former = TestClient(app)
    former.cookies.set("session", make_session_token("former-admin@example.com"))
    assert former.get("/api/admin/system").status_code == 200
    with TestClient(app):  # runs the lifespan again
        pass
    assert _roles()["former-admin@example.com"] == "user"
    assert former.get("/api/admin/system").status_code == 404
