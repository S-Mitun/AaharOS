"""Sales read models available from MP03: customers and orders, with the salesman row filter.

Order taking, approval and the inbox arrive in MP08-MP09; this file grows with them.
"""

import uuid
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.modules.audit import service as audit
from app.modules.identity import service as identity
from app.modules.identity.service import Principal
from app.modules.sales.models import CUSTOMER_KINDS, Customer, SalesOrder


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


def create_customer(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    code: str,
    name: str,
    kind: str,
    state_code: str,
    gstin: str | None = None,
) -> uuid.UUID:
    """Master data (MP05 seeds). Customer management screens arrive with MP09."""
    if kind not in CUSTOMER_KINDS:
        raise DomainError("unknown_customer_kind", f"customer kind must be one of {', '.join(CUSTOMER_KINDS)}")
    customer_id = uuid.uuid4()
    session.execute(
        insert(Customer).values(
            id=customer_id,
            organization_id=organization_id,
            code=code,
            name=name,
            kind=kind,
            state_code=state_code,
            gstin=gstin,
            created_by=actor_id,
        )
    )
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="customer.create",
        entity_type="customer",
        entity_id=customer_id,
        after={"code": code, "name": name, "kind": kind, "state_code": state_code, "gstin": gstin},
    )
    return customer_id


def customer_id_by_code(session: Session, code: str) -> uuid.UUID | None:
    return session.execute(select(Customer.id).where(Customer.code == code)).scalar_one_or_none()
