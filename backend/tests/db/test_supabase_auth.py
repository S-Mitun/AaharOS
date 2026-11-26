"""Supabase Auth as the identity server (hosted mode): the browser signs in at Supabase; the app checks the Supabase
token and opens its own session; password sign-in here is off; sign-up takes the Supabase token; a bad token is 401.
Supabase's answer is simulated (no network in tests)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.modules.identity import supabase_auth
from tests.db.conftest import STAFF_PASSWORD, Staff

GOOD = "token-of-a-signed-in-supabase-user"


@pytest.fixture
def supabase_mode(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    s = get_settings()
    monkeypatch.setattr(s, "auth_mode", "supabase")
    monkeypatch.setattr(s, "supabase_url", "https://demo-ref.supabase.co")
    monkeypatch.setattr(s, "supabase_key", "sb_publishable_demo")
    who: dict[str, str] = {}

    def verified(token: str) -> str:
        if token not in who:
            raise AuthenticationError("supabase_token_invalid", "your sign-in has expired; sign in again")
        return who[token]

    monkeypatch.setattr(supabase_auth, "verified_email", verified)
    return who


def test_config_tells_the_browser_where_to_sign_in(api_app: Any, supabase_mode: dict[str, str]) -> None:
    cfg = TestClient(api_app).get("/api/auth/config").json()
    assert cfg == {
        "mode": "supabase",
        "supabase_url": "https://demo-ref.supabase.co",
        "supabase_key": "sb_publishable_demo",
    }


def test_exchange_opens_the_apps_session_and_logout_ends_it(
    api_app: Any, staff: Staff, supabase_mode: dict[str, str]
) -> None:
    supabase_mode[GOOD + "-admin"] = staff.emails["ADMIN"]
    c = TestClient(api_app)
    r = c.post("/api/auth/exchange", json={"access_token": GOOD + "-admin"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "ADMIN" and c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_password_sign_in_here_is_off_and_bad_tokens_are_refused(
    api_app: Any, staff: Staff, supabase_mode: dict[str, str]
) -> None:
    c = TestClient(api_app)
    r = c.post("/api/auth/login", json={"email": staff.emails["ADMIN"], "password": STAFF_PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "use_supabase_sign_in"
    bad = c.post("/api/auth/exchange", json={"access_token": "x" * 40})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "supabase_token_invalid"
    supabase_mode[GOOD + "-stranger"] = "stranger@aaharos.demo"  # a Supabase account with no factory here
    assert c.post("/api/auth/exchange", json={"access_token": GOOD + "-stranger"}).status_code == 401


def test_sign_up_takes_the_supabase_account(api_app: Any, supabase_mode: dict[str, str]) -> None:
    email = f"visitor-{uuid.uuid4().hex[:8]}@aaharos.demo"
    supabase_mode[GOOD + "-new"] = email
    c = TestClient(api_app)
    no_token = c.post("/api/signup", json={"factory_name": "DEMO Supa Snacks", "display_name": "DEMO Visitor"})
    assert no_token.status_code == 422 and no_token.json()["error"]["code"] == "access_token_required"
    made = c.post(
        "/api/signup",
        json={"factory_name": "DEMO Supa Snacks", "display_name": "DEMO Visitor", "access_token": GOOD + "-new"},
    )
    assert made.status_code == 201 and made.json()["email"] == email
    me = c.post("/api/auth/exchange", json={"access_token": GOOD + "-new"}).json()
    assert me["role"] == "OWNER" and me["organization"]["name"] == "DEMO Supa Snacks (DEMO sandbox)"
