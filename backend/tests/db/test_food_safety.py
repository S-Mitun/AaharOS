"""The DEMO history, the oil log and fill weights against PostgreSQL (MP13, ADR-0020, module 2): the history posts
once through the real services and keeps every integrity check green; the oil log and fill weights read what batch
completion recorded, against effective-dated DEMO settings."""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.cli import demo_history
from app.core.calendar import business_date
from app.core.db import org_scope
from app.core.oracle import load_oracle
from app.modules.identity import service as identity
from app.modules.judge.replay import post_section5_opening, setup_section5, setup_section5_food_safety
from app.modules.reports import close
from tests.db.conftest import BACKEND, Tenant, add_member, login_client

ORACLE = BACKEND.parent / "benchmark" / "expected_results.yaml"


def _factory(
    owner_engine: Engine, app_engine: Engine, label: str, settings: bool
) -> tuple[uuid.UUID, dict[str, str], dict[str, uuid.UUID]]:
    with Session(app_engine, expire_on_commit=False) as s:
        org = identity.create_scratch_tenant(s, kind="SIM", label=label)
        s5 = setup_section5(s, load_oracle(ORACLE), org)
        post_section5_opening(s, load_oracle(ORACLE), s5)
        if settings:
            setup_section5_food_safety(s, org)
        s.commit()
    t = Tenant(org=org, items=s5.item_ids, locations={}, customer=s5.customer_ids["RET-A"])
    emails, ids = {}, {}
    for role, key in (
        ("PRODUCTION", "PRODUCTION"),
        ("ADMIN", "ADMIN"),
        ("SALESMAN", "SALESMAN_A"),
        ("SALESMAN", "SALESMAN_B"),
        ("AUDITOR", "AUDITOR"),
        ("OWNER", "OWNER"),
    ):
        ids[key], emails[key] = add_member(owner_engine, t, role, key)
    return org, emails, ids


@pytest.fixture(scope="module")
def demo(owner_engine: Engine, app_engine: Engine) -> dict[str, Any]:
    org, emails, ids = _factory(owner_engine, app_engine, "HIST", settings=True)
    with Session(app_engine, expire_on_commit=False) as s:
        org_scope(s, org)
        added = demo_history.seed_history(s, org, ids, start=business_date() - timedelta(days=5))
        s.commit()
        again = demo_history.seed_history(s, org, ids)
        checks = close.integrity_checks(s, org)
    return {"org": org, "emails": emails, "added": added, "again": again, "checks": checks}


def test_the_history_is_posted_once_and_keeps_the_books_whole(demo: dict[str, Any]) -> None:
    assert demo["added"][1] == "batches B-001, B-002, B-003 with oil sessions and fill samples"
    assert demo["added"][2].startswith("6 orders") and demo["again"] == []
    failing = [c for c in demo["checks"] if not c["ok"]]
    assert failing == [], failing


def test_the_history_traces_supplier_lots_to_batches_and_retailers(api_app: Any, demo: dict[str, Any]) -> None:
    owner = login_client(api_app, demo["emails"]["OWNER"])
    lots = {lot["lot_no"]: lot["lot_id"] for lot in owner.get("/api/trace/lots", params={"q": "DEMO-"}).json()["lots"]}
    assert set(lots) == {"DEMO-FL-01", "DEMO-FL-02", "DEMO-PCH-01", "DEMO-SP-01", "DEMO-OIL-01"}
    fl2 = owner.get(f"/api/trace/lots/{lots['DEMO-FL-02']}").json()
    assert [b["run_no"] for b in fl2["backward"]["batches"]] == ["B-002", "B-003"]  # it arrived after B-001
    recall = owner.get(f"/api/trace/recall/{lots['DEMO-FL-01']}").json()
    assert {c["customer_code"] for c in recall["customers"]} == {"RET-A", "RET-C", "RET-D"}


def test_the_oil_log_against_ruco_and_tpc(api_app: Any, demo: dict[str, Any]) -> None:
    production = login_client(api_app, demo["emails"]["PRODUCTION"])
    oil = production.get("/api/trace/oil", params={"days": 30}).json()
    assert (oil["threshold_l_per_day"], oil["tpc_limit_pct"], oil["records_required"]) == ("50", "25", False)
    litres = [d["litres"]["value"] for d in oil["days"]]
    assert litres == ["10.2", "10.3", "10.5"]  # newest first; fresh oil + top-ups
    assert oil["days"][2]["litres"]["inputs"][0]["source"]["type"] == "production_run"
    flags = [(s["run_no"], s["tpc_pct"], s["discard_oil"]) for d in oil["days"] for s in d["sessions"]]
    assert flags == [("B-003", "26", True), ("B-002", "18.5", False), ("B-001", "12", False)]
    assert production.get("/api/trace/oil", params={"days": 0}).status_code == 422


def test_fill_weights_giveaway_and_short_fills(api_app: Any, demo: dict[str, Any]) -> None:
    auditor = login_client(api_app, demo["emails"]["AUDITOR"])
    fill = auditor.get("/api/trace/fill-weights").json()
    assert fill["tolerances"] == [{"declared_g": "200", "tolerance_g": "9"}, {"declared_g": "500", "tolerance_g": "15"}]
    assert "Legal Metrology" in fill["note"]
    runs = {r["run_no"]: r for r in fill["runs"]}
    b1 = runs["B-001"]
    assert (b1["mean_net"]["value"], b1["over_per_packet"]["value"]) == ("203.8", "3.8")
    # ingredients 1,720.00 flour (40 kg at WAC 43.00) + 1,470.00 oil + 240.00 spice over the 40 kg recipe bulk
    assert b1["cost_per_kg"]["value"] == "85.75"
    assert b1["giveaway"]["value"] == str((Decimal("3.8") * 190 * Decimal("85.75") / 1000).quantize(Decimal("0.01")))
    assert b1["short_fill_alert"] is False
    b3 = runs["B-003"]
    assert (b3["short_limit_g"], b3["short_samples"], b3["short_fill_alert"]) == ("191", ["190"], True)
    assert b3["giveaway"]["value"] == "0.00"  # under-filled on average: no giveaway
    salesman = login_client(api_app, demo["emails"]["SALESMAN_A"])
    assert salesman.get("/api/trace/fill-weights").status_code == 403


def test_without_settings_the_oil_log_says_what_is_missing(
    api_app: Any, owner_engine: Engine, app_engine: Engine
) -> None:
    _, emails, _ = _factory(owner_engine, app_engine, "NOSET", settings=False)
    owner = login_client(api_app, emails["OWNER"])
    r = owner.get("/api/trace/oil")
    assert r.status_code == 422 and r.json()["error"]["code"] == "setting_missing"
    fill = owner.get("/api/trace/fill-weights").json()
    assert fill["tolerances"] == [] and fill["runs"] == []
