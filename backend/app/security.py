"""Authentication / request-protection dependencies shared by all private routers."""

from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.sessions import get_user_for_token, is_admin

SESSION_COOKIE = "session"
OAUTH_STATE_COOKIE = "oauth_state"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "XMLHttpRequest"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_user_for_token(db, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def _same_origin(request: Request, origin: str) -> bool:
    """The Origin is this app: the host the request was sent to (kept by Caddy and the dev proxy), or the
    public address from GOOGLE_REDIRECT_URI."""
    host = request.headers.get("host", "")
    return (bool(host) and urlsplit(origin).netloc == host) or origin == get_settings().public_origin


def csrf_protect(request: Request) -> None:
    """State-changing requests must carry a custom header, and must not come from another site.

    Browsers refuse to send custom headers cross-origin without a CORS preflight, and this API
    allows no cross-origin access, so a third-party site cannot forge these requests. As a second layer,
    a request whose Origin header names another site is refused too.
    """
    if request.method in SAFE_METHODS:
        return
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing request header")
    origin = request.headers.get("origin")
    if origin is not None and not _same_origin(request, origin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request from another site")


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Admin-only routes answer 404 to everyone else, as if they did not exist."""
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return user


# Applied to every private router.
private_dependencies = [Depends(get_current_user), Depends(csrf_protect)]
admin_dependencies = [Depends(require_admin), Depends(csrf_protect)]
