"""The preprocessing pipeline (MP16, Part D.2): raw -> contract-validated -> canonical units -> de-duplicated ->
chronology-checked -> feature tables. Every stage logs rows in / out and why rows left. Pure Python; reads records only.
"""

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date
from statistics import median

from analytics.simulator.generate import Invoice, OrderLine, Run

UNIT_ERROR_RATIO = 50  # a line this many times its customer x SKU median is a unit slip (packets keyed as grams)


@dataclass
class StageLog:
    stage: str
    rows_in: int
    rows_out: int
    reasons: dict[str, int] = field(default_factory=dict)


@dataclass
class Clean:
    orders: list[OrderLine]
    runs: list[Run]
    invoices: list[Invoice]
    log: list[StageLog]
    duplicates_removed: set[str]
    unit_fixed: set[str]


def contract(orders: list[OrderLine]) -> tuple[list[OrderLine], StageLog]:
    ok, reasons = [], defaultdict(int)
    for o in orders:
        if o.packets <= 0:
            reasons["packets not positive"] += 1
        elif not o.customer or not o.sku:
            reasons["missing customer or SKU"] += 1
        else:
            try:
                date.fromisoformat(o.order_date)
            except ValueError:
                reasons["bad date"] += 1
                continue
            ok.append(o)
    return ok, StageLog("contract", len(orders), len(ok), dict(reasons))


def canonical_units(orders: list[OrderLine]) -> tuple[list[OrderLine], set[str], StageLog]:
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for o in orders:
        by_key[(o.customer, o.sku)].append(o.packets)
    medians = {k: median(v) for k, v in by_key.items()}
    out, fixed = [], set()
    for o in orders:
        if o.packets > UNIT_ERROR_RATIO * medians[(o.customer, o.sku)] and o.packets % 1000 == 0:
            out.append(replace(o, packets=o.packets // 1000))
            fixed.add(o.order_id)
        else:
            out.append(o)
    return out, fixed, StageLog("canonical units", len(orders), len(out), {"unit slip corrected (/1000)": len(fixed)})


def deduplicate(orders: list[OrderLine]) -> tuple[list[OrderLine], set[str], StageLog]:
    seen: set[tuple[str, str]] = set()
    out, removed = [], set()
    for o in orders:
        key = (o.idempotency_key, o.sku)
        if key in seen:
            removed.add(o.order_id)
            continue
        seen.add(key)
        out.append(o)
    return out, removed, StageLog("de-duplicated", len(orders), len(out), {"same idempotency key": len(removed)})


def chronology(invoices: list[Invoice]) -> tuple[list[Invoice], StageLog]:
    ok = [i for i in invoices if i.paid_date >= i.invoice_date]
    return ok, StageLog("chronology", len(invoices), len(ok), {"paid before invoiced": len(invoices) - len(ok)})


def run(orders: list[OrderLine], runs: list[Run], invoices: list[Invoice]) -> Clean:
    a, log1 = contract(orders)
    b, removed, log2 = deduplicate(a)
    c, fixed, log3 = canonical_units(b)
    inv, log4 = chronology(invoices)
    return Clean(c, runs, inv, [log1, log2, log3, log4], removed, fixed)


def weekly(orders: list[OrderLine]) -> dict[tuple[str, str], dict[int, int]]:
    """Feature table: (SKU, state) -> week -> packets."""
    out: dict[tuple[str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for o in orders:
        out[(o.sku, o.state)][o.week] += o.packets
    return out
