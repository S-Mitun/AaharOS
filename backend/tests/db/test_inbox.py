"""The order inbox and decisions against PostgreSQL through the real API (MP09, ADR-0016): full approval reserves or
writes nothing, partial approval with a backorder, the backorder covered later, reject and cancel release stock, a
stale order needs a price choice, the credit check, amendments keep the salesman's values, wait for the next batch,
the inbox views, and racing approvals."""

import threading
import time
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, func, select

from app.core.errors import DomainError
from app.modules.audit.models import AuditLog
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.ledger.models import Reservation
from app.modules.sales import service as sales
from app.modules.valuation import service as valuation
from app.modules.valuation.service import OpeningLine
from tests.db.conftest import Staff, login_client, make_staff, scoped_session

D = Decimal


class Shop:
    def __init__(self, staff: Staff, dist_b: uuid.UUID, price_list: uuid.UUID) -> None:
        self.staff = staff
        self.item = staff.tenant.items["murukku_200g"]
        self.ret_a = staff.tenant.customer
        self.dist_b = dist_b
        self.price_list = price_list


@pytest.fixture
def shop(owner_engine: Engine, app_engine: Engine) -> Shop:
    """A tenant with logins, Retailer A and Distributor B both on the salesman's route, price list v1 at 50.00 and
    238 finished packets on hand (NIT's figure after run B-001)."""
    staff = make_staff(owner_engine, "INBOX")
    s = scoped_session(app_engine, staff.tenant)
    org = staff.tenant.org
    ledger.ensure_locations(s, org)
    dist_b = sales.create_customer(
        s,
        organization_id=org,
        actor_id=None,
        code="DIST-B",
        name="DEMO Distributor B",
        kind="DISTRIBUTOR",
        state_code="29",
        credit_limit=D("100000.00"),
    )
    for n, customer in enumerate((staff.tenant.customer, dist_b), start=1):
        identity.assign_customer(
            s,
            organization_id=org,
            actor_id=None,
            salesman_id=staff.user_ids["SALESMAN"],
            customer_id=customer,
            route_order=n,
        )
    item = staff.tenant.items["murukku_200g"]
    pl = sales.create_price_list(
        s, organization_id=org, actor_id=None, code="GENERAL", effective_from=date(2026, 4, 1), items={item: D("50.00")}
    )
    lot = ledger.create_lot(
        s, organization_id=org, actor_id=None, item_id=item, lot_no="OPEN-LOT", source_type="opening"
    )
    valuation.post_opening(
        s,
        organization_id=org,
        actor_id=None,
        posting_date=date(2026, 11, 21),
        lines=[OpeningLine(item, "FG_STORE", D(238), "packet", D("28.85"), lot_id=lot)],
    )
    s.commit()
    s.close()
    return Shop(staff, dist_b, pl)


