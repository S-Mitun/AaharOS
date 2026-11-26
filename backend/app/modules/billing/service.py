"""Billing use cases (MP10, ADR-0017): GST invoices from approved orders, cancellation before dispatch, credit notes,
the invoice view and its printable document. Other modules call only this file. Functions run in the caller's
transaction and never commit (the API route commits).

An invoice posts in one savepoint: lock the order -> packets approved and not yet invoiced -> tax from the rules in
force on the invoice date -> claim the Idempotency-Key -> gapless AHR number -> invoice + lines + tax lines -> order
status (INVOICED once every agreed packet is invoiced) -> audit -> store the response. A refusal rolls back the
number too.

Billing (L6) answers sales' question "how many packets are invoiced" (registered below); dispatch and collections
(L6 siblings that import billing) answer billing's questions about dispatched packets and allocated payments.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import idempotency
from app.core.calendar import business_date, financial_year
from app.core.errors import DomainError, NotFoundError
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.billing import domain
from app.modules.billing.domain import BillingError, CreditLineIn
from app.modules.billing.models import (
    CreditNote,
    CreditNoteLine,
    CreditNoteTaxLine,
    Invoice,
    InvoiceLine,
    InvoiceTaxLine,
)
from app.modules.catalog import service as catalog
from app.modules.identity import service as identity
from app.modules.sales import service as sales
from app.modules.tax import domain as tax_domain
from app.modules.tax import service as tax


def _db_error(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


# ---------- what sibling modules tell billing ----------

DispatchFacts = Callable[[Session, uuid.UUID], dict[str, Any]]  # invoice -> {"packets": {item: n}, "lots": [...]}
AllocatedProvider = Callable[[Session, uuid.UUID], Decimal]  # invoice -> rupees allocated from payments
# MP13 (T4): (customer, dispatched lots) -> [{"lot_no", "url"}], the batch-passport links printed on the invoice
PassportProvider = Callable[[Session, uuid.UUID, list[dict[str, Any]]], list[dict[str, str]]]
_dispatch_facts: DispatchFacts | None = None
_allocated: AllocatedProvider | None = None
_passports: PassportProvider | None = None


def register_dispatch_facts(provider: DispatchFacts | None) -> None:
    global _dispatch_facts
    _dispatch_facts = provider


def register_passport_provider(provider: PassportProvider | None) -> None:
    global _passports
    _passports = provider


def register_allocated_provider(provider: AllocatedProvider | None) -> None:
    global _allocated
    _allocated = provider


def _dispatched(session: Session, invoice_id: uuid.UUID) -> dict[str, Any]:
    return {"packets": {}, "lots": []} if _dispatch_facts is None else _dispatch_facts(session, invoice_id)


def _paid(session: Session, invoice_id: uuid.UUID) -> Decimal:
    return Decimal("0.00") if _allocated is None else _allocated(session, invoice_id)


# ---------- invoiced packets (sales asks through its provider) ----------


def invoiced_by_item(session: Session, order_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = session.execute(
        select(InvoiceLine.item_id, func.sum(InvoiceLine.qty))
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(Invoice.sales_order_id == order_id, Invoice.status == "POSTED")
        .group_by(InvoiceLine.item_id)
    ).tuples()
    return {item: int(qty) for item, qty in rows}


def dispatched_by_item_for_order(session: Session, order_id: uuid.UUID) -> dict[uuid.UUID, int]:
    out: dict[uuid.UUID, int] = {}
    for inv_id in session.execute(
        select(Invoice.id).where(Invoice.sales_order_id == order_id, Invoice.status == "POSTED")
    ).scalars():
        for item, qty in _dispatched(session, inv_id)["packets"].items():
            out[item] = out.get(item, 0) + int(qty)
    return out


sales.register_invoiced_provider(invoiced_by_item)


def sync_order(
    session: Session, organization_id: uuid.UUID, actor_id: uuid.UUID | None, order_id: uuid.UUID, reason: str
) -> str:
    """Set the order's status from what is now invoiced and dispatched."""
    return sales.sync_billing_status(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        order_id=order_id,
        invoiced=invoiced_by_item(session, order_id),
        dispatched=dispatched_by_item_for_order(session, order_id),
        reason=reason,
    )


