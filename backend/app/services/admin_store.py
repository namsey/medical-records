"""AdminStore: what the admin panel may read and change.

Accounts and invites only. It never reads a record, a doctor, a laboratory or a file: storage is a sum of
document sizes, and deleting an account removes its data without looking at it.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, Invite, MedicalRecord, User, utcnow
from app.schemas import AdminUserOut, InviteCreated, InviteOut
from app.security import require_admin
from app.services import invites, sessions
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
        return InviteCreated(**_invite_out(invite).model_dump(), link=invites.invite_link(token))

    def list_invites(self) -> list[InviteOut]:
        return [_invite_out(invite) for invite in invites.list_invites(self.db)]

    def revoke_invite(self, invite_id: str) -> InviteOut:
        return _invite_out(invites.revoke_invite(self.db, invite_id))

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

    def set_disabled(self, user_id: str, disabled: bool) -> None:
        user = self._changeable_user(user_id)
        user.disabled_at = utcnow() if disabled else None
        if disabled:
            sessions.delete_user_sessions(self.db, user.id)
        self.db.commit()

    def delete_user(self, user_id: str, confirm_email: str) -> None:
        """Delete the account and everything in it: records, doctors, laboratories, tags, files and sessions."""
        user = self._changeable_user(user_id)
        if invites.normalize_email(confirm_email) != user.email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Type the account's email to confirm"
            )
        # Records first (their documents, medicines, results and tag links go with them), so no record still
        # points at a doctor or laboratory when the account's other rows are removed with it.
        self.db.execute(delete(MedicalRecord).where(MedicalRecord.user_id == user.id))
        self.db.execute(delete(User).where(User.id == user.id))
        self.db.commit()
        self.files.delete_user_files(user.id)


def get_admin_store(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminStore:
    return AdminStore(db, admin)
