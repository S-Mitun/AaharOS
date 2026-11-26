"""Invoices, dispatch and collections against PostgreSQL through the real API (MP10, ADR-0017): NIT's invoice A,
the printable document, gapless numbers under concurrency, FEFO at lot value, partial dispatch, cancellation before
dispatch only, credit notes, payments with oldest-due allocation and advances, and the guards between them."""

import threading
import time
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import org_scope
from app.core.errors import DomainError
from app.core.oracle import load_oracle
from app.modules.billing import service as billing
from app.modules.identity import service as identity
from app.modules.judge.replay import setup_section5
from app.modules.ledger import service as ledger
from app.modules.sales import service as sales
from app.modules.sales.domain import OrderLineIn
from app.modules.valuation import service as valuation
from app.modules.valuation.service import OpeningLine
from tests.db.conftest import BACKEND, Tenant, add_member, login_client, scoped_session

D = Decimal
DAY = date(2026, 11, 21)


class Factory:
    def __init__(self, org: uuid.UUID, emails: dict[str, str], s5: Any, item: uuid.UUID) -> None:
        self.org, self.emails, self.s5, self.item = org, emails, s5, item
        self.ret_a = s5.customer_ids["RET-A"]
        self.dist_b = s5.customer_ids["DIST-B"]
        self.tenant = Tenant(org=org, items=s5.item_ids, locations={}, customer=self.ret_a)


@pytest.fixture
def factory(owner_engine: Engine, app_engine: Engine) -> Factory:
    """A fresh tenant with the section 5 master data (price list, GST rule, DEMO profile), logins, and 238 FG
    packets in two lots: OPEN-LOT (no date, 50 at 28.85) and B-TEST (best before Feb 2027, 188 worth 4,055.00)."""
    oracle = load_oracle(BACKEND.parent / "benchmark" / "expected_results.yaml")
    with Session(app_engine, expire_on_commit=False) as s:
        org = identity.create_scratch_tenant(s, kind="SIM", label="BILL")
        s5 = setup_section5(s, oracle, org)
        item = s5.item_ids["murukku_200g"]
        open_lot = ledger.create_lot(
            s, organization_id=org, actor_id=None, item_id=item, lot_no="OPEN-LOT", source_type="opening"
        )
        batch = ledger.create_lot(
            s,
            organization_id=org,
            actor_id=None,
            item_id=item,
            lot_no="B-TEST",
            source_type="opening",
            mfg_date=date(2026, 11, 21),
            best_before=date(2027, 2, 19),
        )
        valuation.post_opening(
            s,
            organization_id=org,
            actor_id=None,
            posting_date=DAY,
            lines=[
                OpeningLine(item, "FG_STORE", D(50), "packet", D("28.85"), lot_id=open_lot),
                OpeningLine(item, "FG_STORE", D(188), "packet", D("21.569149"), lot_id=batch),
            ],
        )
        s.commit()
    t = Tenant(org=org, items=s5.item_ids, locations={}, customer=s5.customer_ids["RET-A"])
    emails = {role: add_member(owner_engine, t, role)[1] for role in ("ADMIN", "OWNER", "AUDITOR")}
    return Factory(org, emails, s5, item)


def approved_order(app_engine: Engine, f: Factory, customer: uuid.UUID, qty: int) -> uuid.UUID:
    s = scoped_session(app_engine, f.tenant)
    placed = sales.receive_order(
        s,
        organization_id=f.org,
        actor_id=None,
        customer_id=customer,
        price_list_id=f.s5.price_list_id,
        lines=[OrderLineIn(f.item, qty, D("50.00"))],
    )
    sales.approve_order(s, organization_id=f.org, actor_id=None, order_id=placed.order_id, partial=True)
    s.commit()
    s.close()
    return placed.order_id


def atp(app_engine: Engine, f: Factory) -> int:
    s = scoped_session(app_engine, f.tenant)
    try:
        return int(ledger.available_to_promise(s, f.item)["available"])
    finally:
        s.close()


