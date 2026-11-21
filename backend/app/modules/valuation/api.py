"""Valuation route (MP05): each pooled item's quantity, value and average cost, with its formula (Explained).

Needs `report.read`, so a salesman never sees cost (MP04 review, docs/security.md).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.valuation import service

router = APIRouter(prefix="/api/stock", tags=["stock"])


@router.get("/valuation")
def valuation(
    _principal: Annotated[Principal, Depends(require("report.read"))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    return {"method": "WAC", "items": service.valuation_summary(session)}
