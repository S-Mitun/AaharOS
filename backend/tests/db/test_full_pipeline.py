"""Full-stack regression (deployment review): one visitor signs up for a sandbox factory and runs NIT's Section 5
day through the HTTP API only, the way the web app does, then the MP11-MP14 read models on top of it. The oracle's
figures must come out of the API exactly: FG 238 after the run and 88 after the dispatch, invoice A Rs 7,875.00,
Rs 3,875.00 still owed, run cost Rs 5,855.00 and Rs 31.14 a packet. Then trace and recall, trips, cost-to-serve,
reports, the brief, and every integrity check of the tenant."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.calendar import business_date
from app.core.db import org_scope
from app.modules.reports import close

D = Decimal


def _ok(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()


def _fg_on_hand(client: TestClient, item_id: str) -> Decimal:
    rows = _ok(client.get("/api/stock/balances"))
    rows = rows["balances"] if isinstance(rows, dict) else rows
    return sum(
        (D(r["qty_base"]) for r in rows if r["item_id"] == item_id and r["location"] == "FG_STORE"),
        D(0),
    )


def test_nit_day_through_the_http_api_and_everything_built_on_it(
    api_app: Any, owner_engine: Engine, app_engine: Engine
) -> None:
    today = business_date().isoformat()
    c = TestClient(api_app)
    email = f"pipeline-{uuid.uuid4().hex[:10]}@aaharos-demo.invalid"
    made = _ok(
        c.post(
            "/api/signup",
            json={
                "factory_name": "DEMO Pipeline",
                "display_name": "DEMO Owner",
                "email": email,
                "password": "pipeline-pass-1",
            },
        ),
        201,
    )
    _ok(c.post("/api/auth/login", json={"email": email, "password": "pipeline-pass-1"}))

    # master data the sandbox came with
    items = {i["item_code"]: i["item_id"] for i in _ok(c.get("/api/planning/item-settings"))["items"]}
    customers = {x["code"]: x["id"] for x in _ok(c.get("/api/customers"))["customers"]}
    supplier = _ok(c.get("/api/suppliers"))["suppliers"][0]["id"]
    price_list = next(p for p in _ok(c.get("/api/price-lists"))["price_lists"] if p["in_force_today"])["id"]
    recipe = next(r for r in _ok(c.get("/api/recipes"))["recipes"] if r["code"] == "MURUKKU")
    recipe_version = next(v["id"] for v in recipe["versions"] if v["status"] == "ACTIVE")
    pack = next(p for p in _ok(c.get("/api/pack-specs"))["pack_specs"] if p["code"] == "MURUKKU-200G")
    pack_version = next(v["id"] for v in pack["versions"] if v["status"] == "ACTIVE")
    catalog = _ok(c.get("/api/sales/catalog", params={"customer_id": customers["RET-A"]}))
    fg = next(i for i in catalog["products"] if i["code"] == "murukku_200g")
    assert fg["price_ex_tax"] == "50.00"

    # step 1: the purchase, with a supplier lot; a retried submit with the same key is replayed, not doubled
    key = str(uuid.uuid4())
    receipt = {
        "supplier_id": supplier,
        "supplier_invoice_ref": "DEMO-PIPE-1",
        "received_on": today,
        "lines": [{"item_id": items["flour"], "qty": "60", "unit": "kg", "rate": "45.00", "lot_no": "PIPE-FL-1"}],
    }
    first = _ok(c.post("/api/purchases/receipts", json=receipt, headers={"Idempotency-Key": key}), 201)
    again = c.post("/api/purchases/receipts", json=receipt, headers={"Idempotency-Key": key})
    assert again.json()["replayed"] is True and again.json()["receipt_no"] == first["receipt_no"]

    # steps 2-3: the batch, frozen at start, issued at WAC, completed with oil and fill samples
    run = _ok(
        c.post(
            "/api/runs",
            json={
                "recipe_version_id": recipe_version,
                "run_date": today,
                "pack_lines": [{"pack_spec_version_id": pack_version}],
            },
        ),
        201,
    )
    run_id = run["id"] if "id" in run else run["run_id"]
    _ok(c.post(f"/api/runs/{run_id}/start"))
    issue = {
        "lines": [
            {"item_id": items["flour"], "qty": "40", "unit": "kg"},
            {"item_id": items["cooking_oil"], "qty": "10.5", "unit": "L"},
            {"item_id": items["spice_mix"], "qty": "1.2", "unit": "kg"},
        ]
    }
    _ok(c.post(f"/api/runs/{run_id}/issues", json=issue), 201)
    pack_line = _ok(c.get(f"/api/runs/{run_id}"))["analysis"]["pack_lines"][0]["pack_line_id"]
    done = _ok(
        c.post(
            f"/api/runs/{run_id}/complete",
            json={
                "pack_lines": [
                    {
                        "pack_line_id": pack_line,
                        "good_units": "188",
                        "packaging": [
                            {"item_id": items["pouch_200g"], "used": "194", "damaged": "6"},
                            {"item_id": items["carton_20"], "used": "9"},
                        ],
                    }
                ],
                "fill_weight_samples": [{"gross_g": "207", "net_g": "203"}, {"gross_g": "205", "net_g": "201"}],
                "oil_session": {"fresh_ml": "10000", "topup_ml": "500", "tpc_pct": "12"},
            },
        ),
        201,
    )
    assert done["status"] == "COMPLETED"
    assert _fg_on_hand(c, fg["item_id"]) == 238  # row 4

    # steps 4-5, 7: Retailer A's order, approved, invoiced, dispatched first-expiry-first-out, part paid
    order = _ok(
        c.post(
            "/api/orders",
            json={
                "customer_id": customers["RET-A"],
                "price_list_id": price_list,
                "lines": [{"item_id": fg["item_id"], "qty": "150", "price_ex_tax": "50.00"}],
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        ),
        201,
    )
    order_id = order["id"] if "id" in order else order["order_id"]
    _ok(c.post(f"/api/orders/{order_id}/approve", json={}))
    invoice = _ok(
        c.post(f"/api/orders/{order_id}/invoice", json={}, headers={"Idempotency-Key": str(uuid.uuid4())}), 201
    )
    assert (invoice["taxable"], invoice["by_tax"], invoice["total"]) == (
        "7500.00",
        {"CGST": "187.50", "SGST": "187.50"},
        "7875.00",
    )
    _ok(c.post(f"/api/invoices/{invoice['id']}/dispatch", json={}, headers={"Idempotency-Key": str(uuid.uuid4())}), 201)
    assert _fg_on_hand(c, fg["item_id"]) == 88  # row 5
    _ok(c.post("/api/payments", json={"customer_id": customers["RET-A"], "amount": "4000.00"}), 201)
    statement = _ok(c.get(f"/api/customers/{customers['RET-A']}/statement"))
    assert "3875.00" in str(statement)  # row 12

    # step 6: Distributor B asks for 120 of the 88: a full approval is refused, the card shows the 32 short
    order_b = _ok(
        c.post(
            "/api/orders",
            json={
                "customer_id": customers["DIST-B"],
                "price_list_id": price_list,
                "lines": [{"item_id": fg["item_id"], "qty": "120", "price_ex_tax": "50.00"}],
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        ),
        201,
    )
    b_id = order_b["id"] if "id" in order_b else order_b["order_id"]
    refused = c.post(f"/api/orders/{b_id}/approve", json={})
    assert refused.status_code in (409, 422)
    assert "32" in str(_ok(c.get(f"/api/inbox/{b_id}")))

    # step 8: run costs, then the costs are final: Rs 5,855.00 and Rs 31.14 a good packet
    _ok(c.post(f"/api/runs/{run_id}/costs", json={"kind": "LABOUR", "amount": "1200.00"}), 201)
    _ok(c.post(f"/api/runs/{run_id}/costs", json={"kind": "GAS_POWER", "amount": "600.00"}), 201)
    _ok(c.post(f"/api/runs/{run_id}/costs/finalise"))
    costing = _ok(c.get(f"/api/runs/{run_id}/costing"))
    assert costing["cost"]["total"]["value"] == "5855.00" and costing["cost"]["per_good_unit_display"] == "31.14"

    # MP13: the batch traces back to the supplier lot and forward to Retailer A's invoice; the recall finds them
    lots = {lot["lot_no"]: lot["lot_id"] for lot in _ok(c.get("/api/trace/lots"))["lots"]}
    batch_lot = next(lot_id for no, lot_id in lots.items() if no.startswith("B-"))
    trace = _ok(c.get(f"/api/trace/lots/{batch_lot}"))
    flour = next(m for m in trace["backward"]["materials"] if m["item_code"] == "flour")
    assert "PIPE-FL-1" in {x.get("lot_no") for x in flour["may_contain"]}
    assert trace["forward"][0]["dispatches"][0]["invoice_no"] == invoice["invoice_no"]
    recall = _ok(c.get(f"/api/trace/recall/{lots['PIPE-FL-1']}"))
    assert [x["customer_code"] for x in recall["customers"]] == ["RET-A"] and recall["simulation"] is True
    assert _ok(c.get("/api/trace/oil"))["days"][0]["litres"]["value"] == "10.5"
    assert _ok(c.get("/api/trace/fill-weights"))["runs"][0]["mean_net"]["value"] == "202"

    # MP14: today's dispatch goes on a trip; the actual km make Retailer A's cost-to-serve and floor
    plan = _ok(c.get("/api/transport/plan", params={"on": today}))
    assert plan["unplanned"] == [] and len(plan["routes"]) == 1
    trip_no = _ok(c.post("/api/transport/trips", json={"on": today}), 201)["trips"][0]
    trip = next(t for t in _ok(c.get("/api/transport/trips"))["trips"] if t["trip_no"] == trip_no)
    _ok(c.post(f"/api/transport/trips/{trip['id']}/complete", json={"actual_km": "25", "tolls": "0"}))
    serve = {r["customer_code"]: r for r in _ok(c.get("/api/transport/cost-to-serve"))["rows"]}
    assert serve["RET-A"]["packets"] == "150" and serve["RET-A"]["price_floor"] is not None

    # MP11-MP12: reports, GST, the brief and the planner read the same records
    register = _ok(c.get("/api/reports/sales-register"))
    assert invoice["invoice_no"] in str(register)
    _ok(c.get("/api/reports/gst-summary"))
    _ok(c.get("/api/planning/brief"))
    _ok(c.get("/api/planning/plan"))
    _ok(c.get("/api/trace/freshness"))

    # and the books of this tenant are whole: audit chain, laws 1-4, balance rebuild, ...
    with owner_engine.connect() as conn:
        org = conn.execute(
            text("SELECT id FROM organizations WHERE code = :c"), {"c": made["organization_code"]}
        ).scalar_one()
    with Session(app_engine) as s:
        org_scope(s, org)
        failing = [chk for chk in close.integrity_checks(s, org) if not chk["ok"]]
    assert failing == [], failing
