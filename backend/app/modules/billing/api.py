"""Billing routes (MP10): invoices from approved orders, the printable document, cancellation and credit notes.
`POST /api/orders/{id}/invoice` honours an Idempotency-Key (a replay returns the first invoice, 200)."""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.billing import document, service
from app.modules.billing.domain import CreditLineIn
from app.modules.billing.schemas import CreditNoteBody, InvoiceBody, ReasonBody
from app.modules.identity.service import Principal, require
from app.modules.sales import service as sales

router = APIRouter(prefix="/api", tags=["billing"])
DbSession = Annotated[Session, Depends(get_session)]


@router.get("/invoices")
def invoices(_principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession) -> dict[str, Any]:
    return {"invoices": service.invoice_list(session)}


@router.get("/invoices/ready")
def ready_to_invoice(
    _principal: Annotated[Principal, Depends(require("invoice.post"))], session: DbSession
) -> dict[str, Any]:
    return {"orders": sales.orders_to_bill(session)}


@router.post("/orders/{order_id}/invoice", status_code=status.HTTP_201_CREATED)
def create_invoice(
    order_id: uuid.UUID,
    body: InvoiceBody,
    response: Response,
    principal: Annotated[Principal, Depends(require("invoice.post"))],
    session: DbSession,
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result = service.create_invoice(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        order_id=order_id,
        invoice_date=body.invoice_date,
        idempotency_key=idempotency_key,
    )
    session.commit()
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return {"replayed": result.replayed, **service.invoice_view(session, result.invoice_id)}


@router.get("/invoices/{invoice_id}")
def get_invoice(
    invoice_id: uuid.UUID, _principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession
) -> dict[str, Any]:
    return service.invoice_view(session, invoice_id)


@router.get("/invoices/{invoice_id}/document", response_class=HTMLResponse)
def invoice_document(
    invoice_id: uuid.UUID, _principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession
) -> HTMLResponse:
    """The printable tax invoice (open it, then print or save as PDF)."""
    return HTMLResponse(document.render(service.invoice_view(session, invoice_id)))


@router.post("/invoices/{invoice_id}/cancel")
def cancel_invoice(
    invoice_id: uuid.UUID,
    body: ReasonBody,
    principal: Annotated[Principal, Depends(require("invoice.cancel"))],
    session: DbSession,
) -> dict[str, Any]:
    service.cancel_invoice(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        invoice_id=invoice_id,
        reason=body.reason,
    )
    session.commit()
    return service.invoice_view(session, invoice_id)


@router.post("/invoices/{invoice_id}/credit-notes", status_code=status.HTTP_201_CREATED)
def credit_note(
    invoice_id: uuid.UUID,
    body: CreditNoteBody,
    principal: Annotated[Principal, Depends(require("credit_note.post"))],
    session: DbSession,
) -> dict[str, Any]:
    note_id, note_no = service.post_credit_note(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        invoice_id=invoice_id,
        reason=body.reason,
        note_date=body.note_date,
        lines=[CreditLineIn(ln.line_no, int(ln.qty), Decimal(ln.rate)) for ln in body.lines],
    )
    session.commit()
    return {"credit_note_id": str(note_id), "credit_note_no": note_no, **service.invoice_view(session, invoice_id)}
