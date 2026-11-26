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
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from itertools import pairwise

from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money
from app.modules.uom.domain import normalise


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


# ---------- T6: oil (RUCO) and fill weights, from what batch completion recorded ----------

ML_PER_L = Decimal(1000)
G_PER_KG = Decimal(1000)


@dataclass(frozen=True)
class OilUse:
    run_id: str
    run_no: str
    fresh_ml: Decimal
    topup_ml: Decimal


@dataclass(frozen=True)
class OilDay:
    day: date
    litres: Explained
    above_threshold: bool


def oil_day(day: date, uses: Sequence[OilUse], threshold_l: Decimal) -> OilDay:
    """Fresh oil plus top-ups on one day, in litres, against the record-keeping threshold (RUCO: above it, daily
    records are required)."""
    inputs: list[ExplainedInput] = []
    for u in uses:
        src = SourceRef("production_run", u.run_id)
        inputs.append(ExplainedInput(f"{u.run_no} fresh oil", u.fresh_ml / ML_PER_L, "L", src))
        if u.topup_ml:
            inputs.append(ExplainedInput(f"{u.run_no} top-ups", u.topup_ml / ML_PER_L, "L", src))
    litres = sum((i.value for i in inputs), Decimal(0))
    return OilDay(
        day,
        Explained(
            normalise(litres),
            "L",
            "sum of fresh oil and top-ups recorded at batch completion that day",
            tuple(inputs),
            method=f"daily records required above {threshold_l} L/day (DEMO setting)",
        ),
        litres > threshold_l,
    )


def tpc_discard(tpc_pct: Decimal | None, limit_pct: Decimal) -> bool:
    """Total polar compounds above the limit: the oil must be discarded."""
    return tpc_pct is not None and tpc_pct > limit_pct


@dataclass(frozen=True)
class FillCheck:
    mean_net: Explained
    over_per_packet: Explained
    cost_per_kg: Explained
    giveaway: Explained
    short_limit_g: Decimal | None  # a packet below this is short (declared - tolerance)
    short: tuple[Decimal, ...]