# ---------- invoices (J2) ----------


@dataclass(frozen=True)
class InvoiceResult:
    invoice_id: uuid.UUID
    invoice_no: str
    replayed: bool


def create_invoice(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    order_id: uuid.UUID,
    invoice_date: date | None = None,
    idempotency_key: uuid.UUID | None = None,
) -> InvoiceResult:
    """Invoice the approved packets of an order that are not invoiced yet, at the order line's price."""
    on = invoice_date or business_date()
    order = sales.order_for_billing(session, order_id, lock=True)
    if order.status not in ("APPROVED", "PART_APPROVED"):
        raise BillingError("order_not_invoiceable", f"this order is {order.status}: only approved packets are invoiced")
    qty = domain.to_invoice({ln.item_id: ln.approved for ln in order.lines}, invoiced_by_item(session, order.id))
    supplier = identity.organization(session, organization_id)
    lines = [ln for ln in order.lines if ln.item_id in qty]
    computed = tax.compute(
        session,
        supplier_state=supplier["state_code"],
        place_of_supply=order.customer_state,
        on=on,
        lines=[tax.TaxedLineIn(n, ln.item_id, qty[ln.item_id], ln.price) for n, ln in enumerate(lines, start=1)],
    )
    t = computed.totals
    digest = idempotency.request_hash(
        {"kind": "invoice", "order_id": order.id, "date": on, "lines": sorted([str(i), q] for i, q in qty.items())}
    )
    try:
        with session.begin_nested():
            if idempotency_key is not None:
                stored = idempotency.claim(session, organization_id, idempotency_key, digest)
                if stored is not None:
                    if "invoice_id" not in stored.body:
                        raise DomainError("idempotency_key_reused", "this Idempotency-Key belongs to another request")
                    return InvoiceResult(uuid.UUID(stored.body["invoice_id"]), stored.body["invoice_no"], True)
            fy = financial_year(on)
            number = session.execute(
                text("SELECT aahar_next_doc_number(:o, :t, :fy)"),
                {"o": organization_id, "t": domain.INVOICE_DOC, "fy": fy},
            ).scalar_one()
            invoice_no = domain.invoice_no(fy, int(number))
            invoice_id = uuid.uuid4()
            session.execute(
                insert(Invoice).values(
                    id=invoice_id,
                    organization_id=organization_id,
                    invoice_no=invoice_no,
                    invoice_date=on,
                    sales_order_id=order.id,
                    customer_id=order.customer_id,
                    supplier_state=supplier["state_code"],
                    place_of_supply=order.customer_state,
                    customer_gstin=order.customer_gstin,
                    regime=computed.regime,
                    taxable=t.taxable,
                    tax_total=t.tax_total,
                    round_off=t.round_off,
                    total=t.total,
                    status="POSTED",
                    created_by=actor_id,
                )
            )
            for lt in computed.lines:
                line_id = uuid.uuid4()
                session.execute(
                    insert(InvoiceLine).values(
                        id=line_id,
                        organization_id=organization_id,
                        invoice_id=invoice_id,
                        line_no=lt.line_no,
                        item_id=lines[lt.line_no - 1].item_id,
                        hsn=computed.hsn[lt.line_no],
                        qty=lt.qty,
                        rate=lt.rate,
                        taxable=lt.taxable,
                        created_by=actor_id,
                    )
                )
                session.execute(
                    insert(InvoiceTaxLine),
                    [
                        {
                            "organization_id": organization_id,
                            "invoice_line_id": line_id,
                            "tax": tx.tax,
                            "rate_pct": tx.rate_pct,
                            "amount": tx.amount,
                            "tax_rule_id": lt.rule_id,
                            "created_by": actor_id,
                        }
                        for tx in lt.taxes
                    ],
                )
            sync_order(session, organization_id, actor_id, order.id, f"invoiced {invoice_no}")
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="invoice.post",
                entity_type="invoice",
                entity_id=invoice_id,
                after={
                    "invoice_no": invoice_no,
                    "invoice_date": on,
                    "order_id": order.id,
                    "regime": computed.regime,
                    "taxable": t.taxable,
                    "taxes": t.by_tax,
                    "round_off": t.round_off,
                    "total": t.total,
                    "lines": [{"item_id": i, "qty": q} for i, q in qty.items()],
                },
            )
            if idempotency_key is not None:
                idempotency.complete(
                    session, organization_id, idempotency_key, 201, {"invoice_id": invoice_id, "invoice_no": invoice_no}
                )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return InvoiceResult(invoice_id, invoice_no, False)