def test_nit_invoice_a_and_its_document(api_app: Any, factory: Factory, app_engine: Engine) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 150)
    admin = login_client(api_app, factory.emails["ADMIN"])
    assert admin.get("/api/invoices/ready").json()["orders"][0]["packets_to_invoice"] == "150"
    r = admin.post(f"/api/orders/{order}/invoice", json={}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert (inv["invoice_no"][:10], len(inv["invoice_no"])) == ("AHR/26-27/", 16)
    assert (inv["regime"], inv["taxable"], inv["by_tax"], inv["total"]) == (
        "INTRA",
        "7500.00",
        {"CGST": "187.50", "SGST": "187.50"},
        "7875.00",
    )
    assert inv["lines"][0]["hsn"] == "21069099" and inv["place_of_supply"] == "33-Tamil Nadu"
    assert inv["amount_in_words"] == "Rupees Seven Thousand Eight Hundred Seventy Five Only"
    assert admin.get(f"/api/inbox/{order}").json()["status"] == "INVOICED"
    html = admin.get(f"/api/invoices/{inv['id']}/document")
    assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")
    for needle in ("TAX INVOICE", "33DEMOX0000X1Z0", "Udyam", "FSSAI", "DEMO - do not pay", "Reverse charge: No"):
        assert needle in html.text, needle
    again = admin.post(f"/api/orders/{order}/invoice", json={})
    assert again.status_code == 422 and again.json()["error"]["code"] == "order_not_invoiceable"
    auditor = login_client(api_app, factory.emails["AUDITOR"])
    assert auditor.get(f"/api/invoices/{inv['id']}").status_code == 200
    assert auditor.post(f"/api/orders/{order}/invoice", json={}).status_code == 403


def test_only_approved_orders_are_invoiced(api_app: Any, factory: Factory, app_engine: Engine) -> None:
    s = scoped_session(app_engine, factory.tenant)
    placed = sales.receive_order(
        s,
        organization_id=factory.org,
        actor_id=None,
        customer_id=factory.ret_a,
        price_list_id=factory.s5.price_list_id,
        lines=[OrderLineIn(factory.item, 10, D("50.00"))],
    )
    s.commit()
    s.close()
    admin = login_client(api_app, factory.emails["ADMIN"])
    r = admin.post(f"/api/orders/{placed.order_id}/invoice", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "order_not_invoiceable"


def test_invoice_numbers_are_gapless_under_concurrency(factory: Factory, app_engine: Engine) -> None:
    orders = [approved_order(app_engine, factory, factory.ret_a, 10) for _ in range(4)]
    barrier = threading.Barrier(len(orders))
    numbers: list[str] = []

    def invoice(order_id: uuid.UUID) -> None:
        s = scoped_session(app_engine, factory.tenant)
        try:
            barrier.wait()
            numbers.append(
                billing.create_invoice(s, organization_id=factory.org, actor_id=None, order_id=order_id).invoice_no
            )
            time.sleep(0.1)
            s.commit()
        finally:
            s.close()

    threads = [threading.Thread(target=invoice, args=(o,)) for o in orders]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert sorted(numbers) == [f"AHR/26-27/{n:06d}" for n in range(1, 5)]


def test_fefo_dispatch_at_lot_value_consumes_the_reservation(
    api_app: Any, factory: Factory, app_engine: Engine
) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 150)
    admin = login_client(api_app, factory.emails["ADMIN"])
    inv = admin.post(f"/api/orders/{order}/invoice", json={}).json()
    preview = admin.post(f"/api/invoices/{inv['id']}/dispatch-preview", json={}).json()
    assert [(p["lot_no"], p["qty"], p["value"]) for p in preview["lines"][0]["picks"]] == [
        ("OPEN-LOT", "50", "1442.50"),
        ("B-TEST", "100", "2156.91"),
    ]
    assert preview["cost_of_goods"] == "3599.41" and preview["eway"]["required"] is False
    assert preview["eway"]["reason"].startswith("Not needed: a delivery within the state")
    r = admin.post(f"/api/invoices/{inv['id']}/dispatch", json={}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["dispatch_no"].startswith("DSP/26-27/") and d["eway"]["payload"]["_notice"].startswith("MOCK")
    assert sorted((ln["lot_no"], ln["qty"]) for ln in d["lines"]) == [("B-TEST", "100"), ("OPEN-LOT", "50")]
    s = scoped_session(app_engine, factory.tenant)
    assert ledger.balance(s, factory.item, "FG_STORE") == (D(88), D("1898.09"))  # 4,055.00 - 2,156.91
    assert ledger.balance(s, factory.item, "CUSTOMER") == (D(100 + 50), D("3599.41"))
    assert ledger.available_to_promise(s, factory.item)["reserved"] == 0
    assert ledger.over_reserved(s) == []
    s.close()
    assert admin.get(f"/api/inbox/{order}").json()["status"] == "DISPATCHED"
    assert admin.post(f"/api/invoices/{inv['id']}/dispatch", json={}).json()["error"]["code"] == "nothing_to_dispatch"


def test_partial_dispatch_keeps_the_rest_held(api_app: Any, factory: Factory, app_engine: Engine) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 150)
    admin = login_client(api_app, factory.emails["ADMIN"])
    inv = admin.post(f"/api/orders/{order}/invoice", json={}).json()
    first = admin.post(
        f"/api/invoices/{inv['id']}/dispatch", json={"lines": [{"item_id": str(factory.item), "qty": "60"}]}
    )
    assert first.status_code == 201, first.text
    assert atp(app_engine, factory) == 88  # 238 - 60 left = 178 on hand, 90 still held
    assert admin.get(f"/api/inbox/{order}").json()["status"] == "INVOICED"
    too_many = admin.post(
        f"/api/invoices/{inv['id']}/dispatch", json={"lines": [{"item_id": str(factory.item), "qty": "91"}]}
    )
    assert too_many.status_code == 422 and too_many.json()["error"]["code"] == "qty_beyond_invoice"
    rest = admin.post(f"/api/invoices/{inv['id']}/dispatch", json={})
    assert rest.status_code == 201
    assert admin.get(f"/api/inbox/{order}").json()["status"] == "DISPATCHED"
    assert atp(app_engine, factory) == 88


def test_choosing_lots_needs_a_reason(api_app: Any, factory: Factory, app_engine: Engine) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 20)
    admin = login_client(api_app, factory.emails["ADMIN"])
    inv = admin.post(f"/api/orders/{order}/invoice", json={}).json()
    s = scoped_session(app_engine, factory.tenant)
    batch = ledger.lot_id_by_no(s, factory.item, "B-TEST")
    s.close()
    body: dict[str, Any] = {
        "lines": [{"item_id": str(factory.item), "qty": "20", "lots": [{"lot_id": str(batch), "qty": "20"}]}]
    }
    refused = admin.post(f"/api/invoices/{inv['id']}/dispatch", json=body)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "override_reason_required"
    ok = admin.post(
        f"/api/invoices/{inv['id']}/dispatch",
        json={**body, "override_reason": "DEMO: customer asked for the fresh batch"},
    )
    assert ok.status_code == 201
    assert ok.json()["lines"][0]["lot_no"] == "B-TEST" and ok.json()["lines"][0]["override_reason"]


