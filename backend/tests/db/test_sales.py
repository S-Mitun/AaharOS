"""Order taking against PostgreSQL through the real API (MP08, ADR-0015): prices from the server's list, the
salesman row filter, assigned customers only, a tampered price refused, a stale price flagged, a duplicate key
replayed, a reused key 409, gapless SO numbers after a refusal, the catalog, last order and summary, and price list
items append-only."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.calendar import business_date, financial_year
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.sales import service as sales
from app.modules.sales.models import SalesOrder
from tests.db.conftest import Staff, add_member, login_client, make_staff, scoped_session, sqlstate

FY = financial_year(business_date())


class Shop:
    def __init__(self, staff: Staff, other_customer: uuid.UUID, price_list: uuid.UUID, salesman_b: str) -> None:
        self.staff = staff
        self.item = staff.tenant.items["murukku_200g"]
        self.customer = staff.tenant.customer
        self.other_customer = other_customer
        self.price_list = price_list
        self.salesman_b = salesman_b


@pytest.fixture
def shop(owner_engine: Engine, app_engine: Engine) -> Shop:
    """A fresh tenant: logins per role, a second salesman, Retailer A assigned to both salesmen, Distributor B
    assigned to nobody, and the general price list v1 (200 g at 50.00)."""
    staff = make_staff(owner_engine, "SALES")
    b_id, b_email = add_member(owner_engine, staff.tenant, "SALESMAN", "salesman-b")
    s = scoped_session(app_engine, staff.tenant)
    org = staff.tenant.org
    ledger.ensure_locations(s, org)
    other = sales.create_customer(
        s,
        organization_id=org,
        actor_id=None,
        code="DIST-B",
        name="DEMO Distributor B",
        kind="DISTRIBUTOR",
        state_code="29",
    )
    for salesman in (staff.user_ids["SALESMAN"], b_id):
        identity.assign_customer(
            s,
            organization_id=org,
            actor_id=None,
            salesman_id=salesman,
            customer_id=staff.tenant.customer,
            route_order=1,
        )
    pl = sales.create_price_list(
        s,
        organization_id=org,
        actor_id=None,
        code="general",
        effective_from=date(2026, 4, 1),
        items={staff.tenant.items["murukku_200g"]: Decimal("50.00")},
    )
    s.commit()
    s.close()
    return Shop(staff, other, pl, b_email)


def order(shop: Shop, qty: str = "150", price: str = "50.00", **over: Any) -> dict[str, Any]:
    return {
        "customer_id": str(shop.customer),
        "price_list_id": str(shop.price_list),
        "captured_at": "2026-11-21T09:15:00+05:30",
        "lines": [{"item_id": str(shop.item), "qty": qty, "price_ex_tax": price}],
        **over,
    }


def price_list_body(shop: Shop, price: str) -> dict[str, Any]:
    return {
        "code": "GENERAL",
        "effective_from": "2026-04-01",
        "items": [{"item_id": str(shop.item), "price_ex_tax": price}],
    }


def count_orders(app_engine: Engine, shop: Shop) -> int:
    s = scoped_session(app_engine, shop.staff.tenant)
    n = s.execute(select(func.count()).select_from(SalesOrder)).scalar_one()
    s.close()
    return int(n)


def test_salesman_places_an_order_priced_by_the_server(api_app: Any, shop: Shop) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    r = client.post("/api/orders", json=order(shop), headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    o = r.json()
    assert (o["order_no"], o["status"], o["replayed"], o["stale"]) == (f"SO/{FY}/000001", "SUBMITTED", False, False)
    assert o["total_ex_tax"]["value"] == "7500.00" and o["lines"][0]["price_ex_tax"] == "50.00"
    assert o["salesman"]["id"] == str(shop.staff.user_ids["SALESMAN"])
    assert o["captured_at"].startswith("2026-11-21T03:45:00")  # stored in UTC
    assert [t["to_status"] for t in o["timeline"]] == ["SUBMITTED"]
    assert (o["price_list"]["code"], o["price_list"]["version"]) == ("GENERAL", 1)


def test_unassigned_customer_refused(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    r = client.post("/api/orders", json=order(shop, customer_id=str(shop.other_customer)))
    assert r.status_code == 403 and r.json()["error"]["code"] == "customer_not_assigned"
    assert count_orders(app_engine, shop) == 0
    owner = login_client(api_app, shop.staff.emails["OWNER"])  # not row-filtered: any customer
    assert owner.post("/api/orders", json=order(shop, customer_id=str(shop.other_customer))).status_code == 201


def test_tampered_price_refused(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    r = client.post("/api/orders", json=order(shop, price="1.00"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "price_mismatch"
    assert count_orders(app_engine, shop) == 0


def test_fractional_and_number_quantities_refused(api_app: Any, shop: Shop) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    for qty in ("1.5", "0", "-2"):
        assert client.post("/api/orders", json=order(shop, qty=qty)).status_code == 422
    bad = order(shop)
    bad["lines"][0]["qty"] = 150  # a JSON number, not a string
    assert client.post("/api/orders", json=bad).status_code == 422


def test_stale_price_flagged_with_the_current_price(api_app: Any, shop: Shop) -> None:
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    v2 = admin.post("/api/price-lists", json=price_list_body(shop, "52.00"))
    assert v2.status_code == 201 and v2.json()["version"] == 2, v2.text
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    r = client.post("/api/orders", json=order(shop))  # the phone still shows v1 at 50.00
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["stale"] is True and o["lines"][0]["price_ex_tax"] == "50.00"
    assert o["stale_detail"]["in_force_price_list"]["version"] == 2
    assert o["stale_detail"]["current_prices"] == {str(shop.item): "52.00"}
    assert "stale" in (o["timeline"][0]["reason"] or "")
    assert client.get("/api/orders").json()["orders"][0]["stale"] is True


def test_order_received_before_a_new_version_stays_fresh(api_app: Any, shop: Shop) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    first = client.post("/api/orders", json=order(shop)).json()
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    assert admin.post("/api/price-lists", json=price_list_body(shop, "52.00")).status_code == 201
    assert client.get(f"/api/orders/{first['id']}").json()["stale"] is False


def test_duplicate_key_replayed_and_reused_key_conflicts(api_app: Any, shop: Shop, app_engine: Engine) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    key = {"Idempotency-Key": str(uuid.uuid4())}
    first = client.post("/api/orders", json=order(shop), headers=key)
    again = client.post("/api/orders", json=order(shop, price="50"), headers=key)
    assert (first.status_code, again.status_code) == (201, 200), again.text
    assert again.json()["id"] == first.json()["id"] and again.json()["replayed"] is True
    conflict = client.post("/api/orders", json=order(shop, qty="151"), headers=key)
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_key_reused"
    assert count_orders(app_engine, shop) == 1


def test_numbers_stay_gapless_after_a_refusal(api_app: Any, shop: Shop) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    assert client.post("/api/orders", json=order(shop)).json()["order_no"] == f"SO/{FY}/000001"
    assert client.post("/api/orders", json=order(shop, price="49.00")).status_code == 422
    assert client.post("/api/orders", json=order(shop, qty="5")).json()["order_no"] == f"SO/{FY}/000002"


def test_salesman_sees_only_own_orders(api_app: Any, shop: Shop) -> None:
    a = login_client(api_app, shop.staff.emails["SALESMAN"])
    b = login_client(api_app, shop.salesman_b)
    mine = a.post("/api/orders", json=order(shop)).json()
    assert [o["id"] for o in a.get("/api/orders").json()["orders"]] == [mine["id"]]
    assert b.get("/api/orders").json()["orders"] == []
    assert b.get(f"/api/orders/{mine['id']}").status_code == 404
    assert b.get(f"/api/sales/customers/{shop.customer}/last-order").json()["last_order"] is None
    admin = login_client(api_app, shop.staff.emails["ADMIN"])
    assert admin.get(f"/api/orders/{mine['id']}").status_code == 200


def test_catalog_last_order_and_summary(api_app: Any, shop: Shop) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    cat = client.get(f"/api/sales/catalog?customer_id={shop.customer}").json()
    assert cat["price_list"]["version"] == 1
    (product,) = cat["products"]
    assert (product["code"], product["price_ex_tax"], product["available_today"]) == ("murukku_200g", "50.00", "0")
    assert client.get(f"/api/sales/catalog?customer_id={shop.other_customer}").status_code == 403
    customers = client.get("/api/customers").json()["customers"]
    assert [(c["code"], c["route_order"]) for c in customers] == [("RET-A", 1)]

    client.post("/api/orders", json=order(shop, qty="150"))
    client.post("/api/orders", json=order(shop, qty="40"))
    last = client.get(f"/api/sales/customers/{shop.customer}/last-order").json()["last_order"]
    assert last["lines"] == [{"item_id": str(shop.item), "qty": "40"}]
    summary = client.get("/api/sales/summary").json()
    (row,) = summary["customers"]
    assert (row["orders"], row["packets"], row["value_ex_tax"]) == (2, "190", "9500.00")
    assert summary["total_ex_tax"]["value"] == "9500.00" and "not invoiced" in summary["note"]


def test_price_list_items_are_append_only(owner_engine: Engine, shop: Shop) -> None:
    for sql in (
        "UPDATE price_list_items SET price_ex_tax = 1 WHERE price_list_id = :p",
        "DELETE FROM price_list_items WHERE price_list_id = :p",
    ):
        with pytest.raises(DBAPIError) as e, owner_engine.begin() as c:
            c.execute(text(sql), {"p": shop.price_list})
        assert sqlstate(e.value) == "AH002"


def test_salesman_cannot_publish_prices(api_app: Any, shop: Shop) -> None:
    client = login_client(api_app, shop.staff.emails["SALESMAN"])
    assert client.post("/api/price-lists", json=price_list_body(shop, "1.00")).status_code == 403
