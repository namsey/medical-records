"""Server-side login sessions.

The browser only ever holds a random token in an HTTP-only cookie. The database stores an HMAC of that
token, so a leaked database file cannot be used to impersonate the user.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import audit
from app.models import User, UserSession, utcnow

# Recording each request's time would mean a database write per request; this often is enough for the idle timeout.
LAST_SEEN_INTERVAL = timedelta(minutes=5)


def hash_token(token: str) -> str:
    """HMAC of a random token (session cookie or invite link), as stored in the database."""
    secret = get_settings().session_secret.encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()



def is_admin_email(email: str) -> bool:
    return email.strip().lower() == get_settings().admin_email_normalized


def is_admin(user: User) -> bool:
    return user.role == "admin" or is_admin_email(user.email)


def can_use_app(user: User) -> bool:
    """The one place that decides whether an account may use the app (sign-in and every request).

    The bootstrap admin (ADMIN_EMAIL) always may. Everyone else needs an account (made from an invite) that is
    not disabled.
    """
    return is_admin_email(user.email) or user.disabled_at is None


def find_user(db: Session, email: str) -> User | None:
    """The account for an email, ignoring case (rows from older versions may not be stored in lower case)."""
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def demote_stale_admins(db: Session) -> int:
    """Keep admin rights in sync with ADMIN_EMAIL: any other admin account becomes a normal user (audited)."""
    stale = [user for user in db.scalars(select(User).where(User.role == "admin")) if not is_admin_email(user.email)]
    for user in stale:
        user.role = "user"
        audit.record(db, "admin_demoted", target=user, detail="not ADMIN_EMAIL")
    return len(stale)


def get_or_create_user(db: Session, email: str, name: str | None) -> User:
    """Record a sign-in. The bootstrap admin is (again) made an active admin; anyone else keeps their state."""
    email = email.strip().lower()
    user = find_user(db, email)
    if user is None:
        user = User(email=email, name=name)
        db.add(user)
    elif name:
        user.name = name
    if is_admin_email(email):
        user.role = "admin"
        user.disabled_at = None
    user.last_login_at = utcnow()
    db.commit()
    return user


def create_session(db: Session, user: User) -> str:
    settings = get_settings()
    purge_expired(db)
    token = secrets.token_urlsafe(48)
    db.add(
        UserSession(
            id=hash_token(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(days=settings.session_max_age_days),
        )
    )
    db.commit()
    return token


def get_user_for_token(db: Session, token: str | None) -> User | None:
    """Return the logged-in user for a session token, or None if it is missing, expired or not allowed."""
    if not token or len(token) > 200:
        return None
    session = db.get(UserSession, hash_token(token))
    if session is None:
        return None
    now = utcnow()
    # Signed out 14 days after signing in (SESSION_MAX_AGE_DAYS), or sooner after SESSION_IDLE_HOURS unused.
    if session.expires_at <= now or session.last_seen_at <= now - _idle_limit():
        db.delete(session)
        db.commit()
        return None
    user = session.user
    # A disabled account is signed out on its very next request.
    if not can_use_app(user):
        return None
    if now - session.last_seen_at >= LAST_SEEN_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return user


def _idle_limit() -> timedelta:
    return timedelta(hours=get_settings().session_idle_hours)


def delete_user_sessions(db: Session, user_id: str) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))


def delete_session(db: Session, token: str | None) -> None:
    if not token or len(token) > 200:
        return
    db.execute(delete(UserSession).where(UserSession.id == hash_token(token)))
    db.commit()


def purge_expired(db: Session) -> None:
    now = utcnow()
    db.execute(
        delete(UserSession).where((UserSession.expires_at <= now) | (UserSession.last_seen_at <= now - _idle_limit()))
    )
    db.commit()
