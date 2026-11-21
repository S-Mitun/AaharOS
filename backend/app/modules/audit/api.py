"""Audit routes for the auditor and the owner: the latest rows and a live chain verification."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.audit import service
from app.modules.identity.service import Principal, require

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/log")
def audit_log(
    principal: Annotated[Principal, Depends(require("audit.read"))],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    rows = service.recent(session, principal.organization_id, limit)
    return {
        "rows": [
            {
                "seq": r.seq,
                "occurred_at": r.occurred_at.isoformat(),
                "actor_id": None if r.actor_id is None else str(r.actor_id),
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": None if r.entity_id is None else str(r.entity_id),
                "summary": r.summary,
                "correlation_id": None if r.correlation_id is None else str(r.correlation_id),
                "hash": r.hash.hex(),
            }
            for r in rows
        ]
    }


@router.get("/verify")
def verify(
    principal: Annotated[Principal, Depends(require("audit.read"))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    verdict = service.verify(session, principal.organization_id)
    return {
        "ok": verdict.ok,
        "rows_checked": verdict.rows_checked,
        "first_bad_seq": verdict.first_bad_seq,
        "reason": verdict.reason,
    }
