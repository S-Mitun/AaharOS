"""The hosted demo (deployment): a visitor creates their own sandbox factory and becomes its owner; the API serves
the built web app at the same address, with client routes falling back to index.html and /api left alone."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.errors import RateLimitedError
from app.modules.judge import signup


def _body(**over: str) -> dict[str, str]:
    email = f"visitor-{uuid.uuid4().hex[:10]}@aaharos-demo.invalid"
    return {
        "factory_name": "Lakshmi Snacks",
        "display_name": "DEMO Visitor",
        "email": email,
        "password": "a-long-DEMO-pass",
        **over,
    }


def test_a_visitor_gets_their_own_factory_with_the_tour_data(api_app: Any) -> None:
    client = TestClient(api_app)
    body = _body()
    r = client.post("/api/signup", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "OWNER" and r.json()["organization_code"].startswith("SIM-OWN-")
    login = client.post("/api/auth/login", json={"email": body["email"], "password": body["password"]})
    assert login.status_code == 200, login.text
    me = login.json()
    assert me["role"] == "OWNER" and me["organization"]["name"] == "Lakshmi Snacks (DEMO sandbox)"
    lots = client.get("/api/trace/lots", params={"q": "OPEN"}).json()["lots"]
    assert [lot["lot_no"] for lot in lots] == ["OPEN-LOT"]  # their own opening stock, as in NIT's Section 5
    assert client.get("/api/trace/oil").status_code == 200  # the DEMO settings came with it
    again = TestClient(api_app).post("/api/signup", json={**_body(), "email": body["email"]})
    assert again.status_code == 409 and again.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize(
    ("field", "value"),
    [("password", "short"), ("email", "not-an-email"), ("factory_name", ""), ("display_name", "x")],
)
def test_bad_sign_ups_are_refused(api_app: Any, field: str, value: str) -> None:
    r = TestClient(api_app).post("/api/signup", json=_body(**{field: value}))
    assert r.status_code == 422


def test_sign_ups_are_rate_limited_per_address() -> None:
    ip = f"203.0.113.{uuid.uuid4().int % 250}"
    for n in range(signup.PER_IP_PER_HOUR):
        signup.check_rate(ip, now=100.0 + n)
    with pytest.raises(RateLimitedError):
        signup.check_rate(ip, now=200.0)
    signup.check_rate(ip, now=100.0 + 3601 + signup.PER_IP_PER_HOUR)


def test_the_api_serves_the_web_app_at_one_address(tmp_path: Path) -> None:
    from app.main import create_app, mount_web

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>AaharOS</title>", encoding="utf-8")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "sw.js").write_text("// sw", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("nope", encoding="utf-8")
    app = create_app()
    mount_web(app, tmp_path)
    client = TestClient(app)
    for page in ("/", "/guide", "/passport/abc.def", "/sales/freshness"):
        r = client.get(page)
        assert r.status_code == 200 and "<title>AaharOS</title>" in r.text, page
        assert r.headers["cache-control"] == "no-cache"
    asset = client.get("/assets/app-abc123.js")
    assert asset.text == "console.log(1)" and "immutable" in asset.headers["cache-control"]
    assert client.get("/sw.js").headers["cache-control"] == "no-cache"
    assert "nope" not in client.get("/../secret.txt").text and "nope" not in client.get("/%2e%2e/secret.txt").text
    missing = client.get("/api/no-such-route")
    assert missing.status_code == 404 and missing.json()["error"]["code"] in ("not_found", "http_404")
    assert client.get("/health").json()["status"] == "ok"  # real routes still win
