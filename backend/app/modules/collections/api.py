"""Collections routes (MP10): what customers owe, a customer's statement, and recording a payment.
`POST /api/payments` honours an Idempotency-Key."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.collections import service
from app.modules.collections.service import AllocationIn
from app.modules.identity.service import Principal, require

router = APIRouter(prefix="/api", tags=["collections"])
DbSession = Annotated[Session, Depends(get_session)]
Rupees = Annotated[str, StringConstraints(pattern=r"^\d{1,10}(\.\d{1,2})?$")]


class AllocationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: uuid.UUID
    amount: Rupees


class PaymentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    amount: Rupees
    received_on: date | None = None
    mode: Annotated[str, StringConstraints(pattern=r"^(CASH|UPI|BANK|CHEQUE)$")] = "UPI"
    reference: Annotated[str, StringConstraints(max_length=100)] | None = None
    allocations: Annotated[list[AllocationBody], Field(max_length=200)] | None = None  # None: oldest due first


@router.get("/collections")
def overview(_principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession) -> dict[str, Any]:
    return service.overview(session)


@router.get("/customers/{customer_id}/statement")
def statement(
    customer_id: uuid.UUID, _principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession
) -> dict[str, Any]:
    return service.statement(session, customer_id)


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def record_payment(
    body: PaymentBody,
    response: Response,
    principal: Annotated[Principal, Depends(require("payment.post"))],
    session: DbSession,
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result = service.record_payment(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        customer_id=body.customer_id,
        amount=Decimal(body.amount),
        received_on=body.received_on,
        mode=body.mode,
        reference=body.reference,
        allocations=None
        if body.allocations is None
        else [AllocationIn(a.invoice_id, Decimal(a.amount)) for a in body.allocations],
        idempotency_key=idempotency_key,
    )
    session.commit()
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return {
        "payment_id": str(result.payment_id),
        "payment_no": result.payment_no,
        "replayed": result.replayed,
        **service.statement(session, body.customer_id),
    }
