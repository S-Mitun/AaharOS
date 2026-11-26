"""Traceability use cases (MP13, ADR-0020). Read-only: nothing here posts, stores or sends anything.

Module 1: trace a lot backward and forward (T1), supplier lot -> batches by the "may contain" window (T2) and the
recall simulator (T3). Every figure is read from posted rows and links to its document.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core.calendar import business_date
from app.core.db import scoped_org
from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.modules.catalog import service as catalog
from app.modules.dispatch import service as dispatch
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.procurement import service as procurement
from app.modules.production import service as production
from app.modules.tax import service as tax
from app.modules.traceability import domain
from app.modules.traceability.domain import NoticeFacts, Shipment, StoreEvent
from app.modules.uom.domain import from_base, normalise

HOME_STORE: Final = {"RAW": "RAW_STORE", "PACK": "PACK_STORE"}
FG_STORE: Final = "FG_STORE"
MAY_CONTAIN_NOTE: Final = (
    "Raw and packing stock is not kept by supplier lot, so a supplier lot may be in every issue of that material"
    " after it arrived, until the store ran out of it. A recall may name an extra batch, never miss one."
)
SIMULATION_NOTE: Final = "DEMO simulation: nothing is stored and nothing is sent."


class TraceError(DomainError):
    pass


def _lot_kind(info: ledger.LotInfo) -> str:
    return {"production_run": "batch_lot", "purchase_receipt": "supplier_lot", "opening": "opening_lot"}[
        info.source_type
    ]


KIND_LABEL: Final = {"batch_lot": "Batch", "supplier_lot": "Supplier lot", "opening_lot": "Opening stock"}


def _lot_row(info: ledger.LotInfo, codes: dict[uuid.UUID, tuple[str, str]]) -> dict[str, Any]:
    kind = _lot_kind(info)
    code, name = codes.get(info.item_id, ("?", "?"))
    return {
        "lot_id": str(info.id),
        "lot_no": info.lot_no,
        "kind": kind,
        "kind_label": KIND_LABEL[kind],
        "item_id": str(info.item_id),
        "item_code": code,
        "item_name": name,
        "mfg_date": None if info.mfg_date is None else info.mfg_date.isoformat(),
        "best_before": None if info.best_before is None else info.best_before.isoformat(),
    }


def search(session: Session, q: str | None) -> list[dict[str, Any]]:
    """Lots whose number contains `q` (newest first); with no `q`, the 50 newest."""
    text = (q or "").strip()
    found = ledger.lots_where(session, text_like=text or None, limit=50)
    codes = catalog.names_for(session, {f.item_id for f in found})
    return [_lot_row(f, codes) for f in found]


# ---------- T2: the "may contain" window of one item at its store ----------


@dataclass(frozen=True)
class Outflow:
    journal_id: str
    kind: str
    posting_date: date
    qty_base: Decimal  # taken out (positive) or, for a return, brought back (negative)
    run_id: uuid.UUID | None
    document: str  # "MI/26-27/000001" or "completion of B-001"
    source: SourceRef


@dataclass(frozen=True)
class Window:
    item_id: uuid.UUID
    store: str
    candidates: dict[str, frozenset[str]]  # outflow journal -> source keys
    outflows: list[Outflow]  # every movement attributable to a batch (issues, returns, completion)
    labels: dict[str, dict[str, Any]]  # source key -> what it is
    still_present: frozenset[str]


def _window(session: Session, item_id: uuid.UUID, store: str) -> Window:
    timeline = ledger.store_timeline(session, item_id, store)
    received = procurement.received_lots(session, item_id=item_id)
    lot_ids = {
        lot.lot_no: lot.id
        for lot in ledger.lots_where(session, item_id=item_id, lot_nos=sorted({r.lot_no for r in received if r.lot_no}))
    }
    by_journal: dict[uuid.UUID, list[procurement.ReceivedLot]] = {}
    for r in received:
        if r.journal_id is not None:
            by_journal.setdefault(r.journal_id, []).append(r)
    issues = production.issue_refs(session, [m.source_id for m in timeline if m.source_type == "material_issue"])
    run_nos = {
        rid: info["run_no"]
        for rid, info in production.trace_runs(
            session,
            sorted(
                {i.run_id for i in issues.values()}
                | {m.source_id for m in timeline if m.source_type == "production_run"},
                key=str,
            ),
        ).items()
    }

    labels: dict[str, dict[str, Any]] = {}
    events: list[StoreEvent] = []
    outflows: list[Outflow] = []
    to_run: dict[uuid.UUID, list[str]] = {}  # run -> its earlier outflow keys (what a return brings back)
    for m in timeline:
        key = str(m.journal_id)
        run_id: uuid.UUID | None = None
        document = m.kind.lower()
        source = SourceRef("stock_journal", key)
        if m.source_type == "material_issue" and m.source_id in issues:
            ref = issues[m.source_id]
            run_id, document, source = ref.run_id, ref.issue_no, SourceRef("material_issue", str(ref.issue_id))
        elif m.source_type == "production_run":
            run_id = m.source_id
            document = f"completion of {run_nos.get(m.source_id, 'batch')}"
            source = SourceRef("production_run", str(m.source_id))
        if m.qty_base < 0:
            events.append(StoreEvent(key, m.posted_at, m.qty_base))
            if run_id is not None:
                to_run.setdefault(run_id, []).append(key)
                outflows.append(Outflow(key, m.kind, m.posting_date, -m.qty_base, run_id, document, source))
            continue
        brings: set[str] = set()
        carries: tuple[str, ...] = ()
        if m.kind == "OPENING":
            brings.add(f"opening:{key}")
            labels[f"opening:{key}"] = {
                "kind": "opening",
                "label": "opening stock, no supplier lot recorded",
                "date": m.posting_date.isoformat(),
                "source": {"type": "stock_journal", "id": key},
            }
        elif m.kind == "RECEIPT" and m.journal_id in by_journal:
            for r in by_journal[m.journal_id]:
                if r.accepted_base <= 0:
                    continue
                if r.lot_no and r.lot_no in lot_ids:
                    sk = f"lot:{lot_ids[r.lot_no]}"
                    labels[sk] = {
                        "kind": "supplier_lot",
                        "label": f"supplier lot {r.lot_no} ({r.supplier_name})",
                        "lot_id": str(lot_ids[r.lot_no]),
                        "lot_no": r.lot_no,
                        "supplier": r.supplier_name,
                        "receipt_no": r.receipt_no,
                        "date": r.received_on.isoformat(),
                        "source": {"type": "purchase_receipt", "id": str(r.receipt_id)},
                    }
                else:
                    sk = f"receipt:{r.receipt_id}"
                    labels[sk] = {
                        "kind": "no_lot",
                        "label": f"receipt {r.receipt_no} ({r.supplier_name}), no supplier lot recorded",
                        "receipt_no": r.receipt_no,
                        "supplier": r.supplier_name,
                        "date": r.received_on.isoformat(),
                        "source": {"type": "purchase_receipt", "id": str(r.receipt_id)},
                    }
                brings.add(sk)
        elif m.kind == "RETURN" and run_id is not None:
            carries = tuple(to_run.get(run_id, []))
            outflows.append(Outflow(key, m.kind, m.posting_date, -m.qty_base, run_id, document, source))
        elif m.kind == "REVERSAL" and m.reverses_journal_id is not None:
            carries = (str(m.reverses_journal_id),)
        else:
            sk = f"other:{key}"
            labels[sk] = {
                "kind": "other",
                "label": f"{m.kind.lower().replace('_', ' ')} on {m.posting_date.isoformat()},"
                " no supplier lot recorded",
                "date": m.posting_date.isoformat(),
                "source": {"type": "stock_journal", "id": key},
            }
            brings.add(sk)
        events.append(StoreEvent(key, m.posted_at, m.qty_base, frozenset(brings), carries))
    result = domain.may_contain(events)
    return Window(item_id, store, result.candidates, outflows, labels, result.still_present)


def _store_of(kind: str) -> str | None:
    return HOME_STORE.get(kind)


# ---------- T1: backward and forward ----------


def _qty(qty_base: Decimal, item_id: uuid.UUID, units: dict[uuid.UUID, Any]) -> tuple[Decimal, str]:
    u = units[item_id]
    return normalise(from_base(qty_base, u.stock_uom, u)), u.stock_uom


def _materials(session: Session, run: dict[str, Any]) -> list[dict[str, Any]]:
    """Every material the batch took from the stores (issues, returns, packing at completion) and what each may
    contain."""
    run_id = uuid.UUID(run["run_id"])
    items: set[uuid.UUID] = set()
    for j in run["material_journal_ids"]:
        for ln in ledger.journal_lines(session, uuid.UUID(j)):
            if ln.location in HOME_STORE.values() and ln.qty_base != 0:
                items.add(ln.item_id)
    kinds = catalog.kinds_for(session, items)
    codes = catalog.codes_for(session, items)
    units = catalog.units_for(session, items)
    out = []
    for item in sorted(items, key=lambda i: codes[i]):
        store = _store_of(kinds[item])
        if store is None:
            continue
        w = _window(session, item, store)
        for o in w.outflows:
            if o.run_id != run_id:
                continue
            keys = w.candidates.get(o.journal_id, frozenset())
            out.append(
                {
                    "item_code": codes[item],
                    "store": store,
                    **_moved(o, item, units),
                    "may_contain": sorted(
                        (w.labels[k] for k in keys if k in w.labels), key=lambda x: (x["date"], x["label"])
                    ),
                }
            )
    return out


def _forward(session: Session, lots: list[ledger.LotInfo], made: dict[uuid.UUID, int | None]) -> list[dict[str, Any]]:
    """Each lot's packets made, every dispatch (number, date, invoice, customer, packets) and what is on hand."""
    shipped = dispatch.lot_dispatches(session, [lot.id for lot in lots])
    codes = catalog.names_for(session, {lot.item_id for lot in lots})
    out = []
    for lot in lots:
        rows = [d for d in shipped if d.lot_id == lot.id]
        on_hand = sum(
            (q for loc, q, _ in ledger.lot_positions(session, lot.item_id, lot.id) if loc == FG_STORE), Decimal(0)
        )
        good = made.get(lot.id)
        out.append(
            {
                **_lot_row(lot, codes),
                "made": None
                if good is None
                else _one(
                    Decimal(good),
                    "packets",
                    "good packets recorded when the batch was completed",
                    "good packets",
                    SourceRef("production_run", str(lot.source_id)),
                ),
                "dispatched": domain.packets_explained(
                    (
                        (f"{d.dispatch_no} to {d.customer_code}", d.qty, SourceRef("dispatch", str(d.dispatch_id)))
                        for d in rows
                    ),
                    "sum of this lot's packets on every dispatch",
                ).to_json(),
                "on_hand": _one(
                    normalise(on_hand),
                    "packets",
                    "this lot's balance in the finished-goods store (stock ledger)",
                    "FG_STORE balance",
                    SourceRef("inventory_balances", str(lot.id)),
                ),
                "dispatches": [
                    {
                        "dispatch_id": str(d.dispatch_id),
                        "dispatch_no": d.dispatch_no,
                        "dispatch_date": d.dispatch_date.isoformat(),
                        "invoice_id": str(d.invoice_id),
                        "invoice_no": d.invoice_no,
                        "customer_id": str(d.customer_id),
                        "customer_code": d.customer_code,
                        "customer_name": d.customer_name,
                        "packets": str(d.qty),
                    }
                    for d in rows
                ],
            }
        )
    return out


