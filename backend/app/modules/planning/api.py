"""Planning routes (MP12): material runway and shortage attribution. Read-only (`report.read`)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.planning import service

router = APIRouter(prefix="/api/planning", tags=["planning"])
DbSession = Annotated[Session, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("report.read"))]


@router.get("/runway")
def runway(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return {"packs": service.runway(session)}


@router.get("/shortage/{order_id}")
def shortage(order_id: uuid.UUID, _principal: Reader, session: DbSession) -> dict[str, Any]:
    return service.shortage_attribution(session, order_id)