def _invoice(session: Session, invoice_id: uuid.UUID, lock: bool = False) -> Invoice:
    query = select(Invoice).where(Invoice.id == invoice_id)
    if lock:
        query = query.with_for_update()
    inv = session.execute(query).scalar_one_or_none()
    if inv is None:
        raise NotFoundError("invoice_not_found", "unknown invoice")
    return inv


def cancel_invoice(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, invoice_id: uuid.UUID, reason: str
) -> None:
    """J3: cancel a posted invoice that has not left the factory, has no payment and no credit note. The order goes
    back to APPROVED (its stock stays held). After a dispatch, correct with a credit note instead."""
    text_reason = (reason or "").strip()
    if len(text_reason) < 3:
        raise BillingError("reason_required", "cancelling an invoice needs a reason")
    inv = _invoice(session, invoice_id, lock=True)
    if inv.status != "POSTED":
        raise BillingError("invoice_not_posted", f"invoice {inv.invoice_no} is {inv.status}")
    if any(_dispatched(session, inv.id)["packets"].values()):
        raise BillingError("invoice_dispatched", "goods on this invoice have left: issue a credit note instead")
    if _paid(session, inv.id) > 0:
        raise BillingError("invoice_paid", "payments are allocated to this invoice: it cannot be cancelled")
    if session.execute(select(CreditNote.id).where(CreditNote.invoice_id == inv.id)).first() is not None:
        raise BillingError("invoice_credited", "this invoice has a credit note: it cannot be cancelled")
    try:
        with session.begin_nested():
            inv.status = "CANCELLED"
            inv.cancelled_at = datetime.now(UTC)
            inv.cancel_reason = text_reason
            session.flush()
            if inv.sales_order_id is not None:
                sync_order(
                    session, organization_id, actor_id, inv.sales_order_id, f"invoice {inv.invoice_no} cancelled"
                )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="invoice.cancel",
                entity_type="invoice",
                entity_id=inv.id,
                before={"status": "POSTED"},
                after={"status": "CANCELLED"},
                note=text_reason,
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc


def _line_taxes(session: Session, invoice_id: uuid.UUID) -> dict[int, domain.InvoiceLineTaxes]:
    lines = list(session.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id)).scalars())
    heads = session.execute(
        select(InvoiceTaxLine.invoice_line_id, InvoiceTaxLine.tax, InvoiceTaxLine.rate_pct).where(
            InvoiceTaxLine.invoice_line_id.in_([ln.id for ln in lines])
        )
    ).all()
    credited = dict(
        session.execute(
            select(CreditNoteLine.invoice_line_id, func.sum(CreditNoteLine.taxable))
            .where(CreditNoteLine.invoice_line_id.in_([ln.id for ln in lines]))
            .group_by(CreditNoteLine.invoice_line_id)
        )
        .tuples()
        .all()
    )
    return {
        ln.line_no: domain.InvoiceLineTaxes(
            ln.line_no,
            ln.taxable,
            Decimal(credited.get(ln.id, 0)),
            tuple(sorted((tx, rate) for lid, tx, rate in heads if lid == ln.id)),
        )
        for ln in lines
    }