def _runs_lots(
    session: Session, runs: dict[uuid.UUID, dict[str, Any]]
) -> tuple[list[ledger.LotInfo], dict[uuid.UUID, int | None]]:
    lots: list[ledger.LotInfo] = []
    made: dict[uuid.UUID, int | None] = {}
    for run in sorted(runs.values(), key=lambda r: r["run_no"]):
        for lot in run["lots"]:
            lot_id = uuid.UUID(lot["lot_id"])
            lots.append(ledger.lot_info(session, lot_id))
            made[lot_id] = lot["good_units"]
    return lots, made


def _run_view(run: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in run.items() if k != "material_journal_ids"}


def _one(value: Decimal, unit: str, formula: str, label: str, source: SourceRef) -> dict[str, Any]:
    """An Explained value read from one posted row."""
    return Explained(value, unit, formula, (ExplainedInput(label, value, unit, source),)).to_json()


def _moved(o: Outflow, item_id: uuid.UUID, units: dict[uuid.UUID, Any]) -> dict[str, Any]:
    qty, unit = _qty(o.qty_base, item_id, units)
    return {
        "document": o.document,
        "direction": "RETURN" if o.qty_base < 0 else "ISSUE",
        "posting_date": o.posting_date.isoformat(),
        "qty": _one(
            qty,
            unit,
            "quantity this document moved out of the store for the batch (a return is negative)",
            o.document,
            o.source,
        ),
        "source": {"type": o.source.type, "id": o.source.id},
    }