def fill_check(
    *,
    run_id: str,
    run_no: str,
    declared_g: Decimal,
    nets: Sequence[Decimal],
    good_units: int,
    ingredient_value: Decimal,
    expected_bulk_g: Decimal,
    tolerance_g: Decimal | None,
) -> FillCheck:
    """Giveaway and short fills from the sampled net weights. Giveaway rupees = grams over the declared net per
    packet x good packets x the batch's ingredient cost per gram (ingredients issued / the recipe's bulk)."""
    if not nets:
        raise ValueError("fill_check needs at least one sample")
    src = SourceRef("production_run", run_id)
    mean = (sum(nets, Decimal(0)) / len(nets)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    mean_x = Explained(
        normalise(mean),
        "g",
        "mean of the sampled net weights",
        tuple(ExplainedInput(f"sample {n}", w, "g", src) for n, w in enumerate(nets, start=1)),
    )
    over = mean - declared_g
    over_x = Explained(
        normalise(over),
        "g",
        "mean sampled net - declared net (negative is under-filled)",
        (
            ExplainedInput("mean sampled net", normalise(mean), "g", src),
            ExplainedInput("declared net", declared_g, "g", src),
        ),
    )
    per_kg = (ingredient_value / expected_bulk_g * G_PER_KG).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    cost_x = Explained(
        normalise(per_kg),
        "INR/kg",
        "ingredients issued to the batch / the recipe's bulk yield",
        (
            ExplainedInput("ingredients issued", ingredient_value, "INR", src),
            ExplainedInput("recipe bulk yield", expected_bulk_g / G_PER_KG, "kg", src),
        ),
    )
    extra_g = max(over, Decimal(0)) * good_units
    rupees = round_money(extra_g / G_PER_KG * per_kg)
    give_x = Explained(
        rupees,
        "INR",
        "max(grams over per packet, 0) x good packets x ingredient cost per kg / 1000",
        (
            ExplainedInput("grams over per packet", normalise(max(over, Decimal(0))), "g", src),
            ExplainedInput("good packets", Decimal(good_units), "packets", src),
            ExplainedInput("ingredient cost", normalise(per_kg), "INR/kg", src),
        ),
        method="estimate from samples",
    )
    limit = None if tolerance_g is None else declared_g - tolerance_g
    short = () if limit is None else tuple(w for w in nets if w < limit)
    return FillCheck(mean_x, over_x, cost_x, give_x, limit, short)


# ---------- T5: the freshness radar ----------

RATE_PLACES = Decimal("0.000001")


@dataclass(frozen=True)
class OrderDay:
    on: date
    packets: int


@dataclass(frozen=True)
class Rates:
    """Packets a day the customer sells, read from their order rhythm."""

    central: Decimal  # packets ordered before the latest order / days from the first to the latest order
    slow: Decimal  # mean order / the longest gap between orders
    fast: Decimal  # mean order / the shortest gap
    orders: int
    span_days: int


def selling_rates(orders: Sequence[OrderDay]) -> Rates | None:
    """None with fewer than two order days: not enough history to say how fast the shelf empties."""
    by_day: dict[date, int] = {}
    for o in orders:
        by_day[o.on] = by_day.get(o.on, 0) + o.packets
    days = sorted(by_day)
    if len(days) < 2:
        return None
    before_latest = Decimal(sum(by_day[d] for d in days[:-1]))
    span = (days[-1] - days[0]).days
    gaps = [(b - a).days for a, b in pairwise(days)]
    mean = before_latest / (len(days) - 1)
    return Rates(
        central=(before_latest / span).quantize(RATE_PLACES, rounding=ROUND_HALF_UP),
        slow=(mean / max(gaps)).quantize(RATE_PLACES, rounding=ROUND_HALF_UP),
        fast=(mean / min(gaps)).quantize(RATE_PLACES, rounding=ROUND_HALF_UP),
        orders=len(days),
        span_days=span,
    )


@dataclass(frozen=True)
class LotDelivery:
    lot_id: str
    lot_no: str
    best_before: date | None
    delivered_on: date
    packets: int
    dispatch_id: str
    dispatch_no: str


def on_shelf(deliveries: Sequence[LotDelivery], rate: Decimal | None, today: date) -> dict[str, Decimal]:
    """Packets of each lot estimated still on the shelf: everything delivered minus what the rate sold since the
    first delivery, the oldest best-before sold first (no date first: opening stock). With no rate, everything."""
    per_lot: dict[str, tuple[date | None, int]] = {}
    for d in deliveries:
        bb, n = per_lot.get(d.lot_id, (d.best_before, 0))
        per_lot[d.lot_id] = (bb, n + d.packets)
    if rate is None or not deliveries:
        return {lot: Decimal(n) for lot, (_, n) in per_lot.items()}
    first = min(d.delivered_on for d in deliveries)
    total = Decimal(sum(n for _, n in per_lot.values()))
    sold = min(total, rate * (today - first).days)
    out: dict[str, Decimal] = {}
    for lot, (_bb, n) in sorted(per_lot.items(), key=lambda kv: (kv[1][0] is not None, kv[1][0] or date.min, kv[0])):
        taken = min(Decimal(n), sold)
        sold -= taken
        out[lot] = Decimal(n) - taken
    return out


@dataclass(frozen=True)
class ShelfEstimate:
    lot_id: str
    lot_no: str
    best_before: date | None
    days_to_best_before: int | None
    delivered: Explained
    low: int
    central: int | None
    high: Explained
    flagged: bool


def shelf_estimates(
    deliveries: Sequence[LotDelivery],
    orders: Sequence[OrderDay],
    today: date,
    alert_days: int,
) -> tuple[Rates | None, list[ShelfEstimate]]:
    """Per lot of one customer and one item: the low, central and high packets still on the shelf, flagged when
    the best-before is within `alert_days` and the high estimate is above zero."""
    rates = selling_rates(orders)
    high = on_shelf(deliveries, None if rates is None else rates.slow, today)
    low = on_shelf(deliveries, None if rates is None else rates.fast, today) if rates else {k: Decimal(0) for k in high}
    central = on_shelf(deliveries, rates.central, today) if rates else None
    first = min((d.delivered_on for d in deliveries), default=today)
    out = []
    for lot_id in high:
        mine = [d for d in deliveries if d.lot_id == lot_id]
        bb = mine[0].best_before
        days = None if bb is None else (bb - today).days
        hi = int(high[lot_id].to_integral_value(rounding=ROUND_CEILING))
        delivered = Explained(
            Decimal(sum(d.packets for d in mine)),
            "packets",
            "sum of this lot's packets on the customer's dispatches",
            tuple(
                ExplainedInput(
                    f"{d.dispatch_no} ({d.delivered_on.isoformat()})",
                    Decimal(d.packets),
                    "packets",
                    SourceRef("dispatch", d.dispatch_id),
                )
                for d in mine
            ),
        )
        inputs = [
            ExplainedInput("delivered in the window, all lots", Decimal(sum(d.packets for d in deliveries)), "packets")
        ]
        if rates is None:
            formula = "not enough history (fewer than two orders): the whole delivery may still be on the shelf"
        else:
            formula = (
                "delivered - packets sold at the slowest order rhythm since the first delivery, oldest best-before"
                " sold first, rounded up"
            )
            inputs += [
                ExplainedInput("slowest selling rate", rates.slow, "packets/day"),
                ExplainedInput("days since the first delivery", Decimal((today - first).days), "days"),
            ]
        out.append(
            ShelfEstimate(
                lot_id=lot_id,
                lot_no=mine[0].lot_no,
                best_before=bb,
                days_to_best_before=days,
                delivered=delivered,
                low=int(low[lot_id].to_integral_value(rounding=ROUND_FLOOR)),
                central=None if central is None else int(central[lot_id].to_integral_value(rounding=ROUND_HALF_UP)),
                high=Explained(Decimal(hi), "packets", formula, tuple(inputs), method="estimate from order rhythm"),
                flagged=days is not None and days <= alert_days and hi > 0,
            )
        )
    return rates, out