def post_credit_note(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    invoice_id: uuid.UUID,
    reason: str,
    lines: Sequence[CreditLineIn],
    note_date: date | None = None,
) -> tuple[uuid.UUID, str]:
    """J3: a value-only credit note against a posted invoice (no stock moves; returned goods are MP13)."""
    text_reason = (reason or "").strip()
    if len(text_reason) < 3:
        raise BillingError("reason_required", "a credit note needs a reason")
    inv = _invoice(session, invoice_id, lock=True)
    if inv.status != "POSTED":
        raise BillingError("invoice_not_posted", f"invoice {inv.invoice_no} is {inv.status}")
    on = note_date or business_date()
    if on < inv.invoice_date:
        raise BillingError("credit_before_invoice", "a credit note cannot be dated before its invoice")
    by_no = _line_taxes(session, inv.id)
    plan = domain.plan_credit_note(lines, by_no)
    ids = {
        ln.line_no: ln.id
        for ln in session.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)).scalars()
    }
    taxable = sum((p.taxable for p in plan), Decimal(0))
    tax_total = sum((amt for p in plan for _, _, amt in p.taxes), Decimal(0))
    try:
        with session.begin_nested():
            fy = financial_year(on)
            number = session.execute(
                text("SELECT aahar_next_doc_number(:o, :t, :fy)"),
                {"o": organization_id, "t": domain.CREDIT_NOTE_DOC, "fy": fy},
            ).scalar_one()
            note_no = domain.credit_note_no(fy, int(number))
            note_id = uuid.uuid4()
            session.execute(
                insert(CreditNote).values(
                    id=note_id,
                    organization_id=organization_id,
                    credit_note_no=note_no,
                    note_date=on,
                    invoice_id=inv.id,
                    reason=text_reason,
                    taxable=taxable,
                    tax_total=tax_total,
                    round_off=Decimal("0.00"),
                    total=taxable + tax_total,
                    created_by=actor_id,
                )
            )
            for p in plan:
                line_id = uuid.uuid4()
                session.execute(
                    insert(CreditNoteLine).values(
                        id=line_id,
                        organization_id=organization_id,
                        credit_note_id=note_id,
                        line_no=p.line_no,
                        invoice_line_id=ids[p.invoice_line_no],
                        qty=p.qty,
                        rate=p.rate,
                        taxable=p.taxable,
                        created_by=actor_id,
                    )
                )
                session.execute(
                    insert(CreditNoteTaxLine),
                    [
                        {
                            "organization_id": organization_id,
                            "credit_note_line_id": line_id,
                            "tax": head,
                            "rate_pct": rate,
                            "amount": amount,
                            "created_by": actor_id,
                        }
                        for head, rate, amount in p.taxes
                    ],
                )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="credit_note.post",
                entity_type="credit_note",
                entity_id=note_id,
                after={
                    "credit_note_no": note_no,
                    "invoice_no": inv.invoice_no,
                    "taxable": taxable,
                    "tax_total": tax_total,
                    "total": taxable + tax_total,
                },
                note=text_reason,
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return note_id, note_no


# ---------- reads ----------


def credited_total(session: Session, invoice_id: uuid.UUID) -> Decimal:
    value = session.execute(
        select(func.coalesce(func.sum(CreditNote.total), 0)).where(CreditNote.invoice_id == invoice_id)
    ).scalar_one()
    return Decimal(value)


@dataclass(frozen=True)
class InvoiceBrief:
    id: uuid.UUID
    invoice_no: str
    invoice_date: date
    customer_id: uuid.UUID
    sales_order_id: uuid.UUID | None
    status: str
    regime: str
    total: Decimal
    credited: Decimal
    due_date: date


def invoices(session: Session, customer_id: uuid.UUID | None = None, status: str | None = None) -> list[InvoiceBrief]:
    query = select(Invoice).order_by(Invoice.invoice_date, Invoice.invoice_no)
    if customer_id is not None:
        query = query.where(Invoice.customer_id == customer_id)
    if status is not None:
        query = query.where(Invoice.status == status)
    rows = list(session.execute(query).scalars())
    terms = {}
    out = []
    for inv in rows:
        if inv.customer_id not in terms:
            terms[inv.customer_id] = sales.customer_terms(session, inv.customer_id)
        c = terms[inv.customer_id]
        out.append(
            InvoiceBrief(
                inv.id,
                inv.invoice_no,
                inv.invoice_date,
                inv.customer_id,
                inv.sales_order_id,
                inv.status,
                inv.regime,
                inv.total,
                credited_total(session, inv.id),
                domain.due_date(inv.invoice_date, int(c["payment_terms_days"]), bool(c["msme_terms"])),
            )
        )
    return out