def _supplier_lot_batches(
    session: Session, info: ledger.LotInfo
) -> tuple[dict[str, Any], dict[uuid.UUID, dict[str, Any]]]:
    """A supplier lot's receipts and every batch whose issues may contain it (T2)."""
    kinds = catalog.kinds_for(session, [info.item_id])
    store = _store_of(kinds[info.item_id])
    receipts = [r for r in procurement.received_lots(session, item_id=info.item_id) if r.lot_no == info.lot_no]
    units = catalog.units_for(session, [info.item_id])
    key = f"lot:{info.id}"
    hits: list[Outflow] = []
    still = False
    if store is not None:
        w = _window(session, info.item_id, store)
        hits = [o for o in w.outflows if key in w.candidates.get(o.journal_id, frozenset())]
        still = key in w.still_present
    runs = production.trace_runs(session, sorted({o.run_id for o in hits if o.run_id is not None}, key=str))
    batches = []
    for rid, run in sorted(runs.items(), key=lambda kv: kv[1]["run_no"]):
        batches.append({**_run_view(run), "issues": [_moved(o, info.item_id, units) for o in hits if o.run_id == rid]})
    accepted = [r for r in receipts if r.accepted_base > 0]
    facts = {
        "store": store,
        "receipts": [
            {
                "receipt_id": str(r.receipt_id),
                "receipt_no": r.receipt_no,
                "status": r.status,
                "received_on": r.received_on.isoformat(),
                "supplier": r.supplier_name,
                "accepted": _one(
                    *_qty(r.accepted_base, info.item_id, units),
                    "accepted quantity on the receipt line",
                    r.receipt_no,
                    SourceRef("purchase_receipt", str(r.receipt_id)),
                ),
            }
            for r in receipts
        ],
        "never_accepted": not accepted,
        "may_still_be_in_store": still,
        "batches": batches,
        "note": MAY_CONTAIN_NOTE,
    }
    return facts, runs


