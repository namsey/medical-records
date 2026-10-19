"""Admin panel: invites and accounts. Admin only (404 for everyone else).

No route here returns another user's records or files: AdminStore only reads accounts, invites and sizes.
"""

from fastapi import APIRouter, Depends, Response, status

from app.schemas import AdminUserOut, DeleteUserIn, InviteCreated, InviteIn, InviteOut
from app.security import admin_dependencies
from app.services import rate_limit
from app.services.admin_store import AdminStore, get_admin_store

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=admin_dependencies)


@router.get("/invites", response_model=list[InviteOut])
def list_invites(store: AdminStore = Depends(get_admin_store)) -> list[InviteOut]:
    return store.list_invites()


@router.post("/invites", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
def create_invite(payload: InviteIn, store: AdminStore = Depends(get_admin_store)) -> InviteCreated:
    """The response holds the invite link. It is shown once: copy it and send it yourself."""
    rate_limit.enforce(rate_limit.INVITE_CREATES, store.admin.id, "Too many invites in the last hour.")
    return store.create_invite(payload.email)


@router.post("/invites/{invite_id}/revoke", response_model=InviteOut)
def revoke_invite(invite_id: str, store: AdminStore = Depends(get_admin_store)) -> InviteOut:
    return store.revoke_invite(invite_id)


@router.get("/users", response_model=list[AdminUserOut])
def list_users(store: AdminStore = Depends(get_admin_store)) -> list[AdminUserOut]:
    return store.list_users()


@router.post("/users/{user_id}/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_user(user_id: str, store: AdminStore = Depends(get_admin_store)) -> Response:
    store.set_disabled(user_id, True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/enable", status_code=status.HTTP_204_NO_CONTENT)
def enable_user(user_id: str, store: AdminStore = Depends(get_admin_store)) -> Response:
    store.set_disabled(user_id, False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, payload: DeleteUserIn, store: AdminStore = Depends(get_admin_store)) -> Response:
    store.delete_user(user_id, payload.confirm_email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
