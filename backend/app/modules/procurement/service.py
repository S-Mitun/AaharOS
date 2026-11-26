"""Procurement use cases (MP05): suppliers, purchase receipts, reversals and the purchase register.

Other modules call only this file. Functions run in the caller's transaction and do not commit (the API route
commits). A receipt posts in one savepoint:
  claim the Idempotency-Key -> gapless GRN number -> receipt + lines as DRAFT -> supplier lot records ->
  SUPPLIER -> store journal at accepted qty x rate -> POSTED -> audit row -> store the response for replays.
A refusal anywhere rolls the whole savepoint back, the GRN number included, so numbers stay gapless.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import idempotency
from app.core.calendar import financial_year
from app.core.errors import DomainError, NotFoundError
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.ledger import service as ledger
from app.modules.ledger.domain import LineSpec
from app.modules.procurement import domain
from app.modules.procurement.domain import ReceiptError, ReceiptLineIn
from app.modules.procurement.models import PurchaseReceipt, PurchaseReceiptLine, Supplier
from app.modules.uom.domain import normalise

DOC_TYPE = "GRN"


def _db_error(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


# ---------- suppliers ----------


def create_supplier(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    code: str,
    name: str,
    state_code: str,
    gstin: str | None = None,
) -> uuid.UUID:
    supplier_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                insert(Supplier).values(
                    id=supplier_id,
                    organization_id=organization_id,
                    code=code,
                    name=name,
                    state_code=state_code,
                    gstin=gstin,
                    created_by=actor_id,
                )
            )
    except DBAPIError as exc:
        err = _db_error(exc)
        if err.code == "duplicate":
            raise DomainError("supplier_code_taken", f"a supplier with code {code!r} already exists") from exc
        raise err from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="supplier.create",
        entity_type="supplier",
        entity_id=supplier_id,
        after={"code": code, "name": name, "state_code": state_code, "gstin": gstin},
    )
    return supplier_id


def list_suppliers(session: Session) -> list[dict[str, Any]]:
    return [
        {"id": str(s.id), "code": s.code, "name": s.name, "state_code": s.state_code, "gstin": s.gstin}
        for s in session.execute(select(Supplier).order_by(Supplier.code)).scalars()
    ]


# ---------- receipts ----------


@dataclass(frozen=True)
class ReceiptResult:
    receipt_id: uuid.UUID
    receipt_no: str
    journal_id: uuid.UUID
    replayed: bool  # True when an Idempotency-Key replay returned the original receipt


def post_receipt(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    supplier_id: uuid.UUID,
    supplier_invoice_ref: str | None,
    received_on: date,
    lines: Sequence[ReceiptLineIn],
    idempotency_key: uuid.UUID | None = None,
) -> ReceiptResult:
    """Record a delivery and post it to stock at accepted qty x rate. A duplicate submit returns the first receipt."""
    item_ids = {line.item_id for line in lines}
    units = catalog.units_for(session, item_ids)
    kinds = catalog.kinds_for(session, item_ids)
    plan = domain.plan_receipt(lines, {i: (units[i], kinds[i]) for i in item_ids})
    if session.execute(select(Supplier.id).where(Supplier.id == supplier_id)).scalar_one_or_none() is None:
        raise NotFoundError("supplier_not_found", "unknown supplier", {"supplier_id": str(supplier_id)})
    invoice_ref = (supplier_invoice_ref or "").strip() or None
    digest = idempotency.request_hash(domain.request_doc(supplier_id, invoice_ref, received_on, plan))

    try:
        with session.begin_nested():
            if idempotency_key is not None:
                stored = idempotency.claim(session, organization_id, idempotency_key, digest)
                if stored is not None:
                    if "receipt_id" not in stored.body:
                        raise DomainError(
                            "idempotency_key_reused", "this Idempotency-Key belongs to a different kind of request"
                        )
                    return ReceiptResult(
                        uuid.UUID(stored.body["receipt_id"]),
                        stored.body["receipt_no"],
                        uuid.UUID(stored.body["journal_id"]),
                        replayed=True,
                    )
            number = session.execute(
                text("SELECT aahar_next_doc_number(:o, :t, :fy)"),
                {"o": organization_id, "t": DOC_TYPE, "fy": financial_year(received_on)},
            ).scalar_one()
            receipt_no = domain.receipt_no(financial_year(received_on), int(number))
            receipt_id = uuid.uuid4()
            session.execute(
                insert(PurchaseReceipt).values(
                    id=receipt_id,
                    organization_id=organization_id,
                    receipt_no=receipt_no,
                    supplier_id=supplier_id,
                    supplier_invoice_ref=invoice_ref,
                    received_on=received_on,
                    status="DRAFT",
                    idempotency_key=idempotency_key,
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(PurchaseReceiptLine),
                [
                    {
                        "organization_id": organization_id,
                        "receipt_id": receipt_id,
                        "line_no": p.line_no,
                        "item_id": p.item_id,
                        "qty_entered": p.qty_entered,
                        "uom_entered": p.unit,
                        "qty_base": p.qty_base,
                        "rate": p.rate,
                        "value": p.value,
                        "freight": p.freight,
                        "accepted_base": p.accepted_base,
                        "rejected_base": p.rejected_base,
                        "lot_no": p.lot_no,
                        "created_by": actor_id,
                    }
                    for p in plan
                ],
            )
            for p in plan:  # decision D4: the supplier's lot is recorded for traceability, raw stock stays lot-less
                if p.lot_no and ledger.lot_id_by_no(session, p.item_id, p.lot_no) is None:
                    ledger.create_lot(
                        session,
                        organization_id=organization_id,
                        actor_id=actor_id,
                        item_id=p.item_id,
                        lot_no=p.lot_no,
                        source_type="purchase_receipt",
                        source_id=receipt_id,
                        mfg_date=p.mfg_date,
                        best_before=p.best_before,
                    )
            stock_lines: list[LineSpec] = []
            for p in plan:
                if p.accepted_base == 0:
                    continue
                base = units[p.item_id].base_uom
                stock_lines += [
                    LineSpec(p.item_id, p.store, p.accepted_base, base, p.value),
                    LineSpec(p.item_id, "SUPPLIER", -p.accepted_base, base, -p.value),
                ]
            posted = ledger.post(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                kind="RECEIPT",
                source_type="purchase_receipt",
                source_id=receipt_id,
                posting_date=received_on,
                lines=stock_lines,
            )
            session.execute(
                update(PurchaseReceipt)
                .where(PurchaseReceipt.id == receipt_id)
                .values(status="POSTED", posted_at=func.now(), journal_id=posted.journal_id)
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="receipt.post",
                entity_type="purchase_receipt",
                entity_id=receipt_id,
                after={
                    "receipt_no": receipt_no,
                    "supplier_id": supplier_id,
                    "supplier_invoice_ref": invoice_ref,
                    "received_on": received_on,
                    "journal_id": posted.journal_id,
                    "lines": [
                        {
                            "item_id": p.item_id,
                            "qty": p.qty_entered,
                            "unit": p.unit,
                            "rate": p.rate,
                            "accepted_base": p.accepted_base,
                            "rejected_base": p.rejected_base,
                            "value": p.value,
                            "freight": p.freight,
                            "lot_no": p.lot_no,
                        }
                        for p in plan
                    ],
                },
            )
            if idempotency_key is not None:
                idempotency.complete(
                    session,
                    organization_id,
                    idempotency_key,
                    201,
                    {"receipt_id": receipt_id, "receipt_no": receipt_no, "journal_id": posted.journal_id},
                )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return ReceiptResult(receipt_id, receipt_no, posted.journal_id, replayed=False)


def reverse_receipt(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, receipt_id: uuid.UUID, reason: str
) -> uuid.UUID:
    """Correct a posted receipt: the exact mirror journal, status REVERSED. Returns the reversal journal id."""
    if not reason.strip():
        raise ReceiptError("reason_required", "reversing a receipt needs a reason")
    receipt = session.execute(
        select(PurchaseReceipt).where(PurchaseReceipt.id == receipt_id).with_for_update()
    ).scalar_one_or_none()
    if receipt is None:
        raise NotFoundError("receipt_not_found", "unknown purchase receipt")
    if receipt.status != "POSTED" or receipt.journal_id is None:
        raise ReceiptError(
            "not_posted", f"receipt {receipt.receipt_no} is {receipt.status}: only a posted one reverses"
        )
    try:
        with session.begin_nested():
            reversal = ledger.reverse(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                journal_id=receipt.journal_id,
                reason=reason,
                posting_date=None,
            )
            session.execute(update(PurchaseReceipt).where(PurchaseReceipt.id == receipt_id).values(status="REVERSED"))
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="receipt.reverse",
                entity_type="purchase_receipt",
                entity_id=receipt_id,
                before={"status": "POSTED"},
                after={"status": "REVERSED", "reversal_journal_id": reversal.journal_id},
                note=reason.strip(),
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    session.expire(receipt)
    return reversal.journal_id


def _line_view(line: PurchaseReceiptLine, code: str) -> dict[str, Any]:
    return {
        "line_no": line.line_no,
        "item_id": str(line.item_id),
        "item_code": code,
        "qty": str(normalise(line.qty_entered)),
        "unit": line.uom_entered,
        "rate": str(normalise(line.rate)),
        "accepted_base": str(normalise(line.accepted_base)),
        "rejected_base": str(normalise(line.rejected_base)),
        "value": str(line.value),
        "freight": str(line.freight),
        "lot_no": line.lot_no,
    }


def get_receipt(session: Session, receipt_id: uuid.UUID) -> dict[str, Any]:
    row = session.execute(
        select(PurchaseReceipt, Supplier.code, Supplier.name)
        .join(Supplier, Supplier.id == PurchaseReceipt.supplier_id)
        .where(PurchaseReceipt.id == receipt_id)
    ).one_or_none()
    if row is None:
        raise NotFoundError("receipt_not_found", "unknown purchase receipt")
    receipt, supplier_code, supplier_name = row
    lines = list(
        session.execute(
            select(PurchaseReceiptLine)
            .where(PurchaseReceiptLine.receipt_id == receipt_id)
            .order_by(PurchaseReceiptLine.line_no)
        ).scalars()
    )
    codes = catalog.codes_for(session, {ln.item_id for ln in lines})
    return {
        "id": str(receipt.id),
        "receipt_no": receipt.receipt_no,
        "status": receipt.status,
        "supplier": {"id": str(receipt.supplier_id), "code": supplier_code, "name": supplier_name},
        "supplier_invoice_ref": receipt.supplier_invoice_ref,
        "received_on": receipt.received_on.isoformat(),
        "journal_id": None if receipt.journal_id is None else str(receipt.journal_id),
        "lines": [_line_view(ln, codes[ln.item_id]) for ln in lines],
        "stock_value": str(sum((ln.value for ln in lines), Decimal(0))),
        "freight_excluded_from_stock": str(sum((ln.freight for ln in lines), Decimal(0))),
    }


def register(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    supplier_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """The purchase register: every receipt line in the range. Totals count POSTED receipts only."""
    if date_from and date_to and date_from > date_to:
        raise DomainError("bad_date_range", "date_from is after date_to")
    query = (
        select(PurchaseReceiptLine, PurchaseReceipt, Supplier.code, Supplier.name)
        .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseReceiptLine.receipt_id)
        .join(Supplier, Supplier.id == PurchaseReceipt.supplier_id)
        .where(PurchaseReceipt.status != "DRAFT")
        .order_by(PurchaseReceipt.received_on, PurchaseReceipt.receipt_no, PurchaseReceiptLine.line_no)
    )
    if date_from:
        query = query.where(PurchaseReceipt.received_on >= date_from)
    if date_to:
        query = query.where(PurchaseReceipt.received_on <= date_to)
    if supplier_id:
        query = query.where(PurchaseReceipt.supplier_id == supplier_id)
    rows = session.execute(query).all()
    codes = catalog.codes_for(session, {ln.item_id for ln, *_ in rows})
    posted = [ln for ln, r, *_ in rows if r.status == "POSTED"]
    return {
        "rows": [
            {
                "receipt_id": str(r.id),
                "receipt_no": r.receipt_no,
                "status": r.status,
                "received_on": r.received_on.isoformat(),
                "supplier_code": scode,
                "supplier_name": sname,
                "supplier_invoice_ref": r.supplier_invoice_ref,
                **_line_view(ln, codes[ln.item_id]),
            }
            for ln, r, scode, sname in rows
        ],
        "totals": {
            "receipts": len({ln.receipt_id for ln in posted}),
            "stock_value": str(sum((ln.value for ln in posted), Decimal(0))),
            "freight_excluded_from_stock": str(sum((ln.freight for ln in posted), Decimal(0))),
        },
        "note": "Totals count POSTED receipts; reversed ones are listed with their status.",
    }


def receipt_value_mismatches(session: Session) -> list[dict[str, str]]:
    """Integrity: for every posted or reversed receipt, Σ accepted line values = the value its journal brought into
    the stores. Empty means every receipt's stock value is explained by its lines (sees all orgs as the owner)."""
    rows = session.execute(
        text(
            """
            WITH lines AS (
              SELECT receipt_id, sum(value) AS v FROM purchase_receipt_lines GROUP BY receipt_id
            ), posted AS (
              SELECT r.id AS receipt_id, coalesce(sum(sl.value) FILTER (WHERE sl.qty_base > 0), 0) AS v
                FROM purchase_receipts r JOIN stock_lines sl ON sl.journal_id = r.journal_id
               WHERE r.status IN ('POSTED', 'REVERSED') GROUP BY r.id
            )
            SELECT r.organization_id, r.receipt_no, l.v, p.v
              FROM purchase_receipts r JOIN lines l ON l.receipt_id = r.id JOIN posted p ON p.receipt_id = r.id
             WHERE l.v <> p.v
            """
        )
    ).all()
    return [
        {"organization_id": str(o), "receipt_no": n, "lines_value": str(lv), "journal_value": str(jv)}
        for o, n, lv, jv in rows
    ]


