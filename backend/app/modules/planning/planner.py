"""The batch planner (MP12, ADR-0019 L4). Pure: no database. OR-Tools CP-SAT, a small integer program.

Decide how many standard batches of each pack to make in the next production day so that the value of open demand
met is as large as possible, within the materials on hand and the daily batch capacity; ties go to fewer batches.
Then work out what a full plan (every open packet) would need, what is short, and what to buy:
  buy = max(0, full-plan need + safety stock - available); if what is left after today's plan falls below the reorder
  level, at least enough to come back to reorder level + safety stock; rounded up to the minimum order.
Quantities are base units (Decimal) scaled to integers for the solver; money is paise.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from typing import Final

from ortools.sat.python import cp_model

from app.core.explained import Explained, ExplainedInput
from app.core.money import round_money
from app.modules.planning.domain import PlanningError

SCALE: Final = 10**6  # base units carry 6 decimals
TIME_LIMIT_S: Final = 5.0


@dataclass(frozen=True)
class PackOption:
    code: str
    version_id: str
    fg_item: str  # item code of the finished good
    good_per_batch: int  # expected good units of one standard batch (rounded down)
    needs: Mapping[str, Decimal]  # material code -> base units per batch


@dataclass(frozen=True)
class Demand:
    fg_item: str
    open_packets: int  # not yet decided + backordered
    available: int  # available to promise now
    value_per_packet: Decimal  # ex-tax, weighted over the open lines

    @property
    def shortfall(self) -> int:
        return max(0, self.open_packets - max(0, self.available))


@dataclass(frozen=True)
class ItemParams:
    reorder_level: Decimal = Decimal(0)
    safety_stock: Decimal = Decimal(0)
    min_order: Decimal = Decimal(0)
    lead_time_days: int = 0


@dataclass(frozen=True)
class Purchase:
    item: str
    qty: Decimal  # base units
    explained: Explained
    lead_time_days: int


@dataclass
class Plan:
    status: str  # OPTIMAL, FEASIBLE or NOTHING_TO_PLAN
    batches: dict[str, int] = field(default_factory=dict)  # pack code -> batches today
    met: dict[str, int] = field(default_factory=dict)  # fg item -> packets of the shortfall met
    value_met: Decimal = Decimal("0.00")
    materials_used: dict[str, Decimal] = field(default_factory=dict)
    full_need: dict[str, Decimal] = field(default_factory=dict)
    short: dict[str, Decimal] = field(default_factory=dict)  # for a full plan
    purchases: list[Purchase] = field(default_factory=list)
    explained: dict[str, Explained] = field(default_factory=dict)  # pack code -> why that many batches


def _scaled(q: Decimal) -> int:
    return int((q * SCALE).to_integral_value(rounding=ROUND_CEILING))


def plan(
    packs: Sequence[PackOption],
    demand: Sequence[Demand],
    available: Mapping[str, Decimal],
    capacity: int,
    params: Mapping[str, ItemParams],
) -> Plan:
    if capacity < 0:
        raise PlanningError("bad_capacity", "batch capacity cannot be negative")
    short_of = {d.fg_item: d for d in demand if d.shortfall > 0}
    options = [p for p in packs if p.fg_item in short_of and p.good_per_batch > 0]
    result = Plan(status="NOTHING_TO_PLAN")
    if options and capacity > 0:
        model = cp_model.CpModel()
        b = {p.code: model.new_int_var(0, capacity, f"b_{p.code}") for p in options}
        model.add(sum(b.values()) <= capacity)
        for m in {m for p in options for m in p.needs}:
            model.add(
                sum(_scaled(p.needs[m]) * b[p.code] for p in options if m in p.needs)
                <= max(0, _scaled(available.get(m, Decimal(0))))
            )
        met = {}
        for item, d in short_of.items():
            makes = [p for p in options if p.fg_item == item]
            if not makes:
                continue
            met[item] = model.new_int_var(0, d.shortfall, f"met_{item}")
            model.add(met[item] <= sum(p.good_per_batch * b[p.code] for p in makes))
        weight = len(options) * capacity + 1  # one paisa of value beats any number of batches saved
        model.maximize(
            sum(int(round_money(short_of[i].value_per_packet) * 100) * weight * v for i, v in met.items())
            - sum(b.values())
        )
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = TIME_LIMIT_S
        solver.parameters.num_workers = 1  # deterministic
        status = solver.status_name(solver.solve(model))
        if status not in ("OPTIMAL", "FEASIBLE"):
            raise PlanningError("no_plan", "the planner found no feasible plan")
        result.status = status
        result.batches = {code: int(solver.value(v)) for code, v in b.items()}
        result.met = {item: int(solver.value(v)) for item, v in met.items()}
        result.value_met = round_money(
            sum((short_of[i].value_per_packet * n for i, n in result.met.items()), Decimal(0))
        )
        for p in options:
            n = result.batches[p.code]
            for m, q in p.needs.items():
                result.materials_used[m] = result.materials_used.get(m, Decimal(0)) + q * n
            result.explained[p.code] = Explained(
                value=Decimal(n),
                unit="batches",
                formula="maximise value of open demand met within materials on hand and daily capacity",
                inputs=(
                    ExplainedInput(
                        f"{p.fg_item} short (open - available)", Decimal(short_of[p.fg_item].shortfall), "packets"
                    ),
                    ExplainedInput("good packets per batch", Decimal(p.good_per_batch), "packets"),
                    ExplainedInput("daily batch capacity", Decimal(capacity), "batches"),
                ),
                method="Batch planner (CP-SAT)",
            )
    # what a full plan would need, what is short and what to buy
    full_batches: dict[str, int] = {}
    for item, d in short_of.items():
        make = next((p for p in packs if p.fg_item == item and p.good_per_batch > 0), None)
        if make is not None:
            full_batches[make.code] = math.ceil(d.shortfall / make.good_per_batch)
    for p in packs:
        for m, q in p.needs.items():
            result.full_need[m] = result.full_need.get(m, Decimal(0)) + q * full_batches.get(p.code, 0)
    for m in sorted(set(result.full_need) | set(params)):
        need = result.full_need.get(m, Decimal(0))
        have = available.get(m, Decimal(0))
        prm = params.get(m, ItemParams())
        if need > have:
            result.short[m] = need - have
        after_today = have - result.materials_used.get(m, Decimal(0))
        qty = max(Decimal(0), need + prm.safety_stock - have)
        if after_today < prm.reorder_level:
            qty = max(qty, prm.reorder_level + prm.safety_stock - after_today)
        if Decimal(0) < qty < prm.min_order:
            qty = prm.min_order
        if qty > 0:
            result.purchases.append(
                Purchase(
                    m,
                    qty,
                    Explained(
                        value=qty,
                        unit="base units",
                        formula="max(full-plan need + safety stock - available, reorder level + safety - left "
                        "after today), at least the minimum order",
                        inputs=(
                            ExplainedInput("needed for every open packet", need, "base units"),
                            ExplainedInput("safety stock", prm.safety_stock, "base units"),
                            ExplainedInput("available", have, "base units"),
                            ExplainedInput("left after today's plan", after_today, "base units"),
                            ExplainedInput("reorder level", prm.reorder_level, "base units"),
                            ExplainedInput("minimum order", prm.min_order, "base units"),
                        ),
                        method="Suggested purchase",
                    ),
                    prm.lead_time_days,
                )
            )
    return result
