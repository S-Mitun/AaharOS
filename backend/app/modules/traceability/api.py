"""Traceability routes (MP13, ADR-0020): trace a lot and simulate a recall. Read-only (`report.read`)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.traceability import food_safety, service

router = APIRouter(prefix="/api/trace", tags=["traceability"])
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