@dataclass(frozen=True)
class ReceivedLot:
    """One receipt line of one item, as traceability reads it (MP13, T2). `lot_no` is None when none was recorded."""

    receipt_id: uuid.UUID
    receipt_no: str
    status: str
    received_on: date
    journal_id: uuid.UUID | None
    supplier_code: str
    supplier_name: str
    item_id: uuid.UUID
    lot_no: str | None
    accepted_base: Decimal
    rejected_base: Decimal


def received_lots(
    session: Session, *, item_id: uuid.UUID | None = None, journal_ids: Sequence[uuid.UUID] | None = None
) -> list[ReceivedLot]:
    """Receipt lines of posted or reversed receipts, by item or by the receipt journals that posted them."""
    query = (
        select(
            PurchaseReceipt.id,
            PurchaseReceipt.receipt_no,
            PurchaseReceipt.status,
            PurchaseReceipt.received_on,
            PurchaseReceipt.journal_id,
            Supplier.code,
            Supplier.name,
            PurchaseReceiptLine.item_id,
            PurchaseReceiptLine.lot_no,
            PurchaseReceiptLine.accepted_base,
            PurchaseReceiptLine.rejected_base,
        )
        .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseReceiptLine.receipt_id)
        .join(Supplier, Supplier.id == PurchaseReceipt.supplier_id)
        .where(PurchaseReceipt.status != "DRAFT")
        .order_by(PurchaseReceipt.received_on, PurchaseReceipt.receipt_no, PurchaseReceiptLine.line_no)
    )
    if item_id is not None:
        query = query.where(PurchaseReceiptLine.item_id == item_id)
    if journal_ids is not None:
        query = query.where(PurchaseReceipt.journal_id.in_(list(journal_ids)))
    return [ReceivedLot(*row) for row in session.execute(query).all()]
