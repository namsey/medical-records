"""The signed-in person's own account: agree to the privacy notice, download all their data, delete the account.

These work before the privacy notice is accepted (so someone who does not agree can still take their data and
leave), so this router checks the session and the CSRF header but not consent.
"""

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from app.models import utcnow
from app.schemas import ConsentIn, DeleteUserIn
from app.security import SESSION_COOKIE, csrf_protect, get_current_user
from app.services import rate_limit
from app.services.accounts import Account, get_account

router = APIRouter(prefix="/api/account", tags=["account"], dependencies=[Depends(get_current_user), Depends(csrf_protect)])


@router.post("/consent", status_code=status.HTTP_204_NO_CONTENT)
def give_consent(payload: ConsentIn, account: Account = Depends(get_account)) -> Response:
    """Agree to the privacy notice the app showed. It must be the current version."""
    account.give_consent(payload.version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export")
def download_my_data(account: Account = Depends(get_account)) -> FileResponse:
    """ZIP of records.json and every attached file under its original name, one folder per record."""
    rate_limit.enforce(rate_limit.DATA_EXPORTS, account.user.id, "You downloaded your data several times in the last hour.")
    archive = account.data_export()
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=f"my-medical-records-{utcnow().date().isoformat()}.zip",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )


@router.post("/delete")
def delete_my_account(payload: DeleteUserIn, account: Account = Depends(get_account)) -> JSONResponse:
    """Permanently delete the account and everything in it, then sign out."""
    account.delete(payload.confirm_email)
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
