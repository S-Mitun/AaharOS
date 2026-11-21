"""Dispatch routes (MP10): the FEFO preview (stock movement before posting) and the dispatch itself.
`POST /api/invoices/{id}/dispatch` honours an Idempotency-Key."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.dispatch import service
from app.modules.identity.service import Principal, require

router = APIRouter(prefix="/api", tags=["dispatch"])
DbSession = Annotated[Session, Depends(get_session)]
Packets = Annotated[str, StringConstraints(pattern=r"^\d{1,7}$")]


class LotChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lot_id: uuid.UUID
    qty: Packets


class DispatchLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    qty: Packets
    lots: Annotated[list[LotChoice], Field(max_length=50)] = []  # empty: first-expiry-first-out


class DispatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dispatch_date: date | None = None
    lines: Annotated[list[DispatchLineBody], Field(max_length=200)] = []  # empty: everything left on the invoice
    override_reason: Annotated[str, StringConstraints(max_length=500)] | None = None

    def args(self) -> dict[str, Any]:
        if not self.lines:
            return {"qty": None, "chosen_lots": None}
        return {
            "qty": {ln.item_id: int(ln.qty) for ln in self.lines},
            "chosen_lots": {ln.item_id: {c.lot_id: int(c.qty) for c in ln.lots} for ln in self.lines if ln.lots}
            or None,
        }


@router.post("/invoices/{invoice_id}/dispatch-preview")
def preview(
    invoice_id: uuid.UUID,
    body: DispatchBody,
    _principal: Annotated[Principal, Depends(require("dispatch.post"))],
    session: DbSession,
) -> dict[str, Any]:
    plan = service.plan_dispatch(
        session, invoice_id, override_reason=body.override_reason, dispatch_date=body.dispatch_date, **body.args()
    )
    return service.plan_view(plan)


@router.post("/invoices/{invoice_id}/dispatch", status_code=status.HTTP_201_CREATED)
def dispatch(
    invoice_id: uuid.UUID,
    body: DispatchBody,
    response: Response,
    principal: Annotated[Principal, Depends(require("dispatch.post"))],
    session: DbSession,
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result = service.dispatch_invoice(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        invoice_id=invoice_id,
        override_reason=body.override_reason,
        dispatch_date=body.dispatch_date,
        idempotency_key=idempotency_key,
        **body.args(),
    )
    session.commit()
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return {"replayed": result.replayed, **service.dispatch_view(session, result.dispatch_id)}


@router.get("/invoices/{invoice_id}/dispatches")
def dispatches(
    invoice_id: uuid.UUID, _principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession
) -> dict[str, Any]:
    return {"dispatches": service.dispatches_for(session, invoice_id)}