def invoice_view(session: Session, invoice_id: uuid.UUID) -> dict[str, Any]:
    inv = _invoice(session, invoice_id)
    lines = list(
        session.execute(
            select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id).order_by(InvoiceLine.line_no)
        ).scalars()
    )
    heads = list(
        session.execute(
            select(InvoiceTaxLine).where(InvoiceTaxLine.invoice_line_id.in_([ln.id for ln in lines]))
        ).scalars()
    )
    names = catalog.names_for(session, {ln.item_id for ln in lines})
    units = catalog.units_for(session, {ln.item_id for ln in lines})
    customer = sales.customer_terms(session, inv.customer_id)
    supplier = identity.organization(session, inv.organization_id)
    order_no = None
    if inv.sales_order_id is not None:
        order_no = sales.order_for_billing(session, inv.sales_order_id).order_no
    by_tax: dict[str, Decimal] = {}
    for h in heads:
        by_tax[h.tax] = by_tax.get(h.tax, Decimal(0)) + h.amount
    dispatched = _dispatched(session, inv.id)
    paid = _paid(session, inv.id)
    credited = credited_total(session, inv.id)
    notes = [
        {
            "id": str(n.id),
            "credit_note_no": n.credit_note_no,
            "note_date": n.note_date.isoformat(),
            "total": str(n.total),
            "reason": n.reason,
        }
        for n in session.execute(
            select(CreditNote).where(CreditNote.invoice_id == inv.id).order_by(CreditNote.note_date)
        ).scalars()
    ]
    due = domain.due_date(inv.invoice_date, int(customer["payment_terms_days"]), bool(customer["msme_terms"]))
    outstanding = inv.total - paid - credited if inv.status == "POSTED" else Decimal("0.00")
    return {
        "id": str(inv.id),
        "invoice_no": inv.invoice_no,
        "invoice_date": inv.invoice_date.isoformat(),
        "due_date": due.isoformat(),
        "status": inv.status,
        "cancel_reason": inv.cancel_reason,
        "order_id": None if inv.sales_order_id is None else str(inv.sales_order_id),
        "order_no": order_no,
        "regime": inv.regime,
        "place_of_supply": tax_domain.state_label(inv.place_of_supply),
        "supplier": {**supplier, "state_label": tax_domain.state_label(inv.supplier_state)},
        "customer": {
            **customer,
            "gstin": inv.customer_gstin,
            "state_label": tax_domain.state_label(customer["state_code"]),
        },
        "profile": tax.profile(session, inv.invoice_date),
        "lines": [
            {
                "line_no": ln.line_no,
                "item_id": str(ln.item_id),
                "item_code": names[ln.item_id][0],
                "item_name": names[ln.item_id][1],
                "hsn": ln.hsn,
                "qty": str(ln.qty),
                "unit": units[ln.item_id].stock_uom,
                "rate": str(ln.rate),
                "taxable": str(ln.taxable),
                "dispatched": str(dispatched["packets"].get(ln.item_id, 0)),
                "taxes": [
                    {"tax": h.tax, "rate_pct": str(h.rate_pct.normalize()), "amount": str(h.amount)}
                    for h in sorted(heads, key=lambda x: x.tax)
                    if h.invoice_line_id == ln.id
                ],
            }
            for ln in lines
        ],
        "taxable": str(inv.taxable),
        "by_tax": {k: str(v) for k, v in sorted(by_tax.items())},
        "tax_total": str(inv.tax_total),
        "round_off": str(inv.round_off),
        "total": str(inv.total),
        "amount_in_words": tax_domain.amount_in_words(inv.total),
        "lots": dispatched["lots"],
        "passports": [] if _passports is None else _passports(session, inv.customer_id, dispatched["lots"]),
        "paid": str(paid),
        "credited": str(credited),
        "outstanding": str(outstanding),
        "credit_notes": notes,
    }


