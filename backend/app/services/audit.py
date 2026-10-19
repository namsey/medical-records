"""The audit log: sign-ins, invites, account changes and deletions. Viewable by the admin.

An entry names the action, who did it and which account it was about (ids and emails), plus an optional short
detail such as a refusal reason. It never holds record contents, file names or IP addresses. A refused sign-in
stores only the reason: that person has no account here. Entries are kept for one year.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, User, utcnow

RETENTION = timedelta(days=365)

ACTIONS = {
    "sign_in": "Signed in",
    "sign_in_refused": "Sign-in refused",
    "invite_created": "Invite created",
    "invite_revoked": "Invite revoked",
    "invite_used": "Invite used",
    "account_disabled": "Account disabled",
    "account_enabled": "Account enabled",
    "account_deleted": "Account deleted",
    "quota_changed": "Storage limit changed",
    "consent_given": "Privacy notice accepted",
    "signed_out_everywhere": "Signed out of all devices",
    "data_downloaded": "Data downloaded",
}


def record(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    target: User | None = None,
    target_email: str | None = None,
    detail: str | None = None,
) -> None:
    """Add an entry and commit it."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown audit action {action}")
    db.add(
        AuditEvent(
            action=action,
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            target_id=target.id if target else None,
            target_email=target.email if target else target_email,
            detail=detail,
        )
    )
    db.commit()


def recent(db: Session, *, before: datetime | None = None, limit: int = 50) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.at.desc()).limit(limit)
    if before is not None:
        stmt = stmt.where(AuditEvent.at < before)
    return list(db.scalars(stmt).all())


def purge_old(db: Session) -> None:
    db.execute(delete(AuditEvent).where(AuditEvent.at < utcnow() - RETENTION))
    db.commit()
