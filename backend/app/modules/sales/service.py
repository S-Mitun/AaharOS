"""Sales read models available from MP03: customers and orders, with the salesman row filter.

Order taking, approval and the inbox arrive in MP08-MP09; this file grows with them.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity import service as identity
from app.modules.identity.service import Principal
from app.modules.sales.models import Customer, SalesOrder


def list_customers(session: Session, principal: Principal) -> list[dict[str, Any]]:
    query = select(Customer).order_by(Customer.code)
    if principal.sees_only_own_rows:
        query = query.where(Customer.id.in_(identity.assigned_customer_ids(principal.user_id)))
    return [
        {
            "id": str(c.id),
            "code": c.code,
            "name": c.name,
            "kind": c.kind,
            "state_code": c.state_code,
            "gstin": c.gstin,
        }
        for c in session.execute(query).scalars()
    ]


def list_orders(session: Session, principal: Principal) -> list[dict[str, Any]]:
    query = select(SalesOrder).order_by(SalesOrder.order_date.desc(), SalesOrder.order_no.desc())
    if principal.sees_only_own_rows:
        query = query.where(SalesOrder.salesman_id == principal.user_id)
    return [
        {
            "id": str(o.id),
            "order_no": o.order_no,
            "order_date": o.order_date.isoformat(),
            "customer_id": str(o.customer_id),
            "salesman_id": None if o.salesman_id is None else str(o.salesman_id),
            "status": o.status,
        }
        for o in session.execute(query).scalars()
    ]
