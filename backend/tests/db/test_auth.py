"""Login, cookies, rate limit, refresh rotation, logout and deactivation (MP03, ADR-0010)."""

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.config import get_settings
from app.modules.identity.domain import ACCESS_COOKIE, REFRESH_COOKIE, AccessClaims, issue_access_token
from tests.db.conftest import STAFF_PASSWORD, Staff, add_member, as_org, login_client, make_staff, make_tenant


def _set_cookie_headers(response: Any) -> dict[str, str]:
    headers = response.headers.get_list("set-cookie")
    return {h.split("=", 1)[0]: h for h in headers}


def test_login_sets_httponly_cookies_and_me_works(api_app: Any, staff: Staff) -> None:
    client = TestClient(api_app)
    r = client.post("/api/auth/login", json={"email": staff.emails["ADMIN"], "password": STAFF_PASSWORD})
    assert r.status_code == 200
    assert r.json()["role"] == "ADMIN"
    cookies = _set_cookie_headers(r)
    access, refresh = cookies[ACCESS_COOKIE].lower(), cookies[REFRESH_COOKIE].lower()
    assert "httponly" in access and "samesite=lax" in access and "path=/api" in access
    assert "httponly" in refresh and "samesite=strict" in refresh and "path=/api/auth" in refresh

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["organization"]["code"] == staff.code
    assert "invoice.post" in body["permissions"] and "user.manage" not in body["permissions"]


def test_password_is_stored_as_argon2id(owner_engine: Engine, staff: Staff) -> None:
    with owner_engine.connect() as c:
        stored = c.execute(
            text("SELECT password_hash FROM users WHERE id = :u"), {"u": staff.user_ids["OWNER"]}
        ).scalar_one()
    assert stored.startswith("$argon2id$")
    assert STAFF_PASSWORD not in stored


