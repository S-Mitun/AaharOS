"""Purchase receipts against PostgreSQL through the real API (MP05): posting at accepted qty x rate, a duplicate
submit giving one receipt, 409 on a reused key, reversal, gapless GRN numbers, the register and valuation."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, func, select, text

from app.modules.ledger import service as ledger
from app.modules.ledger.models import Lot, StockJournal
from app.modules.procurement import service as procurement
from app.modules.valuation import service as valuation
from tests.db.conftest import Staff, login_client, make_staff, scoped_session

D = Decimal


@pytest.fixture
def shop(owner_engine: Engine, app_engine: Engine) -> tuple[Staff, uuid.UUID]:
    """A fresh tenant with logins, the standard locations and one DEMO supplier."""
    staff = make_staff(owner_engine, "PROC")
    s = scoped_session(app_engine, staff.tenant)
    ledger.ensure_locations(s, staff.tenant.org)
    supplier = procurement.create_supplier(
        s, organization_id=staff.tenant.org, actor_id=None, code="SUP-1", name="DEMO Flour Mills", state_code="33"
    )
    s.commit()
    s.close()
    return staff, supplier


def body(staff: Staff, supplier: uuid.UUID, **line: Any) -> dict[str, Any]:
    return {
        "supplier_id": str(supplier),
        "supplier_invoice_ref": "DEMO-INV-1",
        "received_on": "2026-11-21",
        "lines": [{"item_id": str(staff.tenant.items["flour"]), "qty": "60", "unit": "kg", "rate": "45", **line}],
    }


def test_receipt_posts_at_accepted_qty_times_rate(
    api_app: Any, shop: tuple[Staff, uuid.UUID], app_engine: Engine
) -> None:
    staff, supplier = shop
    client = login_client(api_app, staff.emails["PRODUCTION"])
    r = client.post("/api/purchases/receipts", json=body(staff, supplier))
    assert r.status_code == 201, r.text
    receipt = r.json()
    assert (receipt["receipt_no"], receipt["status"], receipt["stock_value"]) == (
        "GRN/26-27/000001",
        "POSTED",
        "2700.00",
    )
    s = scoped_session(app_engine, staff.tenant)
    assert ledger.balance(s, staff.tenant.items["flour"], "RAW_STORE") == (D(60000), D("2700.00"))
    assert valuation.wac(s, staff.tenant.items["flour"]).value == D("45.000000")
    s.close()


def test_duplicate_submit_gives_one_receipt(api_app: Any, shop: tuple[Staff, uuid.UUID], app_engine: Engine) -> None:
    staff, supplier = shop
    client = login_client(api_app, staff.emails["OWNER"])
    key = {"Idempotency-Key": str(uuid.uuid4())}
    first = client.post("/api/purchases/receipts", json=body(staff, supplier), headers=key)
    again = client.post(
        "/api/purchases/receipts", json=body(staff, supplier, qty="60000", unit="g", rate="0.045"), headers=key
    )
    assert (first.status_code, again.status_code) == (201, 200), again.text
    assert again.json()["id"] == first.json()["id"] and again.json()["replayed"] is True
    conflict = client.post("/api/purchases/receipts", json=body(staff, supplier, qty="61"), headers=key)
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_key_reused"
    s = scoped_session(app_engine, staff.tenant)
    assert s.execute(select(func.count()).select_from(StockJournal)).scalar_one() == 1
    assert ledger.balance(s, staff.tenant.items["flour"], "RAW_STORE")[0] == D(60000)
    s.close()


def test_rejection_freight_and_supplier_lot(api_app: Any, shop: tuple[Staff, uuid.UUID], app_engine: Engine) -> None:
    staff, supplier = shop
    client = login_client(api_app, staff.emails["PRODUCTION"])
    line = {
        "item_id": str(staff.tenant.items["pouch_200g"]),
        "qty": "500",
        "unit": "piece",
        "rate": "2.50",
        "freight": "40.00",
        "rejected_qty": "20",
        "lot_no": "P-77",
        "mfg_date": "2026-11-01",
        "best_before": "2027-11-01",
    }
    r = client.post("/api/purchases/receipts", json={**body(staff, supplier), "lines": [line]})
    assert r.status_code == 201, r.text
    assert (r.json()["stock_value"], r.json()["freight_excluded_from_stock"]) == ("1200.00", "40.00")
    s = scoped_session(app_engine, staff.tenant)
    assert ledger.balance(s, staff.tenant.items["pouch_200g"], "PACK_STORE") == (D(480), D("1200.00"))
    lot = s.execute(select(Lot).where(Lot.lot_no == "P-77")).scalar_one()
    assert (lot.source_type, lot.best_before) == ("purchase_receipt", date(2027, 11, 1))
    s.close()

    register = login_client(api_app, staff.emails["AUDITOR"]).get("/api/purchases/register").json()
    assert register["totals"] == {"receipts": 1, "stock_value": "1200.00", "freight_excluded_from_stock": "40.00"}
    assert register["rows"][0]["rejected_base"] == "20"


def test_floats_and_bad_input_are_refused(api_app: Any, shop: tuple[Staff, uuid.UUID]) -> None:
    staff, supplier = shop
    client = login_client(api_app, staff.emails["PRODUCTION"])
    float_body = body(staff, supplier)
    float_body["lines"][0]["qty"] = 60.5
    assert client.post("/api/purchases/receipts", json=float_body).status_code == 422
    fg = body(staff, supplier, item_id=str(staff.tenant.items["murukku_200g"]), unit="packet")
    r = client.post("/api/purchases/receipts", json=fg)
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_purchasable"
    r = client.post("/api/purchases/receipts", json={**body(staff, supplier), "supplier_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_reversal_and_its_refusals(api_app: Any, shop: tuple[Staff, uuid.UUID], app_engine: Engine) -> None:
    staff, supplier = shop
    client = login_client(api_app, staff.emails["PRODUCTION"])
    keep = client.post("/api/purchases/receipts", json=body(staff, supplier)).json()
    wrong = client.post("/api/purchases/receipts", json=body(staff, supplier, qty="10", rate="50")).json()

    r = client.post(f"/api/purchases/receipts/{wrong['id']}/reverse", json={"reason": "wrong supplier invoice"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "REVERSED"
    again = client.post(f"/api/purchases/receipts/{wrong['id']}/reverse", json={"reason": "again"})
    assert again.status_code == 422 and again.json()["error"]["code"] == "not_posted"

    s = scoped_session(app_engine, staff.tenant)
    flour = staff.tenant.items["flour"]
    assert ledger.balance(s, flour, "RAW_STORE") == (D(60000), D("2700.00"))  # only the kept receipt remains
    value = valuation.issue_value(
        s, organization_id=staff.tenant.org, item_id=flour, qty_base=D(50000), from_location="RAW_STORE"
    )
    ledger.post(
        s,
        organization_id=staff.tenant.org,
        actor_id=None,
        kind="ISSUE",
        source_type="material_issue",
        source_id=uuid.uuid4(),
        posting_date=date(2026, 11, 21),
        lines=[ledger_line(flour, "WIP", "50000", value), ledger_line(flour, "RAW_STORE", "-50000", -value)],
    )
    s.commit()
    s.close()
    blocked = client.post(f"/api/purchases/receipts/{keep['id']}/reverse", json={"reason": "late return"})
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "negative_stock"
    assert client.get(f"/api/purchases/receipts/{keep['id']}").json()["status"] == "POSTED"  # nothing changed


def test_grn_numbers_stay_gapless_when_a_receipt_is_refused(
    api_app: Any, shop: tuple[Staff, uuid.UUID], owner_engine: Engine
) -> None:
    staff, supplier = shop
    with owner_engine.begin() as c:
        c.execute(
            text("INSERT INTO period_locks (organization_id, period, reason) VALUES (:o, '2026-10-01', 'closed')"),
            {"o": staff.tenant.org},
        )
    client = login_client(api_app, staff.emails["PRODUCTION"])
    refused = client.post("/api/purchases/receipts", json={**body(staff, supplier), "received_on": "2026-10-15"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "period_locked"
    ok = client.post("/api/purchases/receipts", json=body(staff, supplier))
    assert ok.json()["receipt_no"] == "GRN/26-27/000001"


def test_valuation_route_explains_the_average(api_app: Any, shop: tuple[Staff, uuid.UUID]) -> None:
    staff, supplier = shop
    client = login_client(api_app, staff.emails["ADMIN"])
    assert client.post("/api/purchases/receipts", json=body(staff, supplier)).status_code == 403  # ADMIN: no receipts
    owner = login_client(api_app, staff.emails["OWNER"])
    owner.post("/api/purchases/receipts", json=body(staff, supplier))
    items = client.get("/api/stock/valuation").json()["items"]
    (flour,) = [i for i in items if i["item_code"] == "flour"]
    assert flour["average_cost"]["value"] == "45.000000" and flour["average_cost"]["unit"] == "INR/kg"
    assert flour["average_cost"]["formula"] == "pool value / pool quantity"
    salesman = login_client(api_app, staff.emails["SALESMAN"])
    assert salesman.get("/api/stock/valuation").status_code == 403  # cost is never shown to a salesman


# ---------- helpers ----------


def ledger_line(item: uuid.UUID, location: str, qty: str, value: Decimal) -> Any:
    from app.modules.ledger.domain import LineSpec

    return LineSpec(item, location, D(qty), "g", value)
