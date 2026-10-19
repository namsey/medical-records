"""Authentication / request-protection dependencies shared by all private routers."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

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


def csrf_protect(request: Request) -> None:
    """State-changing requests must carry a custom header.

    Browsers refuse to send custom headers cross-origin without a CORS preflight, and this API
    allows no cross-origin access, so a third-party site cannot forge these requests.
    """
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing request header")


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Admin-only routes answer 404 to everyone else, as if they did not exist."""
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return user


# Applied to every private router.
private_dependencies = [Depends(get_current_user), Depends(csrf_protect)]
admin_dependencies = [Depends(require_admin), Depends(csrf_protect)]
