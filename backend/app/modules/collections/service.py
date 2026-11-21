"""Collections use cases (MP10, ADR-0017, J8): payments, their allocation to invoices (by hand or oldest-due first),
advances as the unallocated balance, what each customer owes, and MSME due dates. Other modules call only this file;
functions never commit.

Outstanding per invoice = total - payments allocated - credit notes. Over-allocation is refused here first and by the
database guard (`aahar_check_allocation`, SQLSTATE AH004) as the last line of defence.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import idempotency
from app.core.calendar import business_date, financial_year
from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.billing import service as billing
from app.modules.collections.models import MODES, Payment, PaymentAllocation
from app.modules.sales import service as sales

DOC_TYPE: Final = "RCP"


class CollectionError(DomainError):
    """A payment or allocation the books refuse."""


def _db_error(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


def allocated_to_invoice(session: Session, invoice_id: uuid.UUID) -> Decimal:
    value = session.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(PaymentAllocation.invoice_id == invoice_id)
    ).scalar_one()
    return Decimal(value)


billing.register_allocated_provider(allocated_to_invoice)


@dataclass(frozen=True)
class OpenInvoice:
    invoice_id: uuid.UUID
    invoice_no: str
    invoice_date: date
    due_date: date
    total: Decimal
    paid: Decimal
    credited: Decimal

    @property
    def outstanding(self) -> Decimal:
        return self.total - self.paid - self.credited


def open_invoices(session: Session, customer_id: uuid.UUID) -> list[OpenInvoice]:
    out = []
    for b in billing.invoices(session, customer_id=customer_id, status="POSTED"):
        out.append(
            OpenInvoice(
                b.id, b.invoice_no, b.invoice_date, b.due_date, b.total, allocated_to_invoice(session, b.id), b.credited
            )
        )
    return sorted(out, key=lambda i: (i.due_date, i.invoice_date, i.invoice_no))


def outstanding_explained(session: Session, customer_id: uuid.UUID) -> Explained:
    """What a customer owes (H7 provider for the credit check): Σ (invoice total - paid - credited)."""
    rows = open_invoices(session, customer_id)
    inputs = []
    for r in rows:
        src = SourceRef("invoice", str(r.invoice_id))
        inputs += [
            ExplainedInput(f"{r.invoice_no} total", r.total, "INR", src),
            ExplainedInput(f"{r.invoice_no} paid", -r.paid, "INR", src),
            ExplainedInput(f"{r.invoice_no} credited", -r.credited, "INR", src),
        ]
    return Explained(
        value=round_money(sum((r.outstanding for r in rows), Decimal(0))),
        unit="INR",
        formula="Σ invoices (total - payments allocated - credit notes)",
        inputs=tuple(inputs),
        method="Outstanding",
    )


sales.register_outstanding_provider(outstanding_explained)


@dataclass(frozen=True)
class AllocationIn:
    invoice_id: uuid.UUID
    amount: Decimal


def _plan_allocations(
    open_rows: Sequence[OpenInvoice], amount: Decimal, wanted: Sequence[AllocationIn] | None
) -> list[AllocationIn]:
    """Manual allocations are checked against each invoice's outstanding and the payment; None means oldest-due
    first. Whatever is left stays on the payment as an advance."""
    by_id = {r.invoice_id: r for r in open_rows}
    if wanted is None:
        plan, left = [], amount
        for r in open_rows:
            if left <= 0:
                break
            take = min(left, r.outstanding)
            if take > 0:
                plan.append(AllocationIn(r.invoice_id, take))
                left -= take
        return plan
    total = Decimal(0)
    for a in wanted:
        found = by_id.get(a.invoice_id)
        if found is None:
            raise CollectionError(
                "invoice_not_open",
                "that invoice is not a posted invoice of this customer",
                {"invoice_id": str(a.invoice_id)},
            )
        if a.amount <= 0 or a.amount != round_money(a.amount):
            raise CollectionError("bad_amount", "an allocation is a positive rupee amount with at most two decimals")
        if a.amount > found.outstanding:
            raise CollectionError(
                "over_allocation",
                f"{found.invoice_no} has only {found.outstanding} outstanding",
                {"invoice_no": found.invoice_no, "outstanding": str(found.outstanding)},
            )
        total += a.amount
    if total > amount:
        raise CollectionError("allocations_exceed_payment", "the allocations add up to more than the payment")
    return list(wanted)


@dataclass(frozen=True)
class PaymentResult:
    payment_id: uuid.UUID
    payment_no: str
    replayed: bool


def record_payment(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    customer_id: uuid.UUID,
    amount: Decimal,
    received_on: date | None = None,
    mode: str = "UPI",
    reference: str | None = None,
    allocations: Sequence[AllocationIn] | None = None,
    idempotency_key: uuid.UUID | None = None,
) -> PaymentResult:
    """Record money received and allocate it (by hand, or oldest-due first when none are given)."""
    if mode not in MODES:
        raise CollectionError("bad_mode", f"mode must be one of {', '.join(MODES)}")
    if not isinstance(amount, Decimal) or amount <= 0 or amount != round_money(amount):
        raise CollectionError("bad_amount", "a payment is a positive rupee amount with at most two decimals")
    on = received_on or business_date()
    sales.customer_terms(session, customer_id)  # 404 if unknown
    rows = open_invoices(session, customer_id)
    plan = _plan_allocations(rows, amount, allocations)
    digest = idempotency.request_hash(
        {
            "kind": "payment",
            "customer_id": customer_id,
            "amount": amount,
            "date": on,
            "mode": mode,
            "reference": (reference or "").strip(),
            "allocations": None if allocations is None else sorted([str(a.invoice_id), a.amount] for a in allocations),
        }
    )
    try:
        with session.begin_nested():
            if idempotency_key is not None:
                stored = idempotency.claim(session, organization_id, idempotency_key, digest)
                if stored is not None:
                    if "payment_id" not in stored.body:
                        raise DomainError("idempotency_key_reused", "this Idempotency-Key belongs to another request")
                    return PaymentResult(uuid.UUID(stored.body["payment_id"]), stored.body["payment_no"], True)
            fy = financial_year(on)
            number = session.execute(
                text("SELECT aahar_next_doc_number(:o, :t, :fy)"), {"o": organization_id, "t": DOC_TYPE, "fy": fy}
            ).scalar_one()
            payment_no = f"{DOC_TYPE}/{fy}/{int(number):06d}"
            payment_id = uuid.uuid4()
            session.execute(
                insert(Payment).values(
                    id=payment_id,
                    organization_id=organization_id,
                    payment_no=payment_no,
                    customer_id=customer_id,
                    received_on=on,
                    amount=amount,
                    mode=mode,
                    reference=(reference or "").strip() or None,
                    idempotency_key=idempotency_key,
                    created_by=actor_id,
                )
            )
            for a in plan:
                session.execute(
                    insert(PaymentAllocation).values(
                        organization_id=organization_id,
                        payment_id=payment_id,
                        invoice_id=a.invoice_id,
                        amount=a.amount,
                        created_by=actor_id,
                    )
                )
            allocated = sum((a.amount for a in plan), Decimal(0))
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="payment.post",
                entity_type="payment",
                entity_id=payment_id,
                after={
                    "payment_no": payment_no,
                    "customer_id": customer_id,
                    "amount": amount,
                    "mode": mode,
                    "received_on": on,
                    "allocations": [{"invoice_id": a.invoice_id, "amount": a.amount} for a in plan],
                    "advance": amount - allocated,
                },
            )
            if idempotency_key is not None:
                idempotency.complete(
                    session, organization_id, idempotency_key, 201, {"payment_id": payment_id, "payment_no": payment_no}
                )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return PaymentResult(payment_id, payment_no, False)


def advance_of(session: Session, customer_id: uuid.UUID) -> Decimal:
    paid = session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.customer_id == customer_id)
    ).scalar_one()
    allocated = session.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.customer_id == customer_id)
    ).scalar_one()
    return round_money(Decimal(paid) - Decimal(allocated))


def statement(session: Session, customer_id: uuid.UUID, on: date | None = None) -> dict[str, Any]:
    """A customer's open invoices with due dates and overdue flags, payments, and the advance held."""
    today = on or business_date()
    customer = sales.customer_terms(session, customer_id)
    rows = open_invoices(session, customer_id)
    payments = session.execute(
        select(Payment).where(Payment.customer_id == customer_id).order_by(Payment.received_on, Payment.payment_no)
    ).scalars()
    return {
        "customer": customer,
        "as_of": today.isoformat(),
        "outstanding": outstanding_explained(session, customer_id).to_json(),
        "advance": str(advance_of(session, customer_id)),
        "invoices": [
            {
                "invoice_id": str(r.invoice_id),
                "invoice_no": r.invoice_no,
                "invoice_date": r.invoice_date.isoformat(),
                "due_date": r.due_date.isoformat(),
                "total": str(r.total),
                "paid": str(r.paid),
                "credited": str(r.credited),
                "outstanding": str(r.outstanding),
                "overdue": r.outstanding > 0 and today > r.due_date,
                "days_overdue": max(0, (today - r.due_date).days) if r.outstanding > 0 else 0,
            }
            for r in rows
        ],
        "payments": [
            {
                "id": str(p.id),
                "payment_no": p.payment_no,
                "received_on": p.received_on.isoformat(),
                "amount": str(p.amount),
                "mode": p.mode,
                "reference": p.reference,
            }
            for p in payments
        ],
    }


def overview(session: Session) -> dict[str, Any]:
    """Every customer: outstanding, overdue, advance (the Collections screen)."""
    out = []
    total = Decimal(0)
    for c in sales.customers_brief(session):
        cid = uuid.UUID(c["id"])
        rows = open_invoices(session, cid)
        owed = sum((r.outstanding for r in rows), Decimal(0))
        overdue = sum((r.outstanding for r in rows if r.outstanding > 0 and business_date() > r.due_date), Decimal(0))
        total += owed
        out.append(
            {
                "customer_id": c["id"],
                "customer_name": c["name"],
                "outstanding": str(round_money(owed)),
                "overdue": str(round_money(overdue)),
                "advance": str(advance_of(session, cid)),
                "open_invoices": sum(1 for r in rows if r.outstanding > 0),
            }
        )
    return {"customers": out, "total_outstanding": str(round_money(total))}
