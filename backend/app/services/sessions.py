"""Server-side login sessions.

The browser only ever holds a random token in an HTTP-only cookie. The database stores an HMAC of that
token, so a leaked database file cannot be used to impersonate the user.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, UserSession, utcnow


def _token_id(token: str) -> str:
    secret = get_settings().session_secret.encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def is_allowed_email(email: str) -> bool:
    """The one place that decides which accounts may use the app (sign-in and every request)."""
    return email.strip().lower() == get_settings().allowed_email_normalized


def get_or_create_user(db: Session, email: str, name: str | None) -> User:
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, name=name)
        db.add(user)
    elif name:
        user.name = name
    user.last_login_at = utcnow()
    db.commit()
    return user


def create_session(db: Session, user: User) -> str:
    settings = get_settings()
    purge_expired(db)
    token = secrets.token_urlsafe(48)
    db.add(
        UserSession(
            id=_token_id(token),
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
    session = db.get(UserSession, _token_id(token))
    if session is None:
        return None
    if session.expires_at <= utcnow():
        db.delete(session)
        db.commit()
        return None
    user = session.user
    # If ALLOWED_EMAIL changes, previously issued sessions for other accounts stop working immediately.
    if not is_allowed_email(user.email):
        return None
    return user


def delete_session(db: Session, token: str | None) -> None:
    if not token or len(token) > 200:
        return
    db.execute(delete(UserSession).where(UserSession.id == _token_id(token)))
    db.commit()


def purge_expired(db: Session) -> None:
    db.execute(delete(UserSession).where(UserSession.expires_at <= utcnow()))
    db.commit()