def test_cancel_only_before_dispatch(api_app: Any, factory: Factory, app_engine: Engine) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 150)
    admin = login_client(api_app, factory.emails["ADMIN"])
    inv = admin.post(f"/api/orders/{order}/invoice", json={}).json()
    held = admin.post(f"/api/orders/{order}/cancel", json={"reason": "DEMO: wrong"})
    assert held.status_code == 409 and held.json()["error"]["code"] == "order_already_decided"  # INVOICED
    cancelled = admin.post(f"/api/invoices/{inv['id']}/cancel", json={"reason": "DEMO: wrong rate"}).json()
    assert cancelled["status"] == "CANCELLED" and cancelled["outstanding"] == "0.00"
    assert admin.get(f"/api/inbox/{order}").json()["status"] == "APPROVED"
    assert atp(app_engine, factory) == 88  # the stock stays held for the order
    inv2 = admin.post(f"/api/orders/{order}/invoice", json={}).json()
    assert inv2["invoice_no"].endswith("000002")
    admin.post(f"/api/invoices/{inv2['id']}/dispatch", json={})
    late = admin.post(f"/api/invoices/{inv2['id']}/cancel", json={"reason": "DEMO: too late"})
    assert late.status_code == 422 and late.json()["error"]["code"] == "invoice_dispatched"