def test_wrong_password_and_unknown_email_look_the_same(api_app: Any, staff: Staff) -> None:
    client = TestClient(api_app)
    wrong = client.post("/api/auth/login", json={"email": staff.emails["AUDITOR"], "password": "nope-nope-nope"})
    unknown = client.post("/api/auth/login", json={"email": "ghost@aaharos-demo.invalid", "password": "x"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "invalid_credentials"


def test_login_rate_limited_after_five_failures(owner_engine: Engine, api_app: Any) -> None:
    t = make_tenant(owner_engine, "RATE")
    _uid, email = add_member(owner_engine, t, "SALESMAN")
    client = TestClient(api_app)
    for _ in range(get_settings().login_max_failures):
        assert client.post("/api/auth/login", json={"email": email, "password": "wrong"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"email": email, "password": STAFF_PASSWORD})
    assert blocked.status_code == 429  # even the right password waits out the window
    assert blocked.json()["error"]["code"] == "too_many_attempts"


def test_no_cookie_gives_401_envelope(api_app: Any) -> None:
    r = TestClient(api_app).get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_tampered_or_expired_access_token_rejected(api_app: Any, staff: Staff) -> None:
    client = login_client(api_app, staff.emails["PRODUCTION"])
    token = client.cookies.get(ACCESS_COOKIE)
    assert token
    forged = TestClient(api_app, cookies={ACCESS_COOKIE: token[:-3] + ("AAA" if token[-3:] != "AAA" else "BBB")})
    assert forged.get("/api/auth/me").status_code == 401

    settings = get_settings()
    claims = AccessClaims(staff.user_ids["PRODUCTION"], staff.tenant.org, uuid.uuid4())
    expired = issue_access_token(claims, settings.auth_secret, timedelta(minutes=-1))
    assert TestClient(api_app, cookies={ACCESS_COOKIE: expired}).get("/api/auth/me").status_code == 401

    other_secret = issue_access_token(
        claims, "a-different-secret-of-sufficient-length-1234567890", timedelta(minutes=5)
    )
    assert TestClient(api_app, cookies={ACCESS_COOKIE: other_secret}).get("/api/auth/me").status_code == 401


def test_logout_revokes_the_session_immediately(api_app: Any, staff: Staff) -> None:
    client = login_client(api_app, staff.emails["SALESMAN"])
    access = client.cookies.get(ACCESS_COOKIE)
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    assert ACCESS_COOKIE in r.headers.get("set-cookie", "")  # cleared
    stolen = TestClient(api_app, cookies={ACCESS_COOKIE: access})
    assert stolen.get("/api/auth/me").status_code == 401  # the token is unexpired, but its session is gone


def test_refresh_rotates_and_a_reused_token_ends_the_session(owner_engine: Engine, api_app: Any, staff: Staff) -> None:
    client = login_client(api_app, staff.emails["ADMIN"])
    first = client.cookies.get(REFRESH_COOKIE, path="/api/auth")
    rotated = client.post("/api/auth/refresh")
    assert rotated.status_code == 200
    second = client.cookies.get(REFRESH_COOKIE, path="/api/auth")
    assert second and second != first

    assert first
    thief = TestClient(api_app, cookies={REFRESH_COOKIE: first})
    replay = thief.post("/api/auth/refresh")
    assert replay.status_code == 401

    # the legitimate client is logged out too: the whole session was revoked
    assert client.post("/api/auth/refresh").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    with owner_engine.connect() as c:
        actions = (
            c.execute(
                text("SELECT action FROM audit_log WHERE organization_id = :o ORDER BY seq"), {"o": staff.tenant.org}
            )
            .scalars()
            .all()
        )
    assert "auth.refresh_reused" in actions


def test_deactivated_member_loses_access_at_once(owner_engine: Engine, api_app: Any) -> None:
    team = make_staff(owner_engine, "DEACT")
    salesman = login_client(api_app, team.emails["SALESMAN"])
    owner = login_client(api_app, team.emails["OWNER"])
    r = owner.post(f"/api/identity/users/{team.user_ids['SALESMAN']}/deactivate")
    assert r.status_code == 204
    assert salesman.get("/api/auth/me").status_code == 401
    again = TestClient(api_app).post(
        "/api/auth/login", json={"email": team.emails["SALESMAN"], "password": STAFF_PASSWORD}
    )
    assert again.status_code == 401
    assert owner.post(f"/api/identity/users/{team.user_ids['OWNER']}/deactivate").status_code == 422  # not yourself


def test_owner_creates_a_member_who_can_log_in(owner_engine: Engine, api_app: Any) -> None:
    team = make_staff(owner_engine, "CREATE")
    owner = login_client(api_app, team.emails["OWNER"])
    email = f"new-salesman-{uuid.uuid4().hex[:8]}@aaharos-demo.invalid"
    weak = owner.post(
        "/api/identity/users",
        json={"email": email, "display_name": "DEMO New", "role": "SALESMAN", "password": "short"},
    )
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    made = owner.post(
        "/api/identity/users",
        json={"email": email, "display_name": "DEMO New", "role": "SALESMAN", "password": "a-long-DEMO-pass"},
    )
    assert made.status_code == 201
    assert login_client(api_app, email, "a-long-DEMO-pass").get("/api/auth/me").json()["role"] == "SALESMAN"
    with owner_engine.connect() as c:
        summary = c.execute(
            text("SELECT summary FROM audit_log WHERE organization_id = :o AND action = 'user.create'"),
            {"o": team.tenant.org},
        ).scalar_one()
    assert "a-long-DEMO-pass" not in str(summary)


def test_user_in_two_organizations_must_choose(owner_engine: Engine, api_app: Any) -> None:
    a = make_tenant(owner_engine, "MULTI-A")
    b = make_tenant(owner_engine, "MULTI-B")
    uid, email = add_member(owner_engine, a, "ADMIN")
    with owner_engine.begin() as c:
        c.execute(
            text("INSERT INTO memberships (organization_id, user_id, role_code) VALUES (:o, :u, 'AUDITOR')"),
            {"o": b.org, "u": uid},
        )
        b_code = c.execute(text("SELECT code FROM organizations WHERE id = :o"), {"o": b.org}).scalar_one()
    client = TestClient(api_app)
    ask = client.post("/api/auth/login", json={"email": email, "password": STAFF_PASSWORD})
    assert ask.status_code == 422 and ask.json()["error"]["code"] == "organization_required"
    chosen = client.post(
        "/api/auth/login", json={"email": email, "password": STAFF_PASSWORD, "organization_code": b_code}
    )
    assert chosen.status_code == 200 and chosen.json()["role"] == "AUDITOR"


def test_users_of_another_organization_are_invisible(owner_engine: Engine, app_engine: Engine) -> None:
    """RLS on users: password hashes of another tenant's staff can never be read."""
    a = make_staff(owner_engine, "SEE-A")
    b = make_staff(owner_engine, "SEE-B")
    with app_engine.begin() as c:
        as_org(c, a.tenant.org)
        mine = c.execute(text("SELECT count(*) FROM users WHERE id = ANY(:ids)"), {"ids": list(a.user_ids.values())})
        theirs = c.execute(text("SELECT count(*) FROM users WHERE id = ANY(:ids)"), {"ids": list(b.user_ids.values())})
        assert (mine.scalar_one(), theirs.scalar_one()) == (5, 0)
    with app_engine.begin() as c:  # and nothing at all without an org
        assert c.execute(text("SELECT count(*) FROM users")).scalar_one() == 0


def test_correlation_id_is_echoed_and_audited(owner_engine: Engine, api_app: Any) -> None:
    team = make_staff(owner_engine, "CORR")
    cid = str(uuid.uuid4())
    r = TestClient(api_app).post(
        "/api/auth/login",
        json={"email": team.emails["OWNER"], "password": STAFF_PASSWORD},
        headers={"X-Correlation-Id": cid},
    )
    assert r.headers["X-Correlation-Id"] == cid
    with owner_engine.connect() as c:
        stored = c.execute(
            text("SELECT correlation_id FROM audit_log WHERE organization_id = :o AND action = 'auth.login'"),
            {"o": team.tenant.org},
        ).scalar_one()
    assert str(stored) == cid
