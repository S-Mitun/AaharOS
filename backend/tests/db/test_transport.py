"""Transport against PostgreSQL (MP14, ADR-0021): plan the day's trips from its dispatch notes, write them, record
actual km and tolls, and read cost-to-serve with the Deal Desk floor; who may do what; nothing is planned twice."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.db import org_scope
from app.modules.dispatch import service as dispatch
from app.modules.judge.replay import setup_section5_transport
from tests.db.conftest import login_client
from tests.db.test_food_safety import _factory, demo  # noqa: F401 - the fixture is reused


@pytest.fixture(scope="module")
def fleet(demo: dict[str, Any], app_engine: Engine) -> dict[str, Any]:  # noqa: F811
    with Session(app_engine) as s:
        org_scope(s, demo["org"])
        added = setup_section5_transport(s, demo["org"])
        s.commit()
        days = sorted({b.dispatch_date for b in dispatch.dispatch_briefs(s)})
    return {**demo, "added": added, "days": days}


def test_plan_write_and_complete_the_days_trips(api_app: Any, fleet: dict[str, Any]) -> None:
    admin = login_client(api_app, fleet["emails"]["ADMIN"])
    auditor = login_client(api_app, fleet["emails"]["AUDITOR"])
    day: date = fleet["days"][1]  # Retailer A 30 and Retailer D 80 packets
    plan = auditor.get("/api/transport/plan", params={"on": day.isoformat()}).json()
    assert plan["unplanned"] == [] and "straight-line" in plan["note"]
    route = plan["routes"][0]
    assert {s["customer"] for s in route["stops"]} == {"DEMO Retailer A", "DEMO Retailer D"}
    assert route["cartons"] == 6 and route["vehicle"] == "DEMO mini truck"  # 2 + 4 cartons of 20
    shares = [Decimal(s["cost_share"]) for s in route["stops"]]
    assert sum(shares) == Decimal(route["cost"]["value"])  # the shares add up to the trip cost
    assert "DEMO Flour Mills" in route["backhaul"][0]["text"]  # the supplier is on the Karur road
    assert route["co2"]["method"].startswith("estimate")

    assert auditor.post("/api/transport/trips", json={"on": day.isoformat()}).status_code == 403
    made = admin.post("/api/transport/trips", json={"on": day.isoformat()})
    assert made.status_code == 201, made.text
    assert made.json()["trips"][0].startswith("TRP/")
    again = admin.post("/api/transport/trips", json={"on": day.isoformat()})
    assert again.status_code == 422 and again.json()["error"]["code"] == "nothing_to_plan"  # never planned twice

    trip = next(t for t in admin.get("/api/transport/trips").json()["trips"] if t["trip_date"] == day.isoformat())
    assert trip["status"] == "PLANNED" and trip["actual_cost"] is None
    url = f"/api/transport/trips/{trip['id']}/complete"
    assert admin.post(url, json={"actual_km": "-1"}).status_code == 422
    assert admin.post(url, json={"actual_km": "200", "tolls": "85"}).json()["status"] == "DONE"
    done = next(t for t in admin.get("/api/transport/trips").json()["trips"] if t["id"] == trip["id"])
    assert done["actual_km"] == "200" and done["actual_cost"]["inputs"][5]["value"] == "85.00"
    twice = admin.post(url, json={"actual_km": "200"})
    assert twice.status_code == 409 and twice.json()["error"]["code"] == "trip_done"


def test_cost_to_serve_and_the_deal_desk_floor(api_app: Any, fleet: dict[str, Any]) -> None:
    owner = login_client(api_app, fleet["emails"]["OWNER"])
    owner.post("/api/transport/trips", json={"on": fleet["days"][0].isoformat()})
    body = owner.get("/api/transport/cost-to-serve", params={"days": 30}).json()
    rows = {r["customer_code"]: r for r in body["rows"]}
    assert {"RET-A", "RET-C"} <= set(rows)
    a = rows["RET-A"]
    assert a["total"]["method"] == "cost-to-serve" and int(a["packets"]) > 0
    assert a["price_floor"]["method"] == "Deal Desk floor, ex tax"
    floor = a["price_floor"]["inputs"]
    assert floor[1]["value"] == a["per_packet"]["value"]
    assert owner.get("/api/transport/cost-to-serve", params={"days": 0}).status_code == 422


def test_locations_and_vehicles_are_master_data(api_app: Any, fleet: dict[str, Any]) -> None:
    auditor = login_client(api_app, fleet["emails"]["AUDITOR"])
    owner = login_client(api_app, fleet["emails"]["OWNER"])
    vehicles = auditor.get("/api/transport/vehicles").json()["vehicles"]
    assert [v["name"] for v in vehicles] == ["DEMO mini truck", "DEMO two-wheeler"]
    body = {
        "name": "DEMO van",
        "capacity_cartons": 20,
        "fuel_l_per_100km": "8",
        "driver_allowance": "400",
        "fixed_cost": "200",
    }
    assert auditor.post("/api/transport/vehicles", json=body).status_code == 403
    assert owner.post("/api/transport/vehicles", json=body).status_code == 201
    assert owner.post("/api/transport/vehicles", json=body).status_code == 409
    assert "DEMO vehicles" in fleet["added"]
    bad = owner.put(f"/api/transport/customers/{vehicles[0]['id']}/location", json={"latitude": "91", "longitude": "0"})
    assert bad.status_code == 422


def test_without_settings_or_locations_it_says_what_is_missing(
    api_app: Any, owner_engine: Engine, app_engine: Engine
) -> None:
    _, emails, _ = _factory(owner_engine, app_engine, "NOTRANSPORT", settings=False)
    owner = login_client(api_app, emails["OWNER"])
    r = owner.get("/api/transport/plan")
    assert r.status_code == 422 and r.json()["error"]["code"] == "setting_missing"