def place(api_app: Any, shop: Shop, customer: uuid.UUID, qty: int) -> str:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    r = client.post(
        "/api/orders",
        json={
            "customer_id": str(customer),
            "price_list_id": str(shop.price_list),
            "lines": [{"item_id": str(shop.item), "qty": str(qty), "price_ex_tax": "50.00"}],
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def atp(app_engine: Engine, shop: Shop) -> int:
    s = scoped_session(app_engine, shop.staff.tenant)
    try:
        return int(ledger.available_to_promise(s, shop.item)["available"])
    finally:
        s.close()


def count(app_engine: Engine, shop: Shop, model: Any) -> int:
    s = scoped_session(app_engine, shop.staff.tenant)
    try:
        return int(s.execute(select(func.count()).select_from(model)).scalar_one())
    finally:
        s.close()


def test_nit_retailer_a_then_distributor_b(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    a = place(api_app, shop, shop.ret_a, 150)
    b = place(api_app, shop, shop.dist_b, 120)
    admin = login_client(api_app, shop.staff.emails["ADMIN"])

    r = admin.post(f"/api/orders/{a}/approve", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED" and r.json()["card_lines"][0]["approved"] == "150"
    assert atp(app_engine, shop) == 88

    card = admin.get(f"/api/inbox/{b}").json()
    (line,) = card["card_lines"]
    assert (line["requested"], line["available"]["value"], line["shortage"]["value"]) == ("120", "88", "32")
    assert line["available"]["formula"] == "on hand - reserved" and line["can_send_now"] == "88"
    assert line["next_batch"] is None  # no batch planned: the card says ETA unknown

    reservations, audits = count(app_engine, shop, Reservation), count(app_engine, shop, AuditLog)
    refused = admin.post(f"/api/orders/{b}/approve", json={})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "insufficient_available"
    assert refused.json()["error"]["details"]["lines"][0]["shortage"] == 32
    assert (count(app_engine, shop, Reservation), count(app_engine, shop, AuditLog)) == (reservations, audits)
    assert admin.get(f"/api/inbox/{b}").json()["status"] == "SUBMITTED"

    salesman = login_client(api_app, shop.staff.emails["SALESMAN"])
    assert salesman.get(f"/api/orders/{a}").json()["status"] == "APPROVED"


def test_partial_approval_backorder_then_covered(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    a = place(api_app, shop, shop.ret_a, 150)
    b = place(api_app, shop, shop.dist_b, 120)
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    admin.post(f"/api/orders/{a}/approve", json={})

    part = admin.post(f"/api/orders/{b}/approve", json={"partial": True}).json()
    assert part["status"] == "PART_APPROVED"
    assert (part["card_lines"][0]["approved"], part["card_lines"][0]["backordered"]) == ("88", "32")
    assert atp(app_engine, shop) == 0
    none_yet = admin.post(f"/api/orders/{b}/approve-backorder")
    assert none_yet.status_code == 422 and none_yet.json()["error"]["code"] == "nothing_available"

    # Retailer A cancels: its 150 packets return, and B's backorder can be covered
    cancelled = admin.post(f"/api/orders/{a}/cancel", json={"reason": "DEMO: customer cancelled"}).json()
    assert cancelled["status"] == "CANCELLED" and atp(app_engine, shop) == 150
    done = admin.post(f"/api/orders/{b}/approve-backorder").json()
    assert done["status"] == "APPROVED"
    assert (done["card_lines"][0]["approved"], done["card_lines"][0]["backordered"]) == ("120", "0")
    assert atp(app_engine, shop) == 118


def test_reject_releases_and_needs_a_reason(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    a = place(api_app, shop, shop.ret_a, 150)
    b = place(api_app, shop, shop.dist_b, 120)
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    admin.post(f"/api/orders/{a}/approve", json={})
    assert admin.post(f"/api/orders/{b}/approve", json={"partial": True}).json()["status"] == "PART_APPROVED"
    assert atp(app_engine, shop) == 0
    assert admin.post(f"/api/orders/{b}/reject", json={"reason": " "}).status_code == 422
    rejected = admin.post(f"/api/orders/{b}/reject", json={"reason": "DEMO: no stock this week"}).json()
    assert rejected["status"] == "REJECTED" and atp(app_engine, shop) == 88
    assert "88 packets released" in rejected["decision"]["summary"]
    assert admin.post(f"/api/orders/{a}/reject", json={"reason": "DEMO: wrong"}).status_code == 409  # cancel it
    again = admin.post(f"/api/orders/{b}/approve", json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "order_already_decided"


def test_stale_order_needs_a_price_choice(api_app: Any, shop: Shop) -> None:
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    published = admin.post(
        "/api/price-lists",
        json={
            "code": "GENERAL",
            "effective_from": "2026-04-01",
            "items": [{"item_id": str(shop.item), "price_ex_tax": "52.00"}],
        },
    )
    assert published.status_code == 201
    a = place(api_app, shop, shop.ret_a, 10)  # the phone still shows v1 at 50.00
    card = admin.get(f"/api/inbox/{a}").json()
    assert card["stale_choice_needed"] is True and card["card_lines"][0]["price_current"] == "52.00"
    r = admin.post(f"/api/orders/{a}/approve", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "stale_price_choice_required"
    ok = admin.post(f"/api/orders/{a}/approve", json={"stale_price": "current"}).json()
    line = ok["card_lines"][0]
    assert (line["price_captured"], line["price_final"]) == ("50.00", "52.00")
    assert "v2" in (line["amend_reason"] or "")


def test_credit_limit_needs_an_override_reason(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    s = scoped_session(app_engine, shop.staff.tenant)
    sales.set_credit_limit(
        s, organization_id=shop.staff.tenant.org, actor_id=None, customer_id=shop.ret_a, limit=D("1000.00")
    )
    s.commit()
    s.close()
    a = place(api_app, shop, shop.ret_a, 150)  # 7,500.00 against a 1,000.00 limit
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    card = admin.get(f"/api/inbox/{a}").json()
    assert card["credit"]["over_limit"] is True and card["credit"]["exposure"]["value"] == "7500.00"
    assert card["credit"]["outstanding"]["formula"] == "no invoices exist until MP10"
    r = admin.post(f"/api/orders/{a}/approve", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "credit_limit_exceeded"
    ok = admin.post(f"/api/orders/{a}/approve", json={"credit_override_reason": "DEMO: owner agreed by phone"})
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED"
    assert "credit: DEMO: owner agreed by phone" in ok.json()["timeline"][-1]["reason"]


def test_amendments_keep_the_salesmans_values(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    a = place(api_app, shop, shop.ret_a, 150)
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    assert (
        admin.post(f"/api/orders/{a}/amend", json={"line_no": 1, "price_ex_tax": "48.00", "reason": "x"}).status_code
        == 422
    )
    priced = admin.post(
        f"/api/orders/{a}/amend", json={"line_no": 1, "price_ex_tax": "48.00", "reason": "DEMO: festival discount"}
    ).json()
    assert (priced["card_lines"][0]["price_captured"], priced["card_lines"][0]["price_final"]) == ("50.00", "48.00")
    early = admin.post(f"/api/orders/{a}/amend", json={"line_no": 1, "qty": "100", "reason": "DEMO: smaller"})
    assert early.status_code == 409  # quantities are agreed at approval, then amended down

    cut = admin.post(
        f"/api/orders/{a}/approve", json={"agreed": [{"line_no": 1, "qty": "140"}], "amend_reason": "DEMO: shelf space"}
    ).json()
    assert (cut["card_lines"][0]["requested"], cut["card_lines"][0]["approved"]) == ("150", "140")
    assert atp(app_engine, shop) == 98
    down = admin.post(
        f"/api/orders/{a}/amend", json={"line_no": 1, "qty": "100", "reason": "DEMO: customer called"}
    ).json()
    assert (down["card_lines"][0]["requested"], down["card_lines"][0]["approved"]) == ("150", "100")
    assert atp(app_engine, shop) == 138
    salesman = login_client(api_app, shop.staff.emails["SALESMAN"])
    assert salesman.get(f"/api/orders/{a}").json()["lines"][0]["qty"] == "150"


def test_wait_for_the_next_batch_and_inbox_views(api_app: Any, shop: Shop) -> None:
    a = place(api_app, shop, shop.ret_a, 150)
    b = place(api_app, shop, shop.dist_b, 120)
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    admin.post(f"/api/orders/{a}/approve", json={})
    waited = admin.post(f"/api/orders/{b}/wait").json()
    assert waited["status"] == "SUBMITTED" and waited["waiting"] is True
    assert "no batch planned, ETA unknown" in waited["decision"]["summary"]
    views = {
        v: [o["id"] for o in admin.get(f"/api/inbox?view={v}").json()["orders"]] for v in ("to_decide", "short", "all")
    }
    assert views["to_decide"] == [b] and views["short"] == [b] and set(views["all"]) == {a, b}
    assert admin.get("/api/inbox?view=nonsense").status_code == 422
    salesman = login_client(api_app, shop.staff.emails["SALESMAN"])
    assert salesman.get("/api/inbox").status_code == 403


def test_racing_approvals_for_the_last_packets(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    """Two orders of 150 against 238 approved at the same instant: exactly one wins, the other writes nothing."""
    orders = [uuid.UUID(place(api_app, shop, shop.ret_a, 150)) for _ in range(2)]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def approve(order_id: uuid.UUID) -> None:
        s = scoped_session(app_engine, shop.staff.tenant)
        try:
            barrier.wait()
            sales.approve_order(s, organization_id=shop.staff.tenant.org, actor_id=None, order_id=order_id)
            time.sleep(0.3)
            s.commit()
            outcomes.append("APPROVED")
        except DomainError as exc:
            s.rollback()
            outcomes.append(exc.code)
        finally:
            s.close()

    threads = [threading.Thread(target=approve, args=(o,)) for o in orders]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert sorted(outcomes) == ["APPROVED", "insufficient_available"]
    assert atp(app_engine, shop) == 88


def test_racing_approvals_of_the_same_order(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    order_id = uuid.UUID(place(api_app, shop, shop.ret_a, 100))
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def approve() -> None:
        s = scoped_session(app_engine, shop.staff.tenant)
        try:
            barrier.wait()
            sales.approve_order(s, organization_id=shop.staff.tenant.org, actor_id=None, order_id=order_id)
            time.sleep(0.3)
            s.commit()
            outcomes.append("APPROVED")
        except DomainError as exc:
            s.rollback()
            outcomes.append(exc.code)
        finally:
            s.close()

    threads = [threading.Thread(target=approve) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert sorted(outcomes) == ["APPROVED", "order_already_decided"]
    assert atp(app_engine, shop) == 138
    s = scoped_session(app_engine, shop.staff.tenant)
    assert ledger.over_reserved(s) == []
    s.close()