def trace(session: Session, lot_id: uuid.UUID) -> dict[str, Any]:
    """T1: a lot backward (batch, frozen versions, operator, materials and the supplier lots they may contain) and
    forward (dispatches, invoices, customers, on hand). A supplier lot traces forward through its batches."""
    info = ledger.lot_info(session, lot_id)
    kind = _lot_kind(info)
    codes = catalog.names_for(session, [info.item_id])
    out: dict[str, Any] = {"lot": _lot_row(info, codes), "note": MAY_CONTAIN_NOTE}
    if kind == "supplier_lot":
        facts, runs = _supplier_lot_batches(session, info)
        lots, made = _runs_lots(session, runs)
        out["backward"] = facts
        out["forward"] = _forward(session, lots, made)
        return out
    if kind == "opening_lot":
        out["backward"] = {"batch": None, "materials": [], "text": "opening stock: no batch record behind this lot"}
        out["forward"] = _forward(session, [info], {})
        return out
    assert info.source_id is not None  # a batch lot always names its run
    runs = production.trace_runs(session, [info.source_id])
    run = runs[info.source_id]
    out["backward"] = {"batch": _run_view(run), "materials": _materials(session, run)}
    made = {uuid.UUID(lot["lot_id"]): lot["good_units"] for lot in run["lots"]}
    out["forward"] = _forward(session, [info], made)
    return out


