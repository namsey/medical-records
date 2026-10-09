"""Google sign-in, session cookie handling and logout."""

import hmac
import logging
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import UserOut
from app.security import OAUTH_STATE_COOKIE, SESSION_COOKIE, csrf_protect, get_current_user
from app.services import sessions
from app.services.oauth import OAuthError, build_authorization_url, fetch_user_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

STATE_MAX_AGE_SECONDS = 600
AUTH_COOKIE_PATH = "/api/auth"


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="oauth-state")


def _login_redirect(error: str) -> RedirectResponse:
    response = RedirectResponse(f"/login?error={error}", status_code=302)
    response.delete_cookie(OAUTH_STATE_COOKIE, path=AUTH_COOKIE_PATH)
    return response


@router.get("/login", include_in_schema=False)
def login() -> RedirectResponse:
    """Start the Google OAuth flow."""
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    response = RedirectResponse(build_authorization_url(state, verifier), status_code=302)
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        _state_serializer().dumps({"state": state, "verifier": verifier}),
        max_age=STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",  # must be Lax: the cookie has to come back on Google's top-level redirect
        path=AUTH_COOKIE_PATH,
    )
    return response


@router.get("/callback", include_in_schema=False)
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Google redirects here after sign-in."""
    settings = get_settings()
    if error:
        return _login_redirect("denied")
    if not code or not state:
        return _login_redirect("failed")

    try:
        saved = _state_serializer().loads(request.cookies.get(OAUTH_STATE_COOKIE, ""), max_age=STATE_MAX_AGE_SECONDS)
        expected_state, verifier = str(saved["state"]), str(saved["verifier"])
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        return _login_redirect("failed")
    if not hmac.compare_digest(expected_state, state):
        return _login_redirect("failed")

    try:
        profile = fetch_user_profile(code, verifier)
    except OAuthError:
        logger.warning("Google sign-in failed")
        return _login_redirect("failed")

    email = str(profile.get("email") or "").strip().lower()
    if not email or profile.get("email_verified") is not True or email != settings.allowed_email_normalized:
        logger.warning("Sign-in rejected: account is not the allowed account")
        return _login_redirect("not_allowed")

    name = profile.get("name")
    user = sessions.get_or_create_user(db, email, name if isinstance(name, str) else None)
    token = sessions.create_session(db, user)

    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(OAUTH_STATE_COOKIE, path=AUTH_COOKIE_PATH)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_max_age_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(email=user.email, name=user.name)


@router.post("/logout", dependencies=[Depends(csrf_protect)])
def logout(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    sessions.delete_session(db, request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
