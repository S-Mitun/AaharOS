"""Dispatch use cases (MP10, ADR-0017): FEFO picking from an invoice, the DISPATCH journal (FG_STORE -> CUSTOMER
at lot value, i.e. cost of goods sold) consuming the order's reservations, partial dispatch, and the e-way bill
check with a MOCK payload. Other modules call only this file; functions never commit.

A dispatch posts in one savepoint: claim the key -> gapless DSP number -> reservations split so exactly the packets
leaving are consumed -> the journal -> the dispatch row (insert-only) and its lines -> the order's status -> audit.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
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
from app.modules.billing import service as billing
from app.modules.catalog import service as catalog
from app.modules.dispatch import domain
from app.modules.dispatch.domain import DispatchError, LotAvailable, Pick
from app.modules.dispatch.models import Dispatch, DispatchLine
from app.modules.ledger import service as ledger
from app.modules.ledger.domain import LineSpec
from app.modules.sales import service as sales
from app.modules.tax import service as tax


def _db_error(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


# ---------- what billing asks (registered below) ----------


def facts(session: Session, invoice_id: uuid.UUID) -> dict[str, Any]:
    """Packets dispatched per item for an invoice, and the lots they came from."""
    rows = session.execute(
        select(DispatchLine.item_id, DispatchLine.lot_id, func.sum(DispatchLine.qty))
        .join(Dispatch, Dispatch.id == DispatchLine.dispatch_id)
        .where(Dispatch.invoice_id == invoice_id)
        .group_by(DispatchLine.item_id, DispatchLine.lot_id)
    ).tuples()
    packets: dict[uuid.UUID, int] = {}
    lots = []
    for item, lot, qty in rows:
        packets[item] = packets.get(item, 0) + int(qty)
        lots.append({"item_id": str(item), "lot_no": ledger.lot_no(session, lot), "qty": str(int(qty))})
    return {"packets": packets, "lots": sorted(lots, key=lambda x: x["lot_no"])}


billing.register_dispatch_facts(facts)


# ---------- the plan (preview and post share it) ----------


@dataclass(frozen=True)
class LinePlan:
    item_id: uuid.UUID
    item_name: str
    invoiced: int
    already: int
    now: int
    picks: list[Pick]
    fefo: bool


@dataclass(frozen=True)
class Plan:
    invoice_id: uuid.UUID
    invoice_no: str
    order_id: uuid.UUID
    regime: str
    lines: list[LinePlan]
    consignment_value: Decimal
    eway: Any  # tax.domain.EwayVerdict
    dispatch_date: date


def plan_dispatch(
    session: Session,
    invoice_id: uuid.UUID,
    *,
    qty: Mapping[uuid.UUID, int] | None = None,
    chosen_lots: Mapping[uuid.UUID, Mapping[uuid.UUID, int]] | None = None,
    override_reason: str | None = None,
    dispatch_date: date | None = None,
) -> Plan:
    """What would leave, from which lots, at what value, and whether an e-way bill is needed. No writes."""
    view = billing.invoice_view(session, invoice_id)
    if view["status"] != "POSTED":
        raise DispatchError("invoice_not_posted", f"invoice {view['invoice_no']} is {view['status']}")
    if view["order_id"] is None:
        raise DispatchError("invoice_without_order", "only invoices raised from an order are dispatched here")
    on = dispatch_date or business_date()
    if on < date.fromisoformat(view["invoice_date"]):
        raise DispatchError("dispatch_before_invoice", "goods cannot leave before their invoice date")
    lines = []
    value_rows = []
    for ln in view["lines"]:
        item = uuid.UUID(ln["item_id"])
        invoiced, already = int(ln["qty"]), int(ln["dispatched"])
        left = invoiced - already
        now = left if qty is None else int(qty.get(item, 0))
        if now < 0 or now > left:
            raise DispatchError(
                "qty_beyond_invoice", f"{left} packets of {ln['item_name']} are left to dispatch", {"left": left}
            )
        picks: list[Pick] = []
        fefo = True
        if now:
            lots = [
                LotAvailable(lot.lot_id, lot.lot_no, int(lot.qty_base), lot.value)
                for lot in ledger.fefo_lots(session, item, as_of=on)
            ]
            chosen = (chosen_lots or {}).get(item)
            picks = domain.pick_chosen(lots, chosen, now, override_reason) if chosen else domain.pick_fefo(lots, now)
            fefo = domain.is_fefo(lots, picks)
        total_with_tax = Decimal(ln["taxable"]) + sum((Decimal(t["amount"]) for t in ln["taxes"]), Decimal(0))
        value_rows.append((invoiced, total_with_tax, now))
        lines.append(LinePlan(item, ln["item_name"], invoiced, already, now, picks, fefo))
    if not any(ln.now for ln in lines):
        raise DispatchError("nothing_to_dispatch", "every packet on this invoice has already left")
    consignment = domain.consignment_value(value_rows)
    eway = tax.eway_verdict(session, view["regime"], consignment, on)
    return Plan(
        uuid.UUID(view["id"]),
        view["invoice_no"],
        uuid.UUID(view["order_id"]),
        view["regime"],
        lines,
        consignment,
        eway,
        on,
    )


def plan_view(plan: Plan) -> dict[str, Any]:
    return {
        "invoice_id": str(plan.invoice_id),
        "invoice_no": plan.invoice_no,
        "dispatch_date": plan.dispatch_date.isoformat(),
        "lines": [
            {
                "item_id": str(ln.item_id),
                "item_name": ln.item_name,
                "invoiced": str(ln.invoiced),
                "already_dispatched": str(ln.already),
                "now": str(ln.now),
                "fefo": ln.fefo,
                "picks": [{"lot_no": p.lot_no, "qty": str(p.qty), "value": str(p.value)} for p in ln.picks],
                "stock_movement": [
                    f"FG_STORE -{p.qty} / CUSTOMER +{p.qty} (lot {p.lot_no}, {p.value})" for p in ln.picks
                ],
            }
            for ln in plan.lines
        ],
        "cost_of_goods": str(sum((p.value for ln in plan.lines for p in ln.picks), Decimal(0))),
        "consignment_value": str(plan.consignment_value),
        "eway": {
            "required": plan.eway.required,
            "reason": plan.eway.reason,
            "threshold": str(plan.eway.threshold),
            "mock": True,
        },
    }


def _mock_payload(session: Session, plan: Plan, dispatch_no: str) -> dict[str, Any]:
    view = billing.invoice_view(session, plan.invoice_id)
    return {
        "_notice": "MOCK e-way bill payload: never sent to the e-way bill portal (DEMO)",
        "supplyType": "O",
        "subSupplyType": "1",
        "docType": "INV",
        "docNo": view["invoice_no"],
        "docDate": view["invoice_date"],
        "fromGstin": view["profile"].get("gstin"),
        "fromStateCode": view["supplier"]["state_code"],
        "toGstin": view["customer"].get("gstin"),
        "toStateCode": view["customer"]["state_code"],
        "transactionType": 1,
        "totInvValue": str(plan.consignment_value),
        "dispatchNo": dispatch_no,
        "required": plan.eway.required,
        "reason": plan.eway.reason,
        "itemList": [
            {
                "hsnCode": ln["hsn"],
                "quantity": str(next(p.now for p in plan.lines if str(p.item_id) == ln["item_id"])),
                "qtyUnit": "PCS",
            }
            for ln in view["lines"]
        ],
    }


@dataclass(frozen=True)
class DispatchResult:
    dispatch_id: uuid.UUID
    dispatch_no: str
    journal_id: uuid.UUID
    replayed: bool


def dispatch_invoice(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    invoice_id: uuid.UUID,
    qty: Mapping[uuid.UUID, int] | None = None,
    chosen_lots: Mapping[uuid.UUID, Mapping[uuid.UUID, int]] | None = None,
    override_reason: str | None = None,
    dispatch_date: date | None = None,
    idempotency_key: uuid.UUID | None = None,
) -> DispatchResult:
    """Send the invoiced packets (or part of them), FEFO unless lots are chosen with a reason."""
    plan = plan_dispatch(
        session,
        invoice_id,
        qty=qty,
        chosen_lots=chosen_lots,
        override_reason=override_reason,
        dispatch_date=dispatch_date,
    )
    sales.order_for_billing(session, plan.order_id, lock=True)  # one dispatch of an order at a time
    for ln in plan.lines:
        if ln.now:
            ledger.lock_item_stores(session, organization_id, ln.item_id)
    plan = plan_dispatch(  # again under the locks, so the lots and their values cannot move underneath
        session,
        invoice_id,
        qty=qty,
        chosen_lots=chosen_lots,
        override_reason=override_reason,
        dispatch_date=dispatch_date,
    )
    digest = idempotency.request_hash(
        {
            "kind": "dispatch",
            "invoice_id": invoice_id,
            "date": plan.dispatch_date,
            "lines": sorted([str(ln.item_id), ln.now, [[str(p.lot_id), p.qty] for p in ln.picks]] for ln in plan.lines),
        }
    )
    units = catalog.units_for(session, {ln.item_id for ln in plan.lines})
    line_ids = sales.order_line_ids(session, plan.order_id)
    try:
        with session.begin_nested():
            if idempotency_key is not None:
                stored = idempotency.claim(session, organization_id, idempotency_key, digest)
                if stored is not None:
                    if "dispatch_id" not in stored.body:
                        raise DomainError("idempotency_key_reused", "this Idempotency-Key belongs to another request")
                    return DispatchResult(
                        uuid.UUID(stored.body["dispatch_id"]),
                        stored.body["dispatch_no"],
                        uuid.UUID(stored.body["journal_id"]),
                        True,
                    )
            fy = financial_year(plan.dispatch_date)
            number = session.execute(
                text("SELECT aahar_next_doc_number(:o, :t, :fy)"),
                {"o": organization_id, "t": domain.DOC_TYPE, "fy": fy},
            ).scalar_one()
            dispatch_no = f"{domain.DOC_TYPE}/{fy}/{int(number):06d}"
            dispatch_id = uuid.uuid4()

            # exactly the packets leaving are consumed: a larger reservation is split (release, then hold two)
            reserved = sales.active_reservations_by_item(session, plan.order_id)
            consume: list[uuid.UUID] = []
            first_res: dict[uuid.UUID, uuid.UUID] = {}
            for ln in plan.lines:
                if not ln.now:
                    continue
                held = reserved.get(ln.item_id, [])
                if sum(q for _, q in held) < ln.now:
                    raise DispatchError(
                        "not_reserved", f"{ln.item_name}: fewer packets are held for this order than are leaving"
                    )
                need = ln.now
                for res_id, res_qty in held:
                    if need == 0:
                        break
                    if res_qty <= need:
                        consume.append(res_id)
                        first_res.setdefault(ln.item_id, res_id)
                        need -= res_qty
                        continue
                    ledger.release(
                        session,
                        organization_id=organization_id,
                        actor_id=actor_id,
                        reservation_id=res_id,
                        reason=f"split for {dispatch_no}",
                    )
                    for part in (need, res_qty - need):
                        new_id = ledger.reserve(
                            session,
                            organization_id=organization_id,
                            actor_id=actor_id,
                            order_line_id=line_ids[ln.item_id],
                            item_id=ln.item_id,
                            qty_base=Decimal(part),
                            as_of=plan.dispatch_date,
                        )
                        if part == need:
                            consume.append(new_id)
                            first_res.setdefault(ln.item_id, new_id)
                    need = 0

            stock: list[LineSpec] = []
            for ln in plan.lines:
                base = units[ln.item_id].base_uom
                for p in ln.picks:
                    stock += [
                        LineSpec(ln.item_id, "FG_STORE", -Decimal(p.qty), base, -p.value, lot_id=p.lot_id),
                        LineSpec(ln.item_id, "CUSTOMER", Decimal(p.qty), base, p.value, lot_id=p.lot_id),
                    ]
            posted = ledger.post(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                kind="DISPATCH",
                source_type="dispatch",
                source_id=dispatch_id,
                posting_date=plan.dispatch_date,
                lines=stock,
                consume_reservation_ids=consume,
            )
            session.execute(
                insert(Dispatch).values(
                    id=dispatch_id,
                    organization_id=organization_id,
                    dispatch_no=dispatch_no,
                    dispatch_date=plan.dispatch_date,
                    invoice_id=plan.invoice_id,
                    journal_id=posted.journal_id,
                    eway_required=plan.eway.required,
                    eway_reason=plan.eway.reason,
                    eway_payload=_mock_payload(session, plan, dispatch_no),
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(DispatchLine),
                [
                    {
                        "organization_id": organization_id,
                        "dispatch_id": dispatch_id,
                        "reservation_id": first_res.get(ln.item_id),
                        "item_id": ln.item_id,
                        "lot_id": p.lot_id,
                        "qty": p.qty,
                        "override_reason": None if ln.fefo else (override_reason or "").strip(),
                        "created_by": actor_id,
                    }
                    for ln in plan.lines
                    for p in ln.picks
                ],
            )
            billing.sync_order(session, organization_id, actor_id, plan.order_id, f"dispatched {dispatch_no}")
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="dispatch.post",
                entity_type="dispatch",
                entity_id=dispatch_id,
                after={
                    "dispatch_no": dispatch_no,
                    "invoice_no": plan.invoice_no,
                    "journal_id": posted.journal_id,
                    "lines": [
                        {
                            "item_id": ln.item_id,
                            "packets": ln.now,
                            "fefo": ln.fefo,
                            "lots": [[p.lot_no, p.qty, p.value] for p in ln.picks],
                        }
                        for ln in plan.lines
                    ],
                    "eway_required": plan.eway.required,
                },
                note=None if all(ln.fefo for ln in plan.lines) else override_reason,
            )
            if idempotency_key is not None:
                idempotency.complete(
                    session,
                    organization_id,
                    idempotency_key,
                    201,
                    {"dispatch_id": dispatch_id, "dispatch_no": dispatch_no, "journal_id": posted.journal_id},
                )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return DispatchResult(dispatch_id, dispatch_no, posted.journal_id, False)


def dispatch_view(session: Session, dispatch_id: uuid.UUID) -> dict[str, Any]:
    d = session.execute(select(Dispatch).where(Dispatch.id == dispatch_id)).scalar_one_or_none()
    if d is None:
        raise NotFoundError("dispatch_not_found", "unknown dispatch")
    lines = list(session.execute(select(DispatchLine).where(DispatchLine.dispatch_id == d.id)).scalars())
    names = catalog.names_for(session, {ln.item_id for ln in lines})
    return {
        "id": str(d.id),
        "dispatch_no": d.dispatch_no,
        "dispatch_date": d.dispatch_date.isoformat(),
        "invoice_id": str(d.invoice_id),
        "journal_id": None if d.journal_id is None else str(d.journal_id),
        "eway": {"required": d.eway_required, "reason": d.eway_reason, "payload": d.eway_payload, "mock": True},
        "lines": [
            {
                "item_name": names[ln.item_id][1],
                "lot_no": ledger.lot_no(session, ln.lot_id),
                "qty": str(ln.qty),
                "override_reason": ln.override_reason,
            }
            for ln in lines
        ],
    }


def dispatches_for(session: Session, invoice_id: uuid.UUID) -> list[dict[str, Any]]:
    return [
        dispatch_view(session, d)
        for d in session.execute(
            select(Dispatch.id)
            .where(Dispatch.invoice_id == invoice_id)
            .order_by(Dispatch.dispatch_date, Dispatch.dispatch_no)
        ).scalars()
    ]


@dataclass(frozen=True)
class LotDispatch:
    """One dispatch line of a lot, with its invoice and customer (MP13, T1 forward)."""

    dispatch_id: uuid.UUID
    dispatch_no: str
    dispatch_date: date
    invoice_id: uuid.UUID
    invoice_no: str
    customer_id: uuid.UUID
    customer_code: str
    customer_name: str
    lot_id: uuid.UUID
    qty: int


def lot_dispatches(session: Session, lot_ids: list[uuid.UUID]) -> list[LotDispatch]:
    """Every dispatch line of these lots, oldest first (row-level security keeps it to the caller's org)."""
    if not lot_ids:
        return []
    rows = session.execute(
        text(
            """
            SELECT d.id, d.dispatch_no, d.dispatch_date, i.id, i.invoice_no, c.id, c.code, c.name, dl.lot_id,
                   sum(dl.qty)::int
              FROM dispatch_lines dl
              JOIN dispatches d ON d.id = dl.dispatch_id
              JOIN invoices i ON i.id = d.invoice_id
              JOIN customers c ON c.id = i.customer_id
             WHERE dl.lot_id = ANY(:lots)
             GROUP BY d.id, d.dispatch_no, d.dispatch_date, i.id, i.invoice_no, c.id, c.code, c.name, dl.lot_id
             ORDER BY d.dispatch_date, d.dispatch_no, c.code
            """
        ),
        {"lots": list(lot_ids)},
    ).all()
    return [LotDispatch(*r) for r in rows]


@dataclass(frozen=True)
class Delivery:
    """Packets of one lot sent to one customer on one dispatch (MP13, T5: the freshness radar)."""

    customer_id: uuid.UUID
    customer_code: str
    customer_name: str
    item_id: uuid.UUID
    lot_id: uuid.UUID
    lot_no: str
    best_before: date | None
    dispatch_id: uuid.UUID
    dispatch_no: str
    dispatch_date: date
    qty: int


def deliveries_since(session: Session, since: date) -> list[Delivery]:
    """Every dispatch line since a date, with the customer and the lot's best-before, oldest first."""
    rows = session.execute(
        text(
            """
            SELECT c.id, c.code, c.name, dl.item_id, l.id, l.lot_no, l.best_before, d.id, d.dispatch_no,
                   d.dispatch_date, sum(dl.qty)::int
              FROM dispatch_lines dl
              JOIN dispatches d ON d.id = dl.dispatch_id
              JOIN invoices i ON i.id = d.invoice_id
              JOIN customers c ON c.id = i.customer_id
              JOIN lots l ON l.id = dl.lot_id
             WHERE d.dispatch_date >= :since
             GROUP BY c.id, c.code, c.name, dl.item_id, l.id, l.lot_no, l.best_before, d.id, d.dispatch_no,
                      d.dispatch_date
             ORDER BY d.dispatch_date, d.dispatch_no, l.lot_no
            """
        ),
        {"since": since},
    ).all()
    return [Delivery(*r) for r in rows]


@dataclass(frozen=True)
class DispatchBrief:
    """A dispatch note as trip planning sees it (MP14): who it goes to and how many packets of each item."""

    dispatch_id: uuid.UUID
    dispatch_no: str
    dispatch_date: date
    invoice_no: str
    customer_id: uuid.UUID
    packets: dict[uuid.UUID, int]


def dispatch_briefs(
    session: Session, *, on: date | None = None, dispatch_ids: list[uuid.UUID] | None = None
) -> list[DispatchBrief]:
    """Dispatch notes of one date, or these notes, with their customer and packets per item, in number order."""
    rows = session.execute(
        text(
            "SELECT d.id, d.dispatch_no, d.dispatch_date, i.invoice_no, i.customer_id, dl.item_id, sum(dl.qty)::int"
            " FROM dispatches d JOIN invoices i ON i.id = d.invoice_id JOIN dispatch_lines dl ON dl.dispatch_id = d.id"
            " WHERE (CAST(:on AS date) IS NULL OR d.dispatch_date = :on)"
            " AND (CAST(:ids AS uuid[]) IS NULL OR d.id = ANY(:ids))"
            " GROUP BY d.id, d.dispatch_no, d.dispatch_date, i.invoice_no, i.customer_id, dl.item_id"
            " ORDER BY d.dispatch_no"
        ),
        {"on": on, "ids": dispatch_ids},
    ).all()
    out: dict[uuid.UUID, DispatchBrief] = {}
    for did, no, on_, inv, cust, item, qty in rows:
        brief = out.setdefault(did, DispatchBrief(did, no, on_, inv, cust, {}))
        brief.packets[item] = brief.packets.get(item, 0) + int(qty)
    return list(out.values())