# ---------- T3: the recall simulator ----------


def _sum(rows: list[dict[str, Any]], field: str, formula: str) -> Explained:
    inputs = tuple(
        ExplainedInput(f"lot {r['lot_no']}", Decimal(r[field]["value"]), "packets", SourceRef("lot", r["lot_id"]))
        for r in rows
        if r[field] is not None
    )
    return Explained(sum((i.value for i in inputs), Decimal(0)), "packets", formula, inputs)


def recall(session: Session, lot_id: uuid.UUID, reason: str | None = None) -> dict[str, Any]:
    """T3: from a supplier lot or an FG lot, the batches and FG lots affected, every customer holding packets with
    the invoices, and a printable draft notice. Read-only: nothing is stored or sent."""
    info = ledger.lot_info(session, lot_id)
    kind = _lot_kind(info)
    names = catalog.names_for(session, [info.item_id])
    if kind == "supplier_lot":
        facts, runs = _supplier_lot_batches(session, info)
        lots, made = _runs_lots(session, runs)
        batches = facts["batches"]
        subject = f"supplier lot {info.lot_no} of {names[info.item_id][0]}"
    elif kind == "batch_lot":
        assert info.source_id is not None
        runs = production.trace_runs(session, [info.source_id])
        lots = [info]
        made = {uuid.UUID(lot["lot_id"]): lot["good_units"] for lot in runs[info.source_id]["lots"]}
        batches = [_run_view(runs[info.source_id])]
        subject = f"batch lot {info.lot_no} of {names[info.item_id][0]}"
    else:
        lots, made, batches = [info], {}, []
        subject = f"opening stock lot {info.lot_no} of {names[info.item_id][0]}"
    forward = _forward(session, lots, made)
    shipments = [
        Shipment(
            d["customer_id"],
            d["customer_code"],
            d["customer_name"],
            d["dispatch_id"],
            d["dispatch_no"],
            date.fromisoformat(d["dispatch_date"]),
            d["invoice_no"],
            f["lot_no"],
            int(d["packets"]),
        )
        for f in forward
        for d in f["dispatches"]
    ]
    customers = domain.exposure(shipments)
    on_hand = _sum(forward, "on_hand", "sum of the affected lots' balances in the finished-goods store")
    org = scoped_org(session)
    factory = "DEMO factory" if org is None else identity.organization(session, org)["name"]
    profile = tax.profile(session, business_date())
    why = (reason or "").strip() or "DEMO simulation: suspected quality problem"
    notice = domain.draft_notice(
        NoticeFacts(
            factory=factory,
            fssai_no=profile.get("fssai_no"),
            subject=subject,
            lot_nos=[f["lot_no"] for f in forward],
            best_before=[None if f["best_before"] is None else date.fromisoformat(f["best_before"]) for f in forward],
            reason=why,
            customers=customers,
            on_hand=on_hand.value,
        )
    )
    return {
        "simulation": True,
        "note": SIMULATION_NOTE,
        "may_contain_note": MAY_CONTAIN_NOTE if kind == "supplier_lot" else None,
        "subject": subject,
        "lot": _lot_row(info, names),
        "batches": batches,
        "lots": forward,
        "customers": [
            {
                "customer_id": c.customer_id,
                "customer_code": c.customer_code,
                "customer_name": c.customer_name,
                "packets": c.packets.to_json(),
                "invoice_nos": list(c.invoice_nos),
                "lot_nos": list(c.lot_nos),
                "last_dispatch": c.last_dispatch.isoformat(),
            }
            for c in customers
        ],
        "totals": {
            "made": _sum(forward, "made", "sum of good packets of the affected lots").to_json(),
            "dispatched": _sum(forward, "dispatched", "sum of the affected lots' dispatched packets").to_json(),
            "on_hand": on_hand.to_json(),
            "customers": str(len(customers)),
        },
        "notice": notice,
    }
