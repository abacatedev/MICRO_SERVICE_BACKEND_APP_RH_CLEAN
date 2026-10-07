"""Google OAuth feito à mão com httpx (sem Passport)."""
from urllib.parse import urlencode

import httpx

from app.config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def callback_url() -> str:
    return f"{settings.base_url}/auth/google/callback"


def authorization_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def fetch_profile(code: str) -> dict:
    """Troca o code do Google pelo perfil (sub, email, email_verified, name)."""
    with httpx.Client(timeout=10) as client:
        token = client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": callback_url(),
                "grant_type": "authorization_code",
            },
        )
        token.raise_for_status()
        info = client.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {token.json()['access_token']}"}
        )
        info.raise_for_status()
        return info.json()