def invoice_list(session: Session) -> list[dict[str, Any]]:
    out = []
    for b in invoices(session):
        customer = sales.customer_terms(session, b.customer_id)
        dispatched = _dispatched(session, b.id)["packets"]
        lines = session.execute(
            select(func.coalesce(func.sum(InvoiceLine.qty), 0)).where(InvoiceLine.invoice_id == b.id)
        ).scalar_one()
        out.append(
            {
                "id": str(b.id),
                "invoice_no": b.invoice_no,
                "invoice_date": b.invoice_date.isoformat(),
                "customer_name": customer["name"],
                "status": b.status,
                "total": str(b.total),
                "packets": str(int(lines)),
                "dispatched": str(sum(int(v) for v in dispatched.values())),
                "due_date": b.due_date.isoformat(),
            }
        )
    return list(reversed(out))


def register_rows(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """MP11: every invoice line (POSTED and CANCELLED, with its status) and every credit-note line (negative) in the
    range, with HSN, place of supply, regime and each tax head. The sales register and the GST summary read this."""
    out: list[dict[str, Any]] = []
    invoices_in = list(
        session.execute(
            select(Invoice)
            .where(Invoice.invoice_date >= date_from, Invoice.invoice_date <= date_to)
            .order_by(Invoice.invoice_date, Invoice.invoice_no)
        ).scalars()
    )
    notes_in = list(
        session.execute(
            select(CreditNote, Invoice)
            .join(Invoice, Invoice.id == CreditNote.invoice_id)
            .where(CreditNote.note_date >= date_from, CreditNote.note_date <= date_to)
            .order_by(CreditNote.note_date, CreditNote.credit_note_no)
        ).all()
    )
    customers: dict[uuid.UUID, dict[str, Any]] = {}

    def customer(cid: uuid.UUID) -> dict[str, Any]:
        if cid not in customers:
            customers[cid] = sales.customer_terms(session, cid)
        return customers[cid]

    inv_lines = list(
        session.execute(select(InvoiceLine).where(InvoiceLine.invoice_id.in_([i.id for i in invoices_in]))).scalars()
    )
    inv_taxes = list(
        session.execute(
            select(InvoiceTaxLine).where(InvoiceTaxLine.invoice_line_id.in_([ln.id for ln in inv_lines]))
        ).scalars()
    )
    cn_lines = list(
        session.execute(
            select(CreditNoteLine).where(CreditNoteLine.credit_note_id.in_([n.id for n, _ in notes_in]))
        ).scalars()
    )
    cn_taxes = list(
        session.execute(
            select(CreditNoteTaxLine).where(CreditNoteTaxLine.credit_note_line_id.in_([ln.id for ln in cn_lines]))
        ).scalars()
    )
    orig_lines = {
        ln.id: ln
        for ln in session.execute(
            select(InvoiceLine).where(InvoiceLine.id.in_({ln.invoice_line_id for ln in cn_lines}))
        ).scalars()
    }
    names = catalog.names_for(session, {ln.item_id for ln in inv_lines} | {ln.item_id for ln in orig_lines.values()})

    def heads(rows: list[Any], key: str, line_id: uuid.UUID) -> dict[str, Decimal]:
        found = {t.tax: t.amount for t in rows if getattr(t, key) == line_id}
        return {h: found.get(h, Decimal("0.00")) for h in ("CGST", "SGST", "IGST")}

    rate_of: dict[uuid.UUID, Decimal] = {}
    for t in inv_taxes:
        rate_of[t.invoice_line_id] = rate_of.get(t.invoice_line_id, Decimal(0)) + t.rate_pct
    for inv in invoices_in:
        c = customer(inv.customer_id)
        for ln in sorted((x for x in inv_lines if x.invoice_id == inv.id), key=lambda x: x.line_no):
            h = heads(inv_taxes, "invoice_line_id", ln.id)
            out.append(
                {
                    "doc_type": "INV",
                    "doc_id": str(inv.id),
                    "doc_no": inv.invoice_no,
                    "doc_date": inv.invoice_date.isoformat(),
                    "status": inv.status,
                    "customer_id": str(inv.customer_id),
                    "customer": c["name"],
                    "gstin": inv.customer_gstin,
                    "place_of_supply": inv.place_of_supply,
                    "regime": inv.regime,
                    "hsn": ln.hsn,
                    "item_id": str(ln.item_id),
                    "item": names[ln.item_id][1],
                    "qty": str(ln.qty),
                    "gst_rate": str(rate_of.get(ln.id, Decimal(0)).normalize()),
                    "taxable": str(ln.taxable),
                    "cgst": str(h["CGST"]),
                    "sgst": str(h["SGST"]),
                    "igst": str(h["IGST"]),
                    "total": str(ln.taxable + h["CGST"] + h["SGST"] + h["IGST"]),
                    "original_doc_no": None,
                }
            )
    for note, inv in notes_in:
        c = customer(inv.customer_id)
        for cl in sorted((x for x in cn_lines if x.credit_note_id == note.id), key=lambda x: x.line_no):
            orig = orig_lines[cl.invoice_line_id]
            h = heads(cn_taxes, "credit_note_line_id", cl.id)
            out.append(
                {
                    "doc_type": "CN",
                    "doc_id": str(note.id),
                    "invoice_id": str(inv.id),
                    "doc_no": note.credit_note_no,
                    "doc_date": note.note_date.isoformat(),
                    "status": "POSTED",
                    "customer_id": str(inv.customer_id),
                    "customer": c["name"],
                    "gstin": inv.customer_gstin,
                    "place_of_supply": inv.place_of_supply,
                    "regime": inv.regime,
                    "hsn": orig.hsn,
                    "item_id": str(orig.item_id),
                    "item": names[orig.item_id][1],
                    "qty": str(-cl.qty),
                    "gst_rate": str(rate_of.get(orig.id, Decimal(0)).normalize()) if orig.id in rate_of else "",
                    "taxable": str(-cl.taxable),
                    "cgst": str(-h["CGST"]),
                    "sgst": str(-h["SGST"]),
                    "igst": str(-h["IGST"]),
                    "total": str(-(cl.taxable + h["CGST"] + h["SGST"] + h["IGST"])),
                    "original_doc_no": inv.invoice_no,
                }
            )
    return out


def documents_issued(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """GSTR-1 table 13: per series, the first and last number, how many were issued and how many cancelled."""
    out = []
    for kind, model, no_col, date_col in (
        ("Invoices for outward supply", Invoice, Invoice.invoice_no, Invoice.invoice_date),
        ("Credit notes", CreditNote, CreditNote.credit_note_no, CreditNote.note_date),
    ):
        nos = list(
            session.execute(select(no_col).where(date_col >= date_from, date_col <= date_to).order_by(no_col)).scalars()
        )
        cancelled = 0
        if model is Invoice:
            cancelled = int(
                session.execute(
                    select(func.count()).where(
                        Invoice.invoice_date >= date_from,
                        Invoice.invoice_date <= date_to,
                        Invoice.status == "CANCELLED",
                    )
                ).scalar_one()
            )
        out.append(
            {
                "nature": kind,
                "from": nos[0] if nos else "",
                "to": nos[-1] if nos else "",
                "total": str(len(nos)),
                "cancelled": str(cancelled),
                "net_issued": str(len(nos) - cancelled),
            }
        )
    return out


def tax_line_mismatches(session: Session) -> list[dict[str, str]]:
    """Integrity (law 4, per document): each invoice's tax lines add up to its tax_total and its lines to its
    taxable value (sees all orgs as the owner). The GST summary and export arrive with MP11."""
    rows = session.execute(
        text(
            """
            WITH l AS (SELECT invoice_id, sum(taxable) AS taxable FROM invoice_lines GROUP BY invoice_id),
                 t AS (SELECT il.invoice_id, sum(tl.amount) AS tax FROM invoice_tax_lines tl
                       JOIN invoice_lines il ON il.id = tl.invoice_line_id GROUP BY il.invoice_id)
            SELECT i.organization_id, i.invoice_no, i.taxable, l.taxable, i.tax_total, coalesce(t.tax, 0)
              FROM invoices i JOIN l ON l.invoice_id = i.id LEFT JOIN t ON t.invoice_id = i.id
             WHERE i.taxable <> l.taxable OR i.tax_total <> coalesce(t.tax, 0)
            """
        )
    ).all()
    return [
        {
            "organization_id": str(o),
            "invoice_no": n,
            "header_taxable": str(ht),
            "lines_taxable": str(lt),
            "header_tax": str(htx),
            "lines_tax": str(ltx),
        }
        for o, n, ht, lt, htx, ltx in rows
    ]
