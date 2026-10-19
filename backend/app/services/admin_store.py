"""AdminStore: what the admin panel may read and change.

Accounts and invites only. It never reads a record, a doctor, a laboratory or a file: storage is a sum of
document sizes, and deleting an account removes its data without looking at it.
"""

from datetime import datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, Invite, MedicalRecord, User, utcnow
from app.config import get_settings
from app.schemas import AdminUserOut, AuditOut, DiskOut, InviteCreated, InviteOut, SystemOut
from app.security import require_admin
from app.services import accounts, audit, invites, sessions, system_status
from app.services.storage import FileStore, get_file_store, quota_bytes


def _invite_out(invite: Invite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        email=invite.email,
        status=invites.invite_status(invite),
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        used_at=invite.used_at,
    )


class AdminStore:
    def __init__(self, db: Session, admin: User, files: FileStore | None = None) -> None:
        self.db = db
        self.admin = admin
        self.files = files or get_file_store()

    # ------------------------------------------------------------ invites

    def create_invite(self, email: str) -> InviteCreated:
        invite, token = invites.create_invite(self.db, email, self.admin)
        audit.record(self.db, "invite_created", actor=self.admin, target_email=invite.email)
        return InviteCreated(**_invite_out(invite).model_dump(), link=invites.invite_link(token))

    def list_invites(self) -> list[InviteOut]:
        return [_invite_out(invite) for invite in invites.list_invites(self.db)]

    def revoke_invite(self, invite_id: str) -> InviteOut:
        invite = invites.revoke_invite(self.db, invite_id)
        audit.record(self.db, "invite_revoked", actor=self.admin, target_email=invite.email)
        return _invite_out(invite)

    # ------------------------------------------------------------ accounts

    def list_users(self) -> list[AdminUserOut]:
        usage = (
            select(
                MedicalRecord.user_id,
                func.count(Document.id).label("file_count"),
                func.coalesce(func.sum(Document.size_bytes), 0).label("storage_bytes"),
            )
            .join(Document, Document.record_id == MedicalRecord.id)
            .group_by(MedicalRecord.user_id)
            .subquery()
        )
        rows = self.db.execute(
            select(User, usage.c.file_count, usage.c.storage_bytes)
            .outerjoin(usage, usage.c.user_id == User.id)
            .order_by(User.created_at)
        ).all()
        return [
            AdminUserOut(
                id=user.id,
                email=user.email,
                name=user.name,
                is_admin=sessions.is_admin(user),
                disabled=not sessions.can_use_app(user),
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                file_count=file_count or 0,
                storage_bytes=storage_bytes or 0,
                quota_bytes=quota_bytes(user.quota_bytes),
                quota_is_default=user.quota_bytes is None,
            )
            for user, file_count, storage_bytes in rows
        ]

    def _changeable_user(self, user_id: str) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        if user.id == self.admin.id or sessions.is_admin(user):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An admin account cannot be changed here")
        return user

    def set_quota(self, user_id: str, quota_mb: int | None) -> None:
        """Change an account's storage limit (None: back to the default). Lowering it never deletes files."""
        user = self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        user.quota_bytes = None if quota_mb is None else quota_mb * 1024 * 1024
        self.db.commit()
        audit.record(self.db, "quota_changed", actor=self.admin, target=user, detail="default" if quota_mb is None else f"{quota_mb} MB")

    def set_disabled(self, user_id: str, disabled: bool) -> None:
        user = self._changeable_user(user_id)
        user.disabled_at = utcnow() if disabled else None
        if disabled:
            sessions.delete_user_sessions(self.db, user.id)
        self.db.commit()
        audit.record(self.db, "account_disabled" if disabled else "account_enabled", actor=self.admin, target=user)

    def delete_user(self, user_id: str, confirm_email: str) -> None:
        """Delete the account and everything in it: records, doctors, laboratories, tags, files and sessions."""
        user = self._changeable_user(user_id)
        if invites.normalize_email(confirm_email) != user.email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Type the account's email to confirm"
            )
        email = user.email
        accounts.delete_account(self.db, user, self.files)
        audit.record(self.db, "account_deleted", actor=self.admin, target_email=email)


    # ------------------------------------------------------------ audit log

    def audit_log(self, before: datetime | None, limit: int) -> list[AuditOut]:
        return [
            AuditOut(
                at=event.at,
                action=event.action,
                label=audit.ACTIONS[event.action],
                actor_email=event.actor_email,
                target_email=event.target_email,
                detail=event.detail,
            )
            for event in audit.recent(self.db, before=before, limit=limit)
        ]


    # ------------------------------------------------------------ server

    def system(self) -> SystemOut:
        backup = system_status.backup_state()
        return SystemOut(
            disks=[DiskOut(name=disk.name, percent_used=disk.percent_used) for disk in system_status.disks()],
            disk_alert_percent=get_settings().disk_alert_percent,
            backup_state=backup.state,
            last_backup_at=backup.last_success,
            last_backup_failure_at=backup.last_failure,
            started_at=system_status.STARTED_AT,
        )


def get_admin_store(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminStore:
    return AdminStore(db, admin)
