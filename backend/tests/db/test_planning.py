"""Planning against PostgreSQL (MP12, ADR-0019, module 2): the batch plan reads open demand, approving creates only
DRAFT documents, who may do what, and draft lines are never edited or deleted."""

from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.db.conftest import login_client, sqlstate
from tests.db.test_billing import Factory, approved_order, factory  # noqa: F401 - the fixture is reused


def test_plan_reads_backorders_and_suggests_purchases(api_app: Any, factory: Factory, app_engine: Engine) -> None:  # noqa: F811
    approved_order(app_engine, factory, factory.dist_b, 300)  # 238 held, 62 backordered
    auditor = login_client(api_app, factory.emails["AUDITOR"])
    plan = auditor.get("/api/planning/plan").json()
    demand = {d["item_code"]: d for d in plan["demand"]}
    assert demand["murukku_200g"]["open_packets"] == "62" and demand["murukku_200g"]["shortfall"] == "62"
    assert plan["capacity"] == "2" and plan["status"] in ("OPTIMAL", "FEASIBLE")
    batch = plan["batches"][0]
    assert batch["batches"]["value"] == "0"  # this tenant holds no raw material
    buy = {p["item_code"]: p for p in plan["purchases"]}
    assert set(buy) >= {"flour", "cooking_oil", "spice_mix", "pouch_200g", "carton_20"}
    assert buy["pouch_200g"]["qty_base"] == "500"  # 200 + 200 safety, rounded up to the minimum order of 500
    assert buy["pouch_200g"]["explained"]["method"] == "Suggested purchase"
    assert "Nothing is posted" in plan["note"]


def test_approving_creates_drafts_only(api_app: Any, factory: Factory, app_engine: Engine) -> None:  # noqa: F811
    approved_order(app_engine, factory, factory.dist_b, 300)
    owner = login_client(api_app, factory.emails["OWNER"])
    admin = login_client(api_app, factory.emails["ADMIN"])
    auditor = login_client(api_app, factory.emails["AUDITOR"])
    plan = owner.get("/api/planning/plan").json()
    batch = plan["batches"][0]
    body = {"recipe_version_id": batch["recipe_version_id"], "pack_version_id": batch["pack_version_id"], "batches": 1}

    assert admin.post("/api/planning/batches", json=body).status_code == 403  # starting batches is the floor's
    assert auditor.post("/api/planning/batches", json=body).status_code == 403
    assert owner.post("/api/planning/batches", json={**body, "batches": 0}).status_code == 422
    made = owner.post("/api/planning/batches", json=body)
    assert made.status_code == 201 and made.json()["status"] == "DRAFT"
    runs = owner.get("/api/runs").json()
    run = next(r for r in runs["runs"] if r["id"] == made.json()["run_id"])
    assert run["status"] == "DRAFT"

    lines = [
        {"item_id": p["item_id"], "qty_base": p["qty_base"], "needed_by": p["needed_by"], "reason": "planner"}
        for p in plan["purchases"]
    ]
    assert admin.post("/api/planning/purchase-drafts", json={"lines": lines}).status_code == 403
    assert owner.post("/api/planning/purchase-drafts", json={"lines": []}).status_code == 422
    bad = [{**lines[0], "qty_base": "-1"}]
    assert owner.post("/api/planning/purchase-drafts", json={"lines": bad}).status_code == 422
    draft = owner.post("/api/planning/purchase-drafts", json={"lines": lines, "note": "DEMO"})
    assert draft.status_code == 201 and draft.json()["draft_no"].startswith("DPO/")
    listed = auditor.get("/api/planning/purchase-drafts").json()["drafts"]
    assert listed[0]["status"] == "DRAFT" and len(listed[0]["lines"]) == len(lines)

    url = f"/api/planning/purchase-drafts/{draft.json()['id']}/cancel"
    assert owner.post(url, json={"reason": ""}).status_code == 422
    assert owner.post(url, json={"reason": "DEMO: bought locally"}).json()["status"] == "CANCELLED"
    again = owner.post(url, json={"reason": "DEMO: twice"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "draft_already_cancelled"


def test_item_settings_are_master_data(api_app: Any, factory: Factory) -> None:  # noqa: F811
    admin = login_client(api_app, factory.emails["ADMIN"])
    auditor = login_client(api_app, factory.emails["AUDITOR"])
    items = {i["item_code"]: i for i in auditor.get("/api/planning/item-settings").json()["items"]}
    assert items["pouch_200g"]["min_order_base"] == "500" and items["pouch_200g"]["lead_time_days"] == 7
    body = {"reorder_level_base": "400", "safety_stock_base": "250", "min_order_base": "1000", "lead_time_days": 5}
    url = f"/api/planning/item-settings/{items['pouch_200g']['item_id']}"
    assert auditor.put(url, json=body).status_code == 403
    assert admin.put(url, json={**body, "lead_time_days": 400}).status_code == 422
    assert admin.put(url, json=body).status_code == 200
    items = {i["item_code"]: i for i in auditor.get("/api/planning/item-settings").json()["items"]}
    assert items["pouch_200g"]["min_order_base"] == "1000"


def test_draft_lines_are_never_edited_or_deleted(
    api_app: Any,
    factory: Factory,  # noqa: F811
    owner_engine: Engine,
    app_engine: Engine,
) -> None:
    owner = login_client(api_app, factory.emails["OWNER"])
    item = owner.get("/api/planning/item-settings").json()["items"][0]["item_id"]
    line = {"item_id": item, "qty_base": "10", "needed_by": "2026-12-01"}
    assert owner.post("/api/planning/purchase-drafts", json={"lines": [line]}).status_code == 201
    for sql in (
        "UPDATE draft_purchase_order_lines SET qty_base = 1 WHERE organization_id = :o",
        "DELETE FROM draft_purchase_order_lines WHERE organization_id = :o",
    ):
        with pytest.raises(DBAPIError) as e, owner_engine.begin() as c:
            c.execute(text(sql), {"o": factory.org})
        assert sqlstate(e.value) == "AH002", sql
    with pytest.raises(DBAPIError) as e, app_engine.begin() as c:
        c.execute(text("DELETE FROM draft_purchase_orders WHERE organization_id = :o"), {"o": factory.org})
    assert sqlstate(e.value) == "42501"  # the app role holds no DELETE on drafts
