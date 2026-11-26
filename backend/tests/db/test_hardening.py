"""MP17 hardening: security headers, the same-origin check on writes, readiness, the web app's CSP."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.db.conftest import Staff


def test_security_headers_and_readiness(api_app: Any) -> None:
    c = TestClient(api_app)
    r = c.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin" and "x-correlation-id" in r.headers
    ready = c.get("/ready").json()
    assert ready["status"] == "ready" and int(ready["units"]) > 0


def test_a_write_from_another_site_is_refused(api_app: Any, staff: Staff) -> None:
    c = TestClient(api_app)
    login = {"email": staff.emails["ADMIN"], "password": "DEMO-test-pass-123"}
    evil = c.post("/api/auth/login", json=login, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403 and evil.json()["error"]["code"] == "cross_site_request"
    assert c.post("/api/auth/login", json=login, headers={"Origin": "null"}).status_code == 403
    same = c.post("/api/auth/login", json=login, headers={"Origin": "http://testserver"})
    assert same.status_code == 200
    allowed = c.post("/api/auth/login", json=login, headers={"Origin": "http://localhost:5180"})
    assert allowed.status_code == 200
    assert c.get("/api/auth/me", headers={"Origin": "https://evil.example"}).status_code == 200  # reads pass


def test_the_web_app_gets_a_content_security_policy(tmp_path: Path) -> None:
    from app.main import create_app, mount_web

    (tmp_path / "index.html").write_text("<!doctype html><title>AaharOS</title>", encoding="utf-8")
    app = create_app()
    mount_web(app, tmp_path)
    r = TestClient(app).get("/guide")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    # index.html loads Inter and Noto Sans Tamil from Google Fonts: the policy must allow exactly those two hosts
    assert "https://fonts.googleapis.com" in r.headers["content-security-policy"]
    assert "https://fonts.gstatic.com" in r.headers["content-security-policy"]
