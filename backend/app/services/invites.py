"""Single-use invites: one email address, 7 days, revocable.

The link holds a random secret; the database keeps only its HMAC, so a leaked database cannot be turned back
into working links. The link is shown once, when the invite is made.
"""

import re
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Invite, User, utcnow
from app.services.sessions import hash_token

INVITE_DAYS = 7
MAX_TOKEN_LENGTH = 200
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

InviteStatus = Literal["pending", "used", "expired", "revoked"]
RedeemError = Literal["invite_invalid", "invite_wrong_account"]


def normalize_email(email: str) -> str:
    return email.strip().lower()


def invite_status(invite: Invite) -> InviteStatus:
    if invite.used_at is not None:
        return "used"
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at <= utcnow():
        return "expired"
    return "pending"


def invite_link(token: str) -> str:
    return f"{get_settings().public_origin}/invite/{token}"


def create_invite(db: Session, email: str, created_by: User) -> tuple[Invite, str]:
    """A new pending invite and its secret. Any older pending invite for the same email is revoked."""
    email = normalize_email(email)
    if not EMAIL_RE.match(email) or len(email) > 320:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Enter a valid email address")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email already has an account")
    now = utcnow()
    db.execute(
        update(Invite)
        .where(Invite.email == email, Invite.used_at.is_(None), Invite.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    token = secrets.token_urlsafe(32)
    invite = Invite(
        email=email,
        token_hash=hash_token(token),
        created_by_id=created_by.id,
        created_at=now,
        expires_at=now + timedelta(days=INVITE_DAYS),
    )
    db.add(invite)
    db.commit()
    return invite, token


def find_invite(db: Session, token: str | None) -> Invite | None:
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    return db.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))


def is_usable(db: Session, token: str | None) -> bool:
    invite = find_invite(db, token)
    return invite is not None and invite_status(invite) == "pending"


def revoke_invite(db: Session, invite_id: str) -> Invite:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite_status(invite) != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a pending invite can be revoked")
    invite.revoked_at = utcnow()
    db.commit()
    return invite


def list_invites(db: Session) -> list[Invite]:
    return list(db.scalars(select(Invite).order_by(Invite.created_at.desc())).all())


def redeem(db: Session, token: str | None, email: str, name: str | None) -> User | RedeemError:
    """Create the invited account for a verified Google email, or say why not. The invite works only once."""
    invite = find_invite(db, token)
    if invite is None or invite_status(invite) != "pending":
        return "invite_invalid"
    if invite.email != normalize_email(email):
        return "invite_wrong_account"  # the invite stays usable for the right account
    now = utcnow()
    # One statement checks and uses the invite, so two sign-ins cannot both use it.
    claimed = db.execute(
        update(Invite)
        .where(
            Invite.id == invite.id,
            Invite.used_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > now,
        )
        .values(used_at=now)
    )
    if claimed.rowcount != 1:
        db.rollback()
        return "invite_invalid"
    user = User(email=invite.email, name=name, role="user", last_login_at=now)
    db.add(user)
    db.flush()
    db.execute(update(Invite).where(Invite.id == invite.id).values(used_by_id=user.id))
    db.commit()
    return user
