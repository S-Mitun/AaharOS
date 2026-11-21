"""Sales routes available from MP03 (read-only lists). A salesman sees only assigned customers and own orders."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.sales import service

router = APIRouter(prefix="/api", tags=["sales"])


@router.get("/customers")
def customers(
    principal: Annotated[Principal, Depends(require("customer.read"))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    return {"customers": service.list_customers(session, principal)}


@router.get("/orders")
def orders(
    principal: Annotated[Principal, Depends(require("order.read"))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    return {"orders": service.list_orders(session, principal)}
