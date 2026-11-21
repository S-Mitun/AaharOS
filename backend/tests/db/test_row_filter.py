"""A salesman sees only assigned customers and their own orders (brief section 3, MP03)."""

import uuid
from typing import Any

from sqlalchemy import Engine, text

from tests.db.conftest import add_member, login_client, make_staff


def test_salesman_sees_only_assigned_customers_and_own_orders(owner_engine: Engine, api_app: Any) -> None:
    team = make_staff(owner_engine, "ROWS")
    t = team.tenant
    salesman_a = team.user_ids["SALESMAN"]
    salesman_b, email_b = add_member(owner_engine, t, "SALESMAN", "salesman-b")
    with owner_engine.begin() as c:
        ids = {}
        for code, kind, state in (("DIST-B", "DISTRIBUTOR", "29"), ("RET-C", "RETAILER", "33")):
            ids[code] = c.execute(
                text(
                    "INSERT INTO customers (organization_id, code, name, kind, state_code)"
                    " VALUES (:o, :c, :n, :k, :s) RETURNING id"
                ),
                {"o": t.org, "c": code, "n": f"DEMO {code}", "k": kind, "s": state},
            ).scalar_one()
        ids["RET-A"] = t.customer
        for user, code in ((salesman_a, "RET-A"), (salesman_b, "DIST-B")):
            c.execute(
                text(
                    "INSERT INTO salesman_customer_assignments (organization_id, user_id, customer_id)"
                    " VALUES (:o, :u, :c)"
                ),
                {"o": t.org, "u": user, "c": ids[code]},
            )
        for no, user, code in (("SO-1", salesman_a, "RET-A"), ("SO-2", salesman_b, "DIST-B")):
            c.execute(
                text(
                    "INSERT INTO sales_orders (organization_id, order_no, order_date, customer_id, salesman_id)"
                    " VALUES (:o, :n, '2026-11-21', :c, :u)"
                ),
                {"o": t.org, "n": no, "c": ids[code], "u": user},
            )

    def visible(client: Any) -> tuple[list[str], list[str]]:
        customers = [c["code"] for c in client.get("/api/customers").json()["customers"]]
        orders = [o["order_no"] for o in client.get("/api/orders").json()["orders"]]
        return sorted(customers), sorted(orders)

    assert visible(login_client(api_app, team.emails["SALESMAN"])) == (["RET-A"], ["SO-1"])
    assert visible(login_client(api_app, email_b)) == (["DIST-B"], ["SO-2"])
    everyone = (["DIST-B", "RET-A", "RET-C"], ["SO-1", "SO-2"])
    assert visible(login_client(api_app, team.emails["ADMIN"])) == everyone
    assert visible(login_client(api_app, team.emails["AUDITOR"])) == everyone


def test_salesman_with_no_assignments_sees_nothing(owner_engine: Engine, api_app: Any) -> None:
    team = make_staff(owner_engine, "EMPTY")
    client = login_client(api_app, team.emails["SALESMAN"])
    assert client.get("/api/customers").json() == {"customers": []}
    assert client.get("/api/orders").json() == {"orders": []}
    assert uuid.UUID(str(team.tenant.customer))  # the tenant does have a customer; it is just not assigned
