"""Traceability routes (MP13, ADR-0020): trace a lot and simulate a recall. Read-only (`report.read`)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import NotFoundError
from app.modules.identity import service as identity
from app.modules.identity.service import Principal, require
from app.modules.sales import service as sales
from app.modules.traceability import food_safety, freshness, passport, service

router = APIRouter(prefix="/api/trace", tags=["traceability"])
public_router = APIRouter(prefix="/api/public", tags=["public"])
DbSession = Annotated[Session, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("report.read"))]


@router.get("/lots")
def lots(
    _principal: Reader, session: DbSession, q: Annotated[str | None, Query(max_length=60)] = None
) -> dict[str, Any]:
    return {"lots": service.search(session, q)}


@router.get("/lots/{lot_id}")
def trace(lot_id: uuid.UUID, _principal: Reader, session: DbSession) -> dict[str, Any]:
    return service.trace(session, lot_id)


@router.get("/recall/{lot_id}")
def recall(
    lot_id: uuid.UUID,
    _principal: Reader,
    session: DbSession,
    reason: Annotated[str | None, Query(max_length=200)] = None,
) -> dict[str, Any]:
    """The recall simulator: nothing is stored and nothing is sent."""
    return service.recall(session, lot_id, reason)


Days = Annotated[int, Query(ge=1, le=366)]


@router.get("/oil")
def oil_log(_principal: Reader, session: DbSession, days: Days = 30) -> dict[str, Any]:
    """Oil used per day against the RUCO record-keeping threshold, and TPC against the discard limit."""
    return food_safety.oil_log(session, days)


@router.get("/fill-weights")
def fill_weights(_principal: Reader, session: DbSession, days: Days = 30) -> dict[str, Any]:
    """Giveaway and short fills per batch, from the samples recorded at completion."""
    return food_safety.fill_weights(session, days)


@router.get("/freshness")
def freshness_radar(
    principal: Annotated[Principal, Depends(require("customer.read"))], session: DbSession
) -> dict[str, Any]:
    """The shelf freshness radar. A salesman sees only the customers assigned to them."""
    mine = set(identity.route_order(session, principal.user_id)) if principal.sees_only_own_rows else None
    return freshness.radar(session, mine)


@router.get("/passport/{lot_id}")
def passport_label(
    lot_id: uuid.UUID, _principal: Reader, session: DbSession, customer_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """The batch passport of a finished-goods lot: its signed link and QR code (SVG) for a printable label."""
    if customer_id is not None and not sales.customer_id_exists(session, customer_id):
        raise NotFoundError("customer_not_found", "unknown customer")
    return passport.label(session, lot_id, customer_id)


@router.get("/reorder/{token}")
def reorder(
    token: str, principal: Annotated[Principal, Depends(require("order.create"))], session: DbSession
) -> dict[str, Any]:
    """Scan to reorder: the customer a passport's "Ask for more" link is for, if the signed-in salesman serves them.
    The salesman then opens that customer's pre-filled order and submits it; the link itself writes nothing."""
    customer_id = passport.resolve_reorder(session, token)
    if not sales.customer_id_exists(session, customer_id) or (
        principal.sees_only_own_rows and not identity.is_assigned(session, principal.user_id, customer_id)
    ):
        raise NotFoundError("passport_not_found", "this reorder link is not for one of your customers")
    return {"customer_id": str(customer_id), "order_path": f"/sales/order/{customer_id}?repeat=1"}


@public_router.get("/passport/{token}")
def public_passport(token: str, request: Request, session: DbSession) -> dict[str, Any]:
    """No login: what is printed on the pack, for a signed token. No prices, customers or stock."""
    passport.check_rate(request.client.host if request.client else None)
    return passport.public_view(session, token)