def test_credit_note_reduces_what_is_owed(api_app: Any, factory: Factory, app_engine: Engine) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 150)
    admin = login_client(api_app, factory.emails["ADMIN"])
    inv = admin.post(f"/api/orders/{order}/invoice", json={}).json()
    r = admin.post(
        f"/api/invoices/{inv['id']}/credit-notes",
        json={"reason": "DEMO: festival discount", "lines": [{"line_no": 1, "qty": "150", "rate": "2.00"}]},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["credit_note_no"].startswith("CN/26-27/") and body["credited"] == "315.00"  # 300 + 7.50 + 7.50
    assert body["outstanding"] == "7560.00"
    over = admin.post(
        f"/api/invoices/{inv['id']}/credit-notes",
        json={"reason": "DEMO: too much", "lines": [{"line_no": 1, "qty": "150", "rate": "49.00"}]},
    )
    assert over.status_code == 422 and over.json()["error"]["code"] == "credit_exceeds_invoice_line"


def test_payments_allocation_and_advance(api_app: Any, factory: Factory, app_engine: Engine) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 150)
    admin = login_client(api_app, factory.emails["ADMIN"])
    inv = admin.post(f"/api/orders/{order}/invoice", json={}).json()
    key = {"Idempotency-Key": str(uuid.uuid4())}
    pay = {"customer_id": str(factory.ret_a), "amount": "4000.00", "mode": "UPI", "reference": "DEMO-UPI-1"}
    first = admin.post("/api/payments", json=pay, headers=key)
    assert first.status_code == 201, first.text
    assert first.json()["outstanding"]["value"] == "3875.00"  # NIT's outstanding_A
    replay = admin.post("/api/payments", json=pay, headers=key)
    assert replay.status_code == 200 and replay.json()["payment_id"] == first.json()["payment_id"]
    over = admin.post(
        "/api/payments",
        json={**pay, "amount": "5000.00", "allocations": [{"invoice_id": inv["id"], "amount": "4000.00"}]},
    )
    assert over.status_code == 422 and over.json()["error"]["code"] == "over_allocation"
    advance = admin.post("/api/payments", json={**pay, "amount": "5000.00", "reference": "DEMO-UPI-2"}).json()
    assert advance["outstanding"]["value"] == "0.00" and advance["advance"] == "1125.00"
    assert admin.get(f"/api/invoices/{inv['id']}").json()["paid"] == "7875.00"
    paid_cancel = admin.post(f"/api/invoices/{inv['id']}/cancel", json={"reason": "DEMO: try"})
    assert paid_cancel.status_code == 422 and paid_cancel.json()["error"]["code"] == "invoice_paid"
    overview = admin.get("/api/collections").json()
    row = next(c for c in overview["customers"] if c["customer_id"] == str(factory.ret_a))
    assert (row["outstanding"], row["advance"]) == ("0.00", "1125.00")


def test_outstanding_feeds_the_credit_check(api_app: Any, factory: Factory, app_engine: Engine) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 150)
    admin = login_client(api_app, factory.emails["ADMIN"])
    admin.post(f"/api/orders/{order}/invoice", json={})
    s = scoped_session(app_engine, factory.tenant)
    placed = sales.receive_order(
        s,
        organization_id=factory.org,
        actor_id=None,
        customer_id=factory.ret_a,
        price_list_id=factory.s5.price_list_id,
        lines=[OrderLineIn(factory.item, 10, D("50.00"))],
    )
    s.commit()
    s.close()
    credit = admin.get(f"/api/inbox/{placed.order_id}").json()["credit"]
    assert credit["outstanding"]["value"] == "7875.00"
    assert credit["exposure"]["value"] == "8375.00"


def test_invoice_lines_are_immutable(owner_engine: Engine, factory: Factory, app_engine: Engine) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 10)
    s = scoped_session(app_engine, factory.tenant)
    inv = billing.create_invoice(s, organization_id=factory.org, actor_id=None, order_id=order)
    s.commit()
    s.close()
    with pytest.raises(DBAPIError), owner_engine.begin() as c:
        c.execute(text("UPDATE invoice_lines SET rate = 1 WHERE invoice_id = :i"), {"i": inv.invoice_id})
    with pytest.raises(DomainError), Session(app_engine) as s2:
        org_scope(s2, factory.org)
        billing.cancel_invoice(s2, organization_id=factory.org, actor_id=None, invoice_id=inv.invoice_id, reason=" ")


def test_a_part_approved_order_with_an_invoice_cannot_be_cancelled(
    api_app: Any, factory: Factory, app_engine: Engine
) -> None:
    order = approved_order(app_engine, factory, factory.ret_a, 300)  # 238 held, 62 backordered
    admin = login_client(api_app, factory.emails["ADMIN"])
    assert admin.get(f"/api/inbox/{order}").json()["status"] == "PART_APPROVED"
    inv = admin.post(f"/api/orders/{order}/invoice", json={}).json()
    assert inv["lines"][0]["qty"] == "238"
    refused = admin.post(f"/api/orders/{order}/cancel", json={"reason": "DEMO: changed mind"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "order_has_invoice"
    assert admin.get(f"/api/inbox/{order}").json()["status"] == "PART_APPROVED"  # still owes the backorder
