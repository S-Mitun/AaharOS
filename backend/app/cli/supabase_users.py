"""Hosted mode: make sure every DEMO login exists in Supabase Auth with its DEMO password (idempotent).

Run by deploy/start.sh when AAHAR_AUTH_MODE=supabase. For each DEMO email it tries the password grant; if that fails
it signs the account up. Needs "Confirm email" switched off in the Supabase project (Authentication -> Email):
otherwise a new account cannot sign in until it confirms an email that the DEMO domain can never receive.
"""

import json
import os
import sys
import urllib.error
import urllib.request

from app.cli.seed_demo import DEFAULT_DEMO_PASSWORD, DEMO_USERS
from app.core.config import get_settings


def _post(path: str, body: dict[str, str]) -> tuple[int, dict[str, object]]:
    s = get_settings()
    req = urllib.request.Request(  # noqa: S310 - the configured https Supabase URL
        f"{s.supabase_url.rstrip('/')}/auth/v1/{path}",
        data=json.dumps(body).encode(),
        headers={"apikey": s.supabase_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def _get(path: str) -> dict[str, object]:
    s = get_settings()
    req = urllib.request.Request(  # noqa: S310 - the configured https Supabase URL
        f"{s.supabase_url.rstrip('/')}/auth/v1/{path}", headers={"apikey": s.supabase_key}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return dict(json.loads(resp.read().decode() or "{}"))
    except (urllib.error.URLError, ValueError):
        return {}


def main() -> int:
    s = get_settings()
    if s.auth_mode != "supabase" or not s.supabase_url:
        print("supabase users: skipped (local sign-in)")
        return 0
    problems = 0
    autoconfirm = bool(_get("settings").get("mailer_autoconfirm"))
    for email, _name, _role, env in DEMO_USERS:
        password = os.environ.get(env) or DEFAULT_DEMO_PASSWORD
        status, _ = _post("token?grant_type=password", {"email": email, "password": password})
        if status == 200:
            continue
        if not autoconfirm:  # a sign-up would send a confirmation mail the DEMO domain never receives
            problems += 1
            print(f"supabase users: {email} is missing in Supabase Auth")
            continue
        status, body = _post("signup", {"email": email, "password": password})
        if status == 200 and body.get("access_token"):
            print(f"supabase users: created {email}")
        else:
            problems += 1
            print(f"supabase users: {email} cannot sign in yet ({status}: {body.get('msg') or body.get('error_code')})")
    if problems:
        print("supabase users: create the DEMO logins in Supabase (pre-confirmed), or switch off 'Confirm email'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
