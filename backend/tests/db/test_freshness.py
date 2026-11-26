"""The shelf freshness radar against PostgreSQL (MP13, ADR-0020, module 4), on the DEMO history: today nothing is
near its best-before; ten days before B-001's best-before, Retailer D's single delivery (not enough history) is
flagged, the others' faster rhythms have sold it, and the Morning brief offers "Visit" with the rupees at stake."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.db import org_scope
from app.modules.planning import brief
from app.modules.traceability import freshness
from tests.db.conftest import login_client
from tests.db.test_food_safety import _factory, demo  # noqa: F401 - the fixture is reused


def _b001_best_before(api_app: Any, emails: dict[str, str]) -> date:
    owner = login_client(api_app, emails["OWNER"])
    lots = owner.get("/api/trace/lots", params={"q": "B-001"}).json()["lots"]
    return date.fromisoformat(lots[0]["best_before"])


def test_today_nothing_is_near_its_best_before(api_app: Any, demo: dict[str, Any]) -> None:  # noqa: F811
    owner = login_client(api_app, demo["emails"]["OWNER"])
    body = owner.get("/api/trace/freshness").json()
    assert (body["alert_days"], body["window_days"], body["flagged"]) == ("15", 90, 0)
    d = [r for r in body["rows"] if r["customer_code"] == "RET-D"]
    assert [(r["lot_no"], r["high"]["value"], r["enough_history"]) for r in d] == [("B-001", "80", False)]
    a = {r["lot_no"]: r for r in body["rows"] if r["customer_code"] == "RET-A"}
    assert a["B-002"]["rates"] == {
        "orders": 3,
        "span_days": 4,
        "central": "15.000000",
        "slow": "10.000000",
        "fast": "30.000000",
    }
    assert all(int(r["low"]) <= int(r["central"] or 0) <= int(r["high"]["value"]) for r in body["rows"])
    assert "not a shelf count" in body["note"]


def test_near_best_before_the_slow_shelf_is_flagged_and_reaches_the_brief(
    api_app: Any,
    demo: dict[str, Any],  # noqa: F811
    app_engine: Engine,
) -> None:
    on = _b001_best_before(api_app, demo["emails"]) - timedelta(days=10)
    with Session(app_engine) as s:
        org_scope(s, demo["org"])
        body = freshness.radar(s, on=on)
        flagged = [r for r in body["rows"] if r["flagged"]]
        assert [(r["customer_code"], r["lot_no"], r["high"]["value"], r["days_to_best_before"]) for r in flagged] == [
            ("RET-D", "B-001", "80", 10)
        ]
        assert flagged[0]["value_at_risk"]["value"] == "4000.00"  # 80 x 50.00
        assert flagged[0]["delivered"]["inputs"][0]["source"]["type"] == "dispatch"
        assert {r["customer_code"] for r in body["rows"]} == {"RET-D"}  # A and C have sold theirs by now
        actions = brief.morning_brief(s, on=on)["actions"]
        visit = [a for a in actions if a["kind"] == "visit"]
        assert visit == [
            {
                "kind": "visit",
                "title": "Visit DEMO Retailer D: up to 80 packets expire in 10 days",
                "impact": visit[0]["impact"],
                "link": "/sales/freshness",
            }
        ]
        assert visit[0]["impact"]["value"] == "4000.00" and visit[0]["impact"]["method"] == "Freshness radar"
        assert len(actions) <= 3


def test_a_salesman_sees_only_their_customers(api_app: Any, demo: dict[str, Any]) -> None:  # noqa: F811
    salesman_a = login_client(api_app, demo["emails"]["SALESMAN_A"])
    rows = salesman_a.get("/api/trace/freshness").json()["rows"]
    assert {r["customer_code"] for r in rows} == {"RET-C"}  # RET-A and RET-D are not assigned to them here
    production = login_client(api_app, demo["emails"]["PRODUCTION"])
    assert production.get("/api/trace/freshness").status_code == 403  # no customer.read


def test_without_the_setting_the_radar_says_so_and_the_brief_goes_on(
    api_app: Any, owner_engine: Engine, app_engine: Engine
) -> None:
    org, emails, _ = _factory(owner_engine, app_engine, "NOFRESH", settings=False)
    owner = login_client(api_app, emails["OWNER"])
    r = owner.get("/api/trace/freshness")
    assert r.status_code == 422 and r.json()["error"]["code"] == "setting_missing"
    assert owner.get("/api/planning/brief").status_code == 200
    with Session(app_engine) as s:
        org_scope(s, org)
        assert freshness.top_alert(s) is None
