"""Supabase Auth as the identity server (hosted mode, AAHAR_AUTH_MODE=supabase).

The browser signs up, signs in and signs out at Supabase Auth (its OAuth 2 token endpoint, email + password). It
then hands the Supabase access token to `POST /api/auth/exchange`; this module asks Supabase who the token belongs to
(`GET /auth/v1/user`, so Supabase checks the signature, the expiry and that the session is still signed in) and
returns the verified email. The app then opens its own httpOnly-cookie session with the user's role, exactly as a
local sign-in does (ADR-0010), so every permission check, the audit trail and sign-out work unchanged.
"""

import json
import urllib.error
import urllib.request
from typing import Final

from app.core.config import get_settings
from app.core.errors import AuthenticationError, DomainError

TIMEOUT_S: Final = 10


def enabled() -> bool:
    s = get_settings()
    return s.auth_mode == "supabase" and bool(s.supabase_url) and bool(s.supabase_key)


def verified_email(access_token: str) -> str:
    """The email Supabase Auth vouches for, or AuthenticationError (expired, signed out, forged, unconfirmed)."""
    s = get_settings()
    if not enabled():
        raise DomainError("supabase_auth_off", "this server does not use Supabase sign-in")
    req = urllib.request.Request(  # noqa: S310 - the configured https Supabase URL, never user input
        f"{s.supabase_url.rstrip('/')}/auth/v1/user",
        headers={"apikey": s.supabase_key, "Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
            user = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise AuthenticationError("supabase_token_invalid", "your sign-in has expired; sign in again") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DomainError("supabase_unreachable", "the sign-in server did not answer; try again") from exc
    email = str(user.get("email") or "").strip().lower()
    if not email or not user.get("email_confirmed_at"):
        raise AuthenticationError("supabase_email_unconfirmed", "this email address is not confirmed yet")
    return email
