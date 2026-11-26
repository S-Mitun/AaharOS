"""Traceability rules (MP13, ADR-0020). Pure functions, no database.

T2, the "may contain" window. Raw and packaging stock is lot-less (ADR-0012 D4): the ledger knows how much flour is
in the store, not which supplier's sack each gram came from. So a supplier lot is treated as possibly present in
every outflow of that item from its store after the lot arrived, until the store's balance of that item first falls
to zero (then whatever was in the store, that lot included, is certainly used up). A return to the store brings back
whatever the returned issue may have contained. The window is conservative: a recall may name an extra batch, but it
never misses one, whatever order the floor actually used the sacks in.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.core.explained import Explained, ExplainedInput, SourceRef


@dataclass(frozen=True)
class StoreEvent:
    """One journal's net change to one item at its store. `at` orders events; equal `at` values are one group whose
    inner order is unknown, so its inflows count before its outflows (conservative)."""

    key: str
    at: datetime | int
    qty: Decimal
    brings: frozenset[str] = frozenset()  # the sources an inflow brings in (supplier lots, opening stock, ...)
    carries_from: tuple[str, ...] = ()  # outflow keys whose possible contents an inflow brings back (returns)


@dataclass(frozen=True)
class WindowResult:
    candidates: dict[str, frozenset[str]]  # outflow key -> the sources it may contain
    still_present: frozenset[str]  # the sources that may still be in the store after the last event


def may_contain(events: Sequence[StoreEvent]) -> WindowResult:
    """For every outflow key, the sources it may contain. `events` must be in the order the store saw them."""
    candidates: dict[str, frozenset[str]] = {}
    present: set[str] = set()
    balance = Decimal(0)
    i = 0
    while i < len(events):
        j = i
        while j < len(events) and events[j].at == events[i].at:
            j += 1
        group = events[i:j]
        for e in group:
            if e.qty > 0:
                present |= e.brings
                for k in e.carries_from:
                    present |= candidates.get(k, frozenset())
        snapshot = frozenset(present)
        for e in group:
            if e.qty < 0:
                candidates[e.key] = snapshot
        balance += sum((e.qty for e in group), Decimal(0))
        if balance <= 0:  # the store held none of this item: everything that was in it has left
            present.clear()
        i = j
    return WindowResult(candidates, frozenset(present))


@dataclass(frozen=True)
class Shipment:
    """One dispatch line of an affected lot (forward trace)."""

    customer_id: str
    customer_code: str
    customer_name: str
    dispatch_id: str
    dispatch_no: str
    dispatch_date: date
    invoice_no: str
    lot_no: str
    packets: int


@dataclass(frozen=True)
class Exposure:
    customer_id: str
    customer_code: str
    customer_name: str
    packets: Explained
    invoice_nos: tuple[str, ...]
    lot_nos: tuple[str, ...]
    last_dispatch: date


def packets_explained(label_and_source: Iterable[tuple[str, int, SourceRef]], formula: str) -> Explained:
    inputs = tuple(ExplainedInput(label, Decimal(n), "packets", src) for label, n, src in label_and_source)
    return Explained(sum((i.value for i in inputs), Decimal(0)), "packets", formula, inputs)


def exposure(shipments: Sequence[Shipment]) -> list[Exposure]:
    """Packets of the affected lots per customer, with the invoices they came on, most packets first."""
    by_customer: dict[str, list[Shipment]] = {}
    for s in shipments:
        by_customer.setdefault(s.customer_id, []).append(s)
    out = [
        Exposure(
            customer_id=cid,
            customer_code=rows[0].customer_code,
            customer_name=rows[0].customer_name,
            packets=packets_explained(
                (
                    (f"{r.dispatch_no} ({r.dispatch_date.isoformat()}), lot {r.lot_no}", r.packets, _dispatch(r))
                    for r in rows
                ),
                "sum of packets of the affected lots on this customer's dispatches",
            ),
            invoice_nos=tuple(sorted({r.invoice_no for r in rows})),
            lot_nos=tuple(sorted({r.lot_no for r in rows})),
            last_dispatch=max(r.dispatch_date for r in rows),
        )
        for cid, rows in by_customer.items()
    ]
    return sorted(out, key=lambda e: (-e.packets.value, e.customer_code))


def _dispatch(s: Shipment) -> SourceRef:
    return SourceRef("dispatch", s.dispatch_id)


@dataclass(frozen=True)
class NoticeFacts:
    factory: str
    fssai_no: str | None
    subject: str  # "supplier lot FL-2611 of flour" / "batch lot B-001-1 of murukku_200g"
    lot_nos: Sequence[str]
    best_before: Sequence[date | None]
    reason: str
    customers: Sequence[Exposure] = field(default_factory=tuple)
    on_hand: Decimal = Decimal(0)


DEMO_BANNER = "DEMO SIMULATION - NOTHING HAS BEEN SENT. Fictional data; check with the food-safety officer."


def draft_notice(f: NoticeFacts) -> str:
    """A printable draft recall notice from the recall facts only (no figure is typed by hand)."""
    lots = ", ".join(f.lot_nos) if f.lot_nos else "none"
    dates = sorted({d.isoformat() for d in f.best_before if d is not None})
    lines = [
        DEMO_BANNER,
        "",
        f"DRAFT PRODUCT RECALL NOTICE - {f.factory}",
        f"FSSAI licence: {f.fssai_no or 'not set'}",
        "",
        f"Reason: {f.reason}",
        f"Traced from: {f.subject}",
        f"Affected batch lots: {lots}",
        f"Best before: {', '.join(dates) if dates else 'not recorded'}",
        "",
        "Please stop selling these packets, keep them apart and return them to your salesman:",
    ]
    if not f.customers:
        lines.append("  (no packets of these lots have been dispatched)")
    for c in f.customers:
        lines.append(
            f"  {c.customer_name} ({c.customer_code}): {c.packets.value} packets,"
            f" invoices {', '.join(c.invoice_nos)}, lots {', '.join(c.lot_nos)}"
        )
    lines += ["", f"Still in the factory store (held, not to be dispatched): {f.on_hand} packets", "", DEMO_BANNER]
    return "\n".join(lines)
