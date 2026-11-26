"""Trace and recall against PostgreSQL (MP13, ADR-0020, module 1): B-001 on the NIT replay, and a tenant with
supplier lots where the flour store runs empty between batches, so the "may contain" window must name exactly the
batches a flour lot could be in, and never miss one."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.calendar import business_date
from app.core.oracle import load_oracle
from app.modules.billing import service as billing
from app.modules.dispatch import service as dispatch
from app.modules.identity import service as identity
from app.modules.judge.replay import PACK_200G, replay_stock, setup_section5
from app.modules.ledger import service as ledger
from app.modules.procurement import service as procurement
from app.modules.procurement.domain import ReceiptLineIn
from app.modules.production import service as production
from app.modules.sales import service as sales
from app.modules.sales.domain import OrderLineIn
from tests.db.conftest import BACKEND, Tenant, add_member, login_client

D = Decimal
ORACLE = BACKEND.parent / "benchmark" / "expected_results.yaml"


@dataclass
class Traced:
    org: uuid.UUID
    emails: dict[str, str]
    lots: dict[str, uuid.UUID]  # supplier lot no / batch no -> lot id
    runs: dict[str, str]  # B-001 .. B-003 -> run id
    invoices: dict[str, str]  # customer code -> invoice no


def _batch(
    s: Session,
    org: uuid.UUID,
    actor: uuid.UUID,
    s5: Any,
    on: date,
    issues: list[tuple[date, dict[str, str]]],
    good: int,
    between: Any = None,
) -> uuid.UUID:
    ids = s5.item_ids
    run = production.create_run(
        s,
        organization_id=org,
        actor_id=actor,
        recipe_version_id=s5.recipe_version_id,
        batch_multiplier=D(1),
        run_date=on,
        pack_lines=[production.PackLineRequest(s5.pack_versions[PACK_200G[0]])],
    )
    production.start_run(s, organization_id=org, actor_id=actor, run_id=run)
    units = {"flour": "kg", "cooking_oil": "L", "spice_mix": "kg"}
    for n, (day, lines) in enumerate(issues):
        if n == 1 and between is not None:
            between()
        production.issue_materials(
            s,
            organization_id=org,
            actor_id=actor,
            run_id=run,
            posting_date=day,
            lines=[production.MaterialLineIn(ids[c], D(q), units[c]) for c, q in lines.items()],
        )
    pack_line = production.run_analysis(s, run).pack_lines[0].pack_line_id
    production.complete_run(
        s,
        organization_id=org,
        actor_id=actor,
        run_id=run,
        posting_date=on,
        results=[
            production.PackResultIn(
                pack_line_id=pack_line,
                good_units=good,
                packaging=[
                    production.PackagingIn(ids["pouch_200g"], D(good + 2), D(2), "piece"),
                    production.PackagingIn(ids["carton_20"], D(good // 20), D(0), "piece"),
                ],
            )
        ],
    )
    return run


@pytest.fixture(scope="module")
def traced(owner_engine: Engine, app_engine: Engine) -> Traced:
    """Day 0: flour FL-A 50 kg, oil OIL-A, spice SP-A, pouches P-A. B-001 takes 40 kg; B-002 takes the last 10 kg
    (the flour store is empty), then FL-B 50 kg arrives and B-002 takes 30 kg more; B-003 takes the last 20 kg.
    So FL-A may be in B-001 and B-002 only, FL-B in B-002 and B-003 only. Retailer A gets 150 packets (B-001),
    Distributor B 100 (B-001 then B-002, FEFO)."""
    oracle = load_oracle(ORACLE)
    today = business_date()
    d0 = today - timedelta(days=12)
    with Session(app_engine, expire_on_commit=False) as s:
        org = identity.create_scratch_tenant(s, kind="SIM", label="TRACE")
        s5 = setup_section5(s, oracle, org)
        s.commit()
    t = Tenant(org=org, items=s5.item_ids, locations={}, customer=s5.customer_ids["RET-A"])
    emails: dict[str, str] = {}
    users: dict[str, uuid.UUID] = {}
    for role in ("OWNER", "AUDITOR", "SALESMAN", "PRODUCTION"):
        users[role], emails[role] = add_member(owner_engine, t, role)
    actor = users["PRODUCTION"]
    ids = s5.item_ids
    with Session(app_engine, expire_on_commit=False) as s:
        from app.core.db import org_scope

        org_scope(s, org)

        def receive(on: date, lines: list[ReceiptLineIn]) -> None:
            procurement.post_receipt(
                s,
                organization_id=org,
                actor_id=actor,
                supplier_id=s5.supplier_id,
                supplier_invoice_ref=f"DEMO-{on.isoformat()}",
                received_on=on,
                lines=lines,
            )

        receive(
            d0,
            [
                ReceiptLineIn(ids["flour"], D(50), "kg", D(45), lot_no="FL-A"),
                ReceiptLineIn(ids["cooking_oil"], D(40), "L", D(140), lot_no="OIL-A"),
                ReceiptLineIn(ids["spice_mix"], D(5), "kg", D(200), lot_no="SP-A"),
                ReceiptLineIn(ids["pouch_200g"], D(700), "piece", D("2.50"), lot_no="P-A"),
                ReceiptLineIn(ids["carton_20"], D(40), "piece", D(15)),
            ],
        )
        oil = {"cooking_oil": "10", "spice_mix": "1.2"}
        b1 = _batch(s, org, actor, s5, d0 + timedelta(days=1), [(d0 + timedelta(days=1), {"flour": "40", **oil})], 190)
        d2 = d0 + timedelta(days=3)
        b2 = _batch(
            s,
            org,
            actor,
            s5,
            d2,
            [(d2, {"flour": "10", **oil}), (d2, {"flour": "30"})],
            180,
            between=lambda: receive(d2, [ReceiptLineIn(ids["flour"], D(50), "kg", D(46), lot_no="FL-B")]),
        )
        d3 = d0 + timedelta(days=5)
        b3 = _batch(s, org, actor, s5, d3, [(d3, {"flour": "20", **oil})], 90)

        invoices = {}
        for code, qty in (("RET-A", 150), ("DIST-B", 100)):
            placed = sales.receive_order(
                s,
                organization_id=org,
                actor_id=None,
                customer_id=s5.customer_ids[code],
                price_list_id=s5.price_list_id,
                lines=[OrderLineIn(ids["murukku_200g"], qty, D("50.00"))],
                order_date=d0 + timedelta(days=6),
            )
            sales.approve_order(s, organization_id=org, actor_id=None, order_id=placed.order_id)
            inv = billing.create_invoice(
                s, organization_id=org, actor_id=None, order_id=placed.order_id, invoice_date=d0 + timedelta(days=6)
            )
            dispatch.dispatch_invoice(
                s, organization_id=org, actor_id=None, invoice_id=inv.invoice_id, dispatch_date=d0 + timedelta(days=6)
            )
            invoices[code] = billing.invoice_view(s, inv.invoice_id)["invoice_no"]
        s.commit()
        runs = production.trace_runs(s, [b1, b2, b3])
        lots = {f.lot_no: f.id for f in ledger.lots_where(s)}
    return Traced(org, emails, lots, {v["run_no"]: str(k) for k, v in runs.items()}, invoices)


def _batches(body: dict[str, Any]) -> list[str]:
    return [b["run_no"] for b in body["backward"]["batches"]]


def test_a_flour_lot_may_be_in_the_batches_before_the_store_ran_out(api_app: Any, traced: Traced) -> None:
    auditor = login_client(api_app, traced.emails["AUDITOR"])
    fl_a = auditor.get(f"/api/trace/lots/{traced.lots['FL-A']}").json()
    assert fl_a["lot"]["kind"] == "supplier_lot" and _batches(fl_a) == ["B-001", "B-002"]
    assert fl_a["backward"]["may_still_be_in_store"] is False  # the store ran empty on B-002's first issue
    assert fl_a["backward"]["receipts"][0]["accepted"]["value"] == "50" and "never miss" in fl_a["note"]
    fl_b = auditor.get(f"/api/trace/lots/{traced.lots['FL-B']}").json()
    assert _batches(fl_b) == ["B-002", "B-003"]  # FL-B arrived after the store ran empty: not in B-001
    b2 = next(b for b in fl_b["backward"]["batches"] if b["run_no"] == "B-002")
    assert [i["qty"]["value"] for i in b2["issues"]] == ["30"]  # only the issue after FL-B arrived
    oil = auditor.get(f"/api/trace/lots/{traced.lots['OIL-A']}").json()
    assert _batches(oil) == ["B-001", "B-002", "B-003"] and oil["backward"]["may_still_be_in_store"] is True
    pouches = auditor.get(f"/api/trace/lots/{traced.lots['P-A']}").json()  # packing, consumed at completion
    assert _batches(pouches) == ["B-001", "B-002", "B-003"]


def test_a_batch_lot_traces_back_to_its_supplier_lots_and_forward_to_customers(api_app: Any, traced: Traced) -> None:
    owner = login_client(api_app, traced.emails["OWNER"])
    body = owner.get(f"/api/trace/lots/{traced.lots['B-002']}").json()
    back = body["backward"]
    assert back["batch"]["run_no"] == "B-002" and back["batch"]["recipe"]["code"] == "MURUKKU"
    assert back["batch"]["packs"][0]["code"] == "MURUKKU-200G" and back["batch"]["operator"] == "DEMO PRODUCTION"
    flour = [m for m in back["materials"] if m["item_code"] == "flour"]
    assert [(m["qty"]["value"], [c["lot_no"] for c in m["may_contain"]]) for m in flour] == [
        ("10", ["FL-A"]),
        ("30", ["FL-B"]),  # the first issue emptied the store, so the second can hold FL-B only
    ]
    assert flour[0]["source"]["type"] == "material_issue" and flour[0]["document"].startswith("MI/")
    cartons = next(m for m in back["materials"] if m["item_code"] == "carton_20")
    assert [c["kind"] for c in cartons["may_contain"]] == ["no_lot"]  # received without a supplier lot
    assert "no supplier lot recorded" in cartons["may_contain"][0]["label"]
    fwd = body["forward"][0]
    assert (fwd["made"]["value"], fwd["dispatched"]["value"], fwd["on_hand"]["value"]) == ("180", "60", "120")
    assert [(d["customer_code"], d["packets"], d["invoice_no"]) for d in fwd["dispatches"]] == [
        ("DIST-B", "60", traced.invoices["DIST-B"])
    ]


def test_the_recall_lists_customers_invoices_and_a_demo_notice(api_app: Any, traced: Traced) -> None:
    owner = login_client(api_app, traced.emails["OWNER"])
    r = owner.get(f"/api/trace/recall/{traced.lots['FL-A']}", params={"reason": "DEMO: stones in flour"}).json()
    assert r["simulation"] is True and "nothing is sent" in r["note"]
    assert [b["run_no"] for b in r["batches"]] == ["B-001", "B-002"]
    assert [lot["lot_no"] for lot in r["lots"]] == ["B-001", "B-002"]
    assert [(c["customer_code"], c["packets"]["value"], c["invoice_nos"]) for c in r["customers"]] == [
        ("RET-A", "150", [traced.invoices["RET-A"]]),
        ("DIST-B", "100", [traced.invoices["DIST-B"]]),  # 40 of B-001 and 60 of B-002 on one invoice
    ]
    t = r["totals"]
    assert (t["made"]["value"], t["dispatched"]["value"], t["on_hand"]["value"]) == ("370", "250", "120")
    assert r["notice"].startswith("DEMO SIMULATION - NOTHING HAS BEEN SENT")
    assert "DEMO: stones in flour" in r["notice"] and "10000000000000 (DEMO)" in r["notice"]
    one = owner.get(f"/api/trace/recall/{traced.lots['B-003']}").json()  # from a batch lot: that lot only
    assert [lot["lot_no"] for lot in one["lots"]] == ["B-003"] and one["customers"] == []
    assert "no packets of these lots have been dispatched" in one["notice"]


def test_search_and_who_may_trace(api_app: Any, traced: Traced) -> None:
    auditor = login_client(api_app, traced.emails["AUDITOR"])
    found = auditor.get("/api/trace/lots", params={"q": "fl-"}).json()["lots"]
    assert sorted(f["lot_no"] for f in found) == ["FL-A", "FL-B"]
    assert {f["kind_label"] for f in found} == {"Supplier lot"}
    assert auditor.get("/api/trace/lots", params={"q": "%"}).json()["lots"] == []  # a wildcard is a literal
    salesman = login_client(api_app, traced.emails["SALESMAN"])
    assert salesman.get(f"/api/trace/lots/{traced.lots['FL-A']}").status_code == 403
    assert salesman.get(f"/api/trace/recall/{traced.lots['FL-A']}").status_code == 403
    missing = auditor.get(f"/api/trace/lots/{uuid.uuid4()}")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "lot_not_found"
    assert auditor.get("/api/trace/lots/not-a-uuid").status_code == 422


def test_b001_on_the_nit_replay(app_engine: Engine) -> None:
    """The benchmark tenant has no supplier lots: B-001's materials come from opening stock and an unlotted
    receipt, and the forward trace shows Retailer A's 100 packets and the 88 on hand."""
    from app.core.db import org_scope
    from app.modules.traceability import service as trace

    with Session(app_engine, expire_on_commit=False) as s:
        replay = replay_stock(s, load_oracle(ORACLE))
    with Session(app_engine) as s:
        org_scope(s, replay.organization_id)
        lot = ledger.lot_id_by_no(s, replay.item_ids["murukku_200g"], "B-001")
        assert lot is not None
        body = trace.trace(s, lot)
        flour = next(m for m in body["backward"]["materials"] if m["item_code"] == "flour")
        assert flour["qty"]["value"] == "40"
        assert [c["kind"] for c in flour["may_contain"]] == ["opening", "no_lot"]
        assert flour["may_contain"][0]["label"] == "opening stock, no supplier lot recorded"
        fwd = body["forward"][0]
        assert (fwd["made"]["value"], fwd["dispatched"]["value"], fwd["on_hand"]["value"]) == ("188", "100", "88")
        assert fwd["dispatches"][0]["customer_code"] == "RET-A"
        assert fwd["dispatches"][0]["invoice_no"] == replay.invoice_a["invoice_no"]  # type: ignore[index]
        opening = trace.trace(s, ledger.lot_id_by_no(s, replay.item_ids["murukku_200g"], "OPEN-LOT"))  # type: ignore[arg-type]
        assert opening["backward"]["batch"] is None and opening["forward"][0]["dispatched"]["value"] == "50"
