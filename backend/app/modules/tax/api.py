"""Tax routes (MP10): read the GST rules, and add one (a new effective-dated rule, never an edit)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.tax import service

router = APIRouter(prefix="/api", tags=["tax"])
DbSession = Annotated[Session, Depends(get_session)]


class RuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hsn: Annotated[str, StringConstraints(pattern=r"^\d{4,8}$")]
    rate_pct: Annotated[str, StringConstraints(pattern=r"^\d{1,3}(\.\d{1,2})?$")]
    effective_from: date
    effective_to: date | None = None
    note: Annotated[str, StringConstraints(max_length=300)] | None = None


def _rules(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": str(r.id),
            "hsn": r.hsn,
            "rate_pct": str(r.rate_pct.normalize()),
            "effective_from": r.effective_from.isoformat(),
            "effective_to": None if r.effective_to is None else r.effective_to.isoformat(),
        }
        for r in service.rules(session)
    ]


@router.get("/tax/rules")
def rules(_principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession) -> dict[str, Any]:
    return {"rules": _rules(session)}


@router.post("/tax/rules", status_code=status.HTTP_201_CREATED)
def add_rule(
    body: RuleBody, principal: Annotated[Principal, Depends(require("settings.manage"))], session: DbSession
) -> dict[str, Any]:
    service.create_rule(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        hsn=body.hsn,
        rate_pct=Decimal(body.rate_pct),
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        note=body.note,
    )
    session.commit()
    return {"rules": _rules(session)}
