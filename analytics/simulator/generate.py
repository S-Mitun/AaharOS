"""The Factory Simulator (MP16, MASTER_PACK Part D.1 layer 2). Synthetic, seeded, labelled SIM.

24 months (Nov 2023 - Oct 2025) of one DEMO factory: ~120 customers on 12 routes in TN / KA / KL, 15 SKUs, weekly
orders, ~2 production runs a day with operator, shift and flour-supplier lot, invoices and their payments. It writes
nothing to the database: the analytics read these records only.

Planted truths (hidden parameters the analytics must rediscover; `PLANTED` below):
- festival uplift: Deepavali x3.2 in TN and KA, Pongal x1.8 in TN, Onam x2.5 in KL, in the festival week and the week
  before (dates from `festivals.FESTIVALS`, with sources);
- supplier S-05's flour lots yield 5% less (moisture);
- night-shift operator O-3 (from month 7) overuses oil by about 4%;
- customers on route R-7 pay at about 60 days (others about 22);
- the 500 g SKU, launched in TN in month 13, takes about 15% of the 200 g SKU's demand there;
- injected data faults: 2% of order lines synced twice (same idempotency key), 0.5% of quantities entered in the wrong
  unit (packets x 1000).
"""

import csv
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from analytics.simulator.festivals import festival_weeks

SEED = 20261126
START = date(2023, 11, 6)  # a Monday
WEEKS = 104  # 24 months
STATES = ("TN", "KA", "KL")
PLANTED: dict[str, Any] = {
    "festival_uplift": {"Deepavali": 3.2, "Pongal": 1.8, "Onam": 2.5},
    "supplier_lot_yield_effect": {"S-05": -0.05},
    "operator_oil_effect": {"O-3": 0.04, "from_month": 7},
    "route_payment_days": {"R-7": 60, "other": 22},
    "cannibalisation_500g_on_200g": {"effect": -0.15, "state": "TN", "from_month": 13},
    "faults": {"duplicate_sync_rate": 0.02, "unit_error_rate": 0.005, "unit_error_factor": 1000},
}


@dataclass
class OrderLine:
    order_id: str
    idempotency_key: str
    week: int
    order_date: str
    customer: str
    route: str
    state: str
    sku: str
    packets: int


@dataclass
class Run:
    run_id: str
    run_date: str
    month: int
    operator: str
    shift: str
    flour_supplier: str
    flour_lot: str
    expected_packets: int
    good_packets: int
    yield_pct: float
    oil_l: float


@dataclass
class Invoice:
    invoice_id: str
    customer: str
    route: str
    invoice_date: str
    paid_date: str
    days_to_pay: int
    amount: float


@dataclass
class World:
    orders: list[OrderLine] = field(default_factory=list)
    runs: list[Run] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    truth: dict[str, Any] = field(default_factory=dict)
    fault_ids: dict[str, set[str]] = field(default_factory=lambda: {"duplicate": set(), "unit_error": set()})


def _month(week: int) -> int:
    return week * 7 // 30 + 1  # 1..24


def simulate(seed: int = SEED) -> World:
    rng = random.Random(seed)  # noqa: S311 - a seeded simulation, not security
    w = World(truth=PLANTED)
    skus = [f"SKU-{n:02d}" for n in range(1, 14)] + ["MURUKKU-200G", "MURUKKU-500G"]
    routes = [f"R-{n}" for n in range(1, 13)]
    customers = []
    for n in range(1, 121):
        route = routes[(n - 1) % 12]
        state = STATES[0] if route in ("R-1", "R-2", "R-3", "R-4", "R-5", "R-6", "R-7") else STATES[1 + n % 2]
        customers.append((f"C-{n:03d}", route, state, rng.uniform(4, 20)))
    fest = festival_weeks(START, WEEKS)
    order_no = 0
    for week in range(WEEKS):
        day = START + timedelta(weeks=week)
        trend = 1 + 0.004 * week
        for cid, route, state, size in customers:
            for sku in skus:
                if sku == "MURUKKU-500G" and not (state == "TN" and _month(week) >= 13):
                    continue
                if rng.random() > (0.9 if sku.startswith("MURUKKU") else 0.18):
                    continue
                base = size * (3.0 if sku.startswith("MURUKKU") else 1.0) * trend
                uplift = max(
                    (
                        PLANTED["festival_uplift"][name]
                        for name, states, weeks in fest
                        if week in weeks and state in states
                    ),
                    default=1.0,
                )
                cannibal = (
                    1 + PLANTED["cannibalisation_500g_on_200g"]["effect"]
                    if sku == "MURUKKU-200G" and state == "TN" and _month(week) >= 13
                    else 1.0
                )
                qty = max(1, round(base * uplift * cannibal * rng.lognormvariate(0, 0.12)))
                order_no += 1
                key = f"K{order_no:07d}"
                line = OrderLine(f"O{order_no:07d}", key, week, day.isoformat(), cid, route, state, sku, qty)
                w.orders.append(line)
                if rng.random() < PLANTED["faults"]["duplicate_sync_rate"]:
                    w.orders.append(OrderLine(**{**asdict(line), "order_id": f"O{order_no:07d}D"}))
                    w.fault_ids["duplicate"].add(f"O{order_no:07d}D")
                if rng.random() < PLANTED["faults"]["unit_error_rate"]:
                    line.packets *= PLANTED["faults"]["unit_error_factor"]
                    w.fault_ids["unit_error"].add(line.order_id)
        # invoices: one per customer per week they ordered; payment delay by route
        for cid, route, _state, size in customers:
            if rng.random() > 0.85:
                continue
            mean = PLANTED["route_payment_days"]["R-7" if route == "R-7" else "other"]
            days = max(0, round(rng.gauss(mean, 6)))
            w.invoices.append(
                Invoice(
                    f"I{len(w.invoices) + 1:06d}",
                    cid,
                    route,
                    day.isoformat(),
                    (day + timedelta(days=days)).isoformat(),
                    days,
                    round(size * 150 * rng.uniform(0.8, 1.2), 2),
                )
            )
    operators = {"day": ["O-1", "O-2"], "night": ["O-3", "O-4"]}
    suppliers = [f"S-0{n}" for n in range(1, 9)]
    for d in range(WEEKS * 7):
        day = START + timedelta(days=d)
        month = d // 30 + 1
        for shift in ("day", "night"):
            if shift == "night" and month < 7:
                continue  # the night shift starts in month 7
            op = rng.choice(operators[shift])
            sup = rng.choice(suppliers)
            lot = f"{sup}-L{d // 10:03d}"
            yield_effect = PLANTED["supplier_lot_yield_effect"].get(sup, 0.0)
            yield_pct = min(100.0, rng.gauss(95.0, 1.2) * (1 + yield_effect))
            oil = rng.gauss(10.0, 0.15) * (1 + (PLANTED["operator_oil_effect"]["O-3"] if op == "O-3" else 0))
            good = round(200 * yield_pct / 100)
            w.runs.append(
                Run(
                    f"B{len(w.runs) + 1:05d}",
                    day.isoformat(),
                    month,
                    op,
                    shift,
                    sup,
                    lot,
                    200,
                    good,
                    round(yield_pct, 3),
                    round(oil, 3),
                )
            )
    return w


def write(world: World, out: Path) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, rows in (("orders", world.orders), ("runs", world.runs), ("invoices", world.invoices)):
        with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            fields = list(asdict(rows[0]))
            wr = csv.DictWriter(f, fieldnames=fields)
            wr.writeheader()
            wr.writerows(asdict(r) for r in rows)
        counts[name] = len(rows)
    return counts
