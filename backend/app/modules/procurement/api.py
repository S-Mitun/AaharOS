"""Purchase routes (MP05): receipts (post, reverse, read), the purchase register and suppliers.

`POST /api/purchases/receipts` honours an `Idempotency-Key` header: a duplicate submit returns the first receipt
(200 instead of 201) and posts nothing.
"""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.procurement import service
from app.modules.procurement.domain import ReceiptLineIn
from app.modules.procurement.schemas import ReceiptBody, ReverseBody

router = APIRouter(prefix="/api", tags=["purchases"])
DbSession = Annotated[Session, Depends(get_session)]


@router.post("/purchases/receipts", status_code=status.HTTP_201_CREATED)
def post_receipt(
    body: ReceiptBody,
    response: Response,
    principal: Annotated[Principal, Depends(require("receipt.post"))],
    session: DbSession,
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    lines = []
    for line in body.lines:
        qty, rate, freight, rejected = line.decimals()
        lines.append(
            ReceiptLineIn(
                item_id=line.item_id,
                qty=qty,
                unit=line.unit,
                rate=rate,
                freight=freight,
                rejected_qty=rejected,
                lot_no=line.lot_no,
                mfg_date=line.mfg_date,
                best_before=line.best_before,
            )
        )
    result = service.post_receipt(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        supplier_id=body.supplier_id,
        supplier_invoice_ref=body.supplier_invoice_ref,
        received_on=body.received_on,
        lines=lines,
        idempotency_key=idempotency_key,
    )
    session.commit()
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return {"replayed": result.replayed, **service.get_receipt(session, result.receipt_id)}


@router.post("/purchases/receipts/{receipt_id}/reverse")
def reverse_receipt(
    receipt_id: uuid.UUID,
    body: ReverseBody,
    principal: Annotated[Principal, Depends(require("receipt.post"))],
    session: DbSession,
) -> dict[str, Any]:
    reversal = service.reverse_receipt(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        receipt_id=receipt_id,
        reason=body.reason,
    )
    session.commit()
    return {"reversal_journal_id": str(reversal), **service.get_receipt(session, receipt_id)}


@router.get("/purchases/receipts/{receipt_id}")
def get_receipt(
    receipt_id: uuid.UUID,
    _principal: Annotated[Principal, Depends(require("report.read"))],
    session: DbSession,
) -> dict[str, Any]:
    return service.get_receipt(session, receipt_id)


@router.get("/purchases/register")
def purchase_register(
    _principal: Annotated[Principal, Depends(require("report.read"))],
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    supplier_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return service.register(session, date_from=date_from, date_to=date_to, supplier_id=supplier_id)


@router.get("/suppliers")
def suppliers(
    _principal: Annotated[Principal, Depends(require("report.read"))],
    session: DbSession,
) -> dict[str, Any]:
    return {"suppliers": service.list_suppliers(session)}
