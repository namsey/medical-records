"""Minimal Google OAuth 2.0 authorization-code flow with PKCE (no extra OAuth library needed)."""

import base64
import hashlib
from urllib.parse import urlencode

import httpx

from app.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
HTTP_TIMEOUT = 10.0


class OAuthError(Exception):
    """Raised when Google rejects a request or returns something unusable."""


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def build_authorization_url(state: str, verifier: str, login_hint: str | None = None) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge(verifier),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_URL}?{urlencode(params)}"


def fetch_user_profile(code: str, verifier: str) -> dict[str, object]:
    """Exchange the authorization code for an access token and return Google's userinfo."""
    settings = get_settings()
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            token_response = client.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
            if token_response.status_code != 200:
                raise OAuthError("Google rejected the authorization code")
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise OAuthError("Google did not return an access token")
            profile_response = client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
            if profile_response.status_code != 200:
                raise OAuthError("Could not read the Google profile")
            profile = profile_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OAuthError("Could not reach Google") from exc
    if not isinstance(profile, dict):
        raise OAuthError("Unexpected response from Google")
    return profile
