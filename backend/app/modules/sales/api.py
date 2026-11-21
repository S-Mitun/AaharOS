"""Sales routes: customers, the salesman's catalog, orders and price lists (MP03 reads, MP08 order taking).

A salesman sees only assigned customers and own orders. `POST /api/orders` honours an `Idempotency-Key` header: a
replay returns the original order (200, `replayed: true`); the same key with a different order is 409.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.sales import service
from app.modules.sales.domain import OrderLineIn
from app.modules.sales.schemas import OrderBody, PriceListBody

router = APIRouter(prefix="/api", tags=["sales"])
DbSession = Annotated[Session, Depends(get_session)]


@router.get("/customers")
def customers(
    principal: Annotated[Principal, Depends(require("customer.read"))],
    session: DbSession,
) -> dict[str, Any]:
    return {"customers": service.list_customers(session, principal)}


@router.get("/orders")
def orders(
    principal: Annotated[Principal, Depends(require("order.read"))],
    session: DbSession,
    days: Annotated[int | None, Query(ge=1, le=3660)] = None,
) -> dict[str, Any]:
    return {"orders": service.list_orders(session, principal, days)}


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def place_order(
    body: OrderBody,
    response: Response,
    principal: Annotated[Principal, Depends(require("order.create"))],
    session: DbSession,
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result = service.place_order(
        session,
        principal,
        customer_id=body.customer_id,
        price_list_id=body.price_list_id,
        captured_at=body.captured_at,
        lines=[OrderLineIn(ln.item_id, int(ln.qty), Decimal(ln.price_ex_tax)) for ln in body.lines],
        idempotency_key=idempotency_key,
    )
    session.commit()
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return {"replayed": result.replayed, **service.get_order(session, principal, result.order_id)}


@router.get("/orders/{order_id}")
def get_order(
    order_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require("order.read"))],
    session: DbSession,
) -> dict[str, Any]:
    return service.get_order(session, principal, order_id)


@router.get("/sales/catalog")
def sales_catalog(
    customer_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require("order.read"))],
    session: DbSession,
) -> dict[str, Any]:
    return service.catalog_for(session, principal, customer_id)


@router.get("/sales/customers/{customer_id}/last-order")
def last_order(
    customer_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require("order.read"))],
    session: DbSession,
) -> dict[str, Any]:
    return {"last_order": service.last_order(session, principal, customer_id)}


@router.get("/sales/summary")
def sales_summary(
    principal: Annotated[Principal, Depends(require("order.read"))],
    session: DbSession,
    days: Annotated[int, Query(ge=1, le=366)] = 30,
) -> dict[str, Any]:
    return service.summary(session, principal, days)


@router.get("/price-lists")
def price_lists(
    _principal: Annotated[Principal, Depends(require("customer.read"))],
    session: DbSession,
) -> dict[str, Any]:
    return {"price_lists": service.list_price_lists(session)}


@router.post("/price-lists", status_code=status.HTTP_201_CREATED)
def publish_price_list(
    body: PriceListBody,
    principal: Annotated[Principal, Depends(require("price.manage"))],
    session: DbSession,
) -> dict[str, Any]:
    price_list_id = service.create_price_list(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        code=body.code,
        customer_id=body.customer_id,
        effective_from=body.effective_from,
        items=body.prices(),
    )
    session.commit()
    published = next(p for p in service.list_price_lists(session) if p["id"] == str(price_list_id))
    return published
