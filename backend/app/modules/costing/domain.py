"""Pure costing rules (MP05 D3, MP07, ADR-0004, ADR-0014). No database, and no product knowledge: every number comes
from the run's frozen snapshot, its posted actuals (`production.domain.RunCostingFacts`) and a standard cost card.

- **Standard cost** per unit = (Σ ingredient qty x standard rate + conversion per batch + Σ packaging per unit x
  rate x expected units) / expected units, at full yield (assumption A2). Benchmark: 5,770.00 / 200 = 28.85.
- **Run cost** = materials at book value (net issues + packaging taken at completion) + direct run costs. Cost per
  good unit = run cost / good units, 6 dp, shown to paise (₹5,855.00 / 188 = 31.143617 -> ₹31.14).
- **Waterfall** (decision F5): actual - standard of the good output, split exactly into
  price = actual value - standard rate x actual qty          (per item)
  usage = (actual qty - standard qty) x standard rate        (ingredients: batch standard; packaging: flexible)
  yield = per-batch standard x share of bulk x (expected - good) / expected   (per pack line)
  bulk not allocated = per-batch standard x unallocated / expected bulk
  conversion spend = actual run costs - conversion standard x batch multiplier
  Each part is rounded half up to paise; any difference to the rounded total is an explicit "rounding" part.
- **Sensitivity** (decision F6): the same run with each issue re-valued under FIFO / LAST as of that issue. A method
  with no answer for a movement (LAST before any purchase) uses the book value for it, and says so.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final

from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money, round_unit_cost
from app.modules.production.domain import PackStd, RecipeStd, RunCostingFacts, StdLine, expected_units
from app.modules.uom.domain import ItemUnits, from_base, normalise, to_base
from app.modules.valuation.domain import line_value

ZERO: Final = Decimal(0)
RATE_STEP: Final = Decimal("0.000001")
MATERIAL: Final = "MATERIAL"
PACKAGING: Final = "PACKAGING"
CONVERSION: Final = "CONVERSION"
UNFAVOURABLE: Final = "UNFAVOURABLE"
FAVOURABLE: Final = "FAVOURABLE"
NONE: Final = "NONE"


class CostingError(DomainError):
    """A costing figure the books cannot produce."""


# ---------- the MP05 standard (D3, still used for the opening lot) ----------


@dataclass(frozen=True)
class StandardLine:
    item: str
    qty_per_batch: Decimal  # in the rate's unit (kg, L, piece)
    rate: Decimal  # standard rate: the opening purchase rate (assumption A2)


@dataclass(frozen=True)
class StandardCost:
    materials_per_batch: Decimal
    conversion_per_batch: Decimal
    total_per_batch: Decimal
    expected_output: Decimal
    per_unit: Decimal  # 6 dp; shown to paise


def standard_cost(
    lines: Sequence[StandardLine], conversion_per_batch: Decimal, expected_output: Decimal
) -> StandardCost:
    """(Σ BOM qty x standard rate + conversion costs) / expected good output, at full yield (A2).

    Benchmark: (1,680 + 1,400 + 240 + 500 + 150) + (1,200 + 600) = 5,770.00 per batch / 200 = 28.85 per packet.
    """
    if expected_output <= 0:
        raise DomainError("bad_expected_output", "expected good output must be positive")
    materials = sum((line_value(line.qty_per_batch, line.rate) for line in lines), Decimal(0))
    total = materials + conversion_per_batch
    return StandardCost(
        materials_per_batch=materials,
        conversion_per_batch=conversion_per_batch,
        total_per_batch=total,
        expected_output=expected_output,
        per_unit=round_unit_cost(total / expected_output),
    )


# ---------- standard cost cards (decision F4) ----------


@dataclass(frozen=True)
class CardLine:
    cost_kind: str  # MATERIAL (per batch), PACKAGING (per good unit) or CONVERSION (rupees per batch)
    item_id: uuid.UUID | None
    label: str
    std_qty_base: Decimal
    std_rate: Decimal  # rupees per base unit (g, mL, piece), 6 dp; CONVERSION: 1 x the amount


@dataclass(frozen=True)
class StandardCard:
    card_id: uuid.UUID | None
    pack_spec_version_id: uuid.UUID
    version: int
    effective_from: date
    per_unit: Decimal
    lines: tuple[CardLine, ...]

    def rate(self, item_id: uuid.UUID) -> Decimal | None:
        return next((ln.std_rate for ln in self.lines if ln.item_id == item_id), None)

    @property
    def conversion_per_batch(self) -> Decimal:
        return sum((ln.std_qty_base * ln.std_rate for ln in self.lines if ln.cost_kind == CONVERSION), ZERO)

    def per_batch_rates(self) -> tuple[tuple[uuid.UUID | None, Decimal], ...]:
        """What must agree between the cards of one run: ingredient rates and conversion (decision F5)."""
        rates = sorted((str(ln.item_id), ln.std_rate) for ln in self.lines if ln.cost_kind == MATERIAL)
        return (*((uuid.UUID(i), r) for i, r in rates), (None, self.conversion_per_batch))


def rate_per_base(rate_per_unit: Decimal, units: ItemUnits) -> Decimal:
    """₹42 per kg -> ₹0.042 per g. Refused, not rounded, when it is not exact at 6 dp."""
    per_base = rate_per_unit / to_base(Decimal(1), units.stock_uom, units)
    if per_base < 0 or per_base != per_base.quantize(RATE_STEP):
        raise CostingError(
            "rate_too_precise", f"₹{rate_per_unit} per {units.stock_uom} is not exact at 6 dp per base unit"
        )
    return per_base


def rate_per_stock_unit(rate_per_base_unit: Decimal, units: ItemUnits) -> Decimal:
    """Display: ₹0.042 per g -> ₹42 per kg."""
    return normalise(rate_per_base_unit * to_base(Decimal(1), units.stock_uom, units))


def card_lines(
    recipe: RecipeStd,
    pack: PackStd,
    rates: Mapping[uuid.UUID, Decimal],
    conversion: Mapping[str, Decimal],
) -> tuple[list[CardLine], Decimal]:
    """The card for one pack spec version made from a full batch: lines and the standard cost per unit (6 dp).

    `rates` are rupees per base unit for every ingredient and packaging item; `conversion` is rupees per batch.
    """
    lines: list[CardLine] = []
    for ln in recipe.lines:
        if ln.item_id not in rates:
            raise CostingError("rate_missing", f"no standard rate for {ln.item_code}")
        lines.append(CardLine(MATERIAL, ln.item_id, ln.item_code, ln.qty_base, rates[ln.item_id]))
    for ln in pack.lines:
        if ln.item_id not in rates:
            raise CostingError("rate_missing", f"no standard rate for {ln.item_code}")
        lines.append(CardLine(PACKAGING, ln.item_id, ln.item_code, ln.qty_base, rates[ln.item_id]))
    for label, amount in sorted(conversion.items()):
        if amount < 0:
            raise CostingError("negative_conversion", "a conversion standard cannot be negative")
        lines.append(CardLine(CONVERSION, None, label, Decimal(1), amount))
    expected = expected_units(recipe.bulk_yield_g, pack.net_g)
    per_batch = sum(
        (ln.std_qty_base * ln.std_rate for ln in lines if ln.cost_kind in (MATERIAL, CONVERSION)), ZERO
    ) + sum((ln.std_qty_base * ln.std_rate * expected for ln in lines if ln.cost_kind == PACKAGING), ZERO)
    return lines, round_unit_cost(per_batch / expected)


# ---------- run cost ----------


def _qty(m_qty: Decimal, base: str, stock: str) -> Decimal:
    return from_base(m_qty, stock, ItemUnits(base_uom=base, stock_uom=stock))


@dataclass(frozen=True)
class RunCost:
    materials: Explained
    conversion: Explained
    total: Explained
    per_good_unit: Explained | None  # one pack line: run cost / good units; several: see `lots`
    lots: tuple[Explained, ...]  # per pack line with good units: its lot value / its good units
    written_off: Decimal

    def to_json(self) -> dict[str, Any]:
        return {
            "materials": self.materials.to_json(),
            "conversion": self.conversion.to_json(),
            "total": self.total.to_json(),
            "per_good_unit": None if self.per_good_unit is None else self.per_good_unit.to_json(),
            "per_good_unit_display": None if self.per_good_unit is None else str(round_money(self.per_good_unit.value)),
            "lots": [lot.to_json() for lot in self.lots],
            "written_off": str(self.written_off),
        }


def run_cost(facts: RunCostingFacts) -> RunCost:
    run = SourceRef("production_run", str(facts.run_id))
    materials = Explained(
        value=sum((m.value for m in facts.materials), ZERO),
        unit="INR",
        formula="Σ materials at book value (net issues + packaging taken at completion)",
        method="WAC",
        inputs=tuple(
            ExplainedInput(
                f"{m.item_code} {normalise(_qty(m.qty_base, m.base_uom, m.stock_uom))} {m.stock_uom}",
                m.value,
                "INR",
                SourceRef("stock_journal", str(m.moves[0].journal_id)) if m.moves else run,
            )
            for m in facts.materials
        ),
    )
    conversion = Explained(
        value=sum((c.amount for c in facts.conversion), ZERO),
        unit="INR",
        formula="Σ direct run costs (labour, gas/power, other)",
        inputs=tuple(
            ExplainedInput(c.kind.lower(), c.amount, "INR", SourceRef("run_cost", str(c.run_cost_id)))
            for c in facts.conversion
        ),
    )
    total = Explained(
        value=materials.value + conversion.value,
        unit="INR",
        formula="materials + direct run costs",
        method="WAC" if facts.cost_status == "FINAL" else "WAC, PROVISIONAL",
        inputs=(
            ExplainedInput("materials", materials.value, "INR", run),
            ExplainedInput("direct run costs", conversion.value, "INR", run),
        ),
    )
    lots = tuple(
        Explained(
            value=round_unit_cost(p.lot_value / p.good_units),
            unit=f"INR/{p.pack.fg_stock_uom}",
            formula="lot value / good units",
            method=p.lot_no,
            inputs=(
                ExplainedInput("lot value (on hand, in transit and sold)", p.lot_value, "INR", run),
                ExplainedInput("good units", Decimal(p.good_units), p.pack.fg_stock_uom, run),
            ),
        )
        for p in facts.packs
        if p.good_units > 0
    )
    per_unit = None
    if len(facts.packs) == 1 and facts.packs[0].good_units > 0:
        p = facts.packs[0]
        per_unit = Explained(
            value=round_unit_cost(total.value / p.good_units),
            unit=f"INR/{p.pack.fg_stock_uom}",
            formula="run cost / good units",
            method=total.method,
            inputs=(
                ExplainedInput("run cost", total.value, "INR", run),
                ExplainedInput("good units", Decimal(p.good_units), p.pack.fg_stock_uom, run),
            ),
        )
    return RunCost(materials, conversion, total, per_unit, lots, facts.written_off)


# ---------- the waterfall (decision F5) ----------


def _in_stock(qty_base: Decimal, line: StdLine) -> Decimal:
    return normalise(from_base(qty_base, line.stock_uom, line.units))


@dataclass(frozen=True)
class Component:
    kind: str  # YIELD, PRICE, USAGE, CONVERSION, UNALLOCATED, NO_STANDARD, ROUNDING
    label: str
    item_code: str | None
    value: Decimal  # rupees, + unfavourable, - favourable
    explained: Explained
    note: str | None = None

    @property
    def direction(self) -> str:
        return UNFAVOURABLE if self.value > 0 else FAVOURABLE if self.value < 0 else NONE

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "item_code": self.item_code,
            "value": str(self.value),
            "direction": self.direction,
            "note": self.note,
            "explained": self.explained.to_json(),
        }


@dataclass(frozen=True)
class Waterfall:
    actual: Explained
    standard: Explained
    total: Explained  # actual - standard, + unfavourable
    components: tuple[Component, ...] = field(default_factory=tuple)

    def component(self, kind: str, item_code: str | None = None) -> Component:
        return next(c for c in self.components if c.kind == kind and (item_code is None or c.item_code == item_code))

    def to_json(self) -> dict[str, Any]:
        ranked = sorted(self.components, key=lambda c: -c.value)
        return {
            "actual": self.actual.to_json(),
            "standard": self.standard.to_json(),
            "total": self.total.to_json(),
            "direction": UNFAVOURABLE if self.total.value > 0 else FAVOURABLE if self.total.value < 0 else NONE,
            "components": [c.to_json() for c in ranked],
        }


def _part(
    kind: str,
    label: str,
    item: str | None,
    exact: Decimal,
    formula: str,
    inputs: Sequence[ExplainedInput],
    note: str | None = None,
) -> Component:
    value = round_money(exact)
    return Component(kind, label, item, value, Explained(value, "INR", formula, tuple(inputs)), note)


def waterfall(facts: RunCostingFacts, cards: Sequence[StandardCard]) -> Waterfall:
    """Actual - standard of the good output, split exactly into price, usage, yield and conversion parts."""
    if len(cards) != len(facts.packs):
        raise CostingError("card_missing", "every pack line needs the standard cost card in force on the run date")
    if len({c.per_batch_rates() for c in cards}) > 1:
        raise CostingError(
            "mixed_standards", "the pack lines' cards disagree on ingredient rates or conversion: no single waterfall"
        )
    card = cards[0]
    run = SourceRef("production_run", str(facts.run_id))
    cref = SourceRef("standard_cost_card", str(card.card_id))
    mult = facts.batch_multiplier
    recipe = facts.recipe
    exp_bulk = recipe.bulk_yield_g * mult
    parts: list[Component] = []

    # ingredients: price and usage against the batch standard
    ingredients = {m.item_id: m for m in facts.materials if m.role == "INGREDIENT"}
    per_batch_ing = ZERO
    for ln in recipe.lines:
        rate = card.rate(ln.item_id)
        if rate is None:
            raise CostingError("rate_missing", f"the standard cost card has no rate for {ln.item_code}")
        std_qty = ln.qty_base * mult
        per_batch_ing += std_qty * rate
        m = ingredients.pop(ln.item_id, None)
        qty, value = (m.qty_base, m.value) if m else (ZERO, ZERO)
        r = rate_per_stock_unit(rate, ln.units)
        parts.append(
            _part(
                "PRICE",
                f"{ln.item_code} price",
                ln.item_code,
                value - rate * qty,
                "actual value - standard rate x actual qty",
                (
                    ExplainedInput("actual value", value, "INR", run),
                    ExplainedInput("actual qty", _in_stock(qty, ln), ln.stock_uom, run),
                    ExplainedInput("standard rate", r, f"INR/{ln.stock_uom}", cref),
                ),
            )
        )
        parts.append(
            _part(
                "USAGE",
                f"{ln.item_code} usage",
                ln.item_code,
                (qty - std_qty) * rate,
                "(actual qty - batch standard qty) x standard rate",
                (
                    ExplainedInput("actual qty", _in_stock(qty, ln), ln.stock_uom, run),
                    ExplainedInput("batch standard qty", _in_stock(std_qty, ln), ln.stock_uom, run),
                    ExplainedInput("standard rate", r, f"INR/{ln.stock_uom}", cref),
                ),
            )
        )
    for m in ingredients.values():  # issued but not in the recipe: no standard at all
        parts.append(
            _part(
                "NO_STANDARD",
                f"{m.item_code} (not in the recipe)",
                m.item_code,
                m.value,
                "actual value, no standard",
                (ExplainedInput("actual value", m.value, "INR", run),),
            )
        )

    # conversion
    conv_std = card.conversion_per_batch * mult
    conv_actual = sum((c.amount for c in facts.conversion), ZERO)
    per_batch_std = per_batch_ing + conv_std
    parts.append(
        _part(
            "CONVERSION",
            "conversion spend",
            None,
            conv_actual - conv_std,
            "actual direct run costs - conversion standard per batch x batch multiplier",
            (
                ExplainedInput("actual run costs", conv_actual, "INR", run),
                ExplainedInput("conversion standard", normalise(conv_std), "INR", cref),
            ),
        )
    )

    # yield per pack line, bulk not allocated, packaging usage per pack line and price per item
    std_of_good = ZERO
    pkg_std_at_actual: dict[uuid.UUID, Decimal] = {}
    for p, c in zip(facts.packs, cards, strict=True):
        share = p.bulk_allocated_g / exp_bulk
        expected = expected_units(p.bulk_allocated_g, p.pack.net_g)
        std_of_good += per_batch_std * share * p.good_units / expected
        parts.append(
            _part(
                "YIELD",
                f"yield loss {p.pack.code}",
                p.pack.fg_item_code,
                per_batch_std * share * (expected - p.good_units) / expected,
                "per-batch standard x share of bulk x (expected - good) / expected",
                (
                    ExplainedInput(
                        "per-batch standard (ingredients + conversion)", normalise(per_batch_std), "INR", cref
                    ),
                    ExplainedInput("share of bulk", normalise(share), "x", run),
                    ExplainedInput("expected units", normalise(expected), p.pack.fg_stock_uom, run),
                    ExplainedInput("good units", Decimal(p.good_units), p.pack.fg_stock_uom, run),
                ),
            )
        )
        for ln in p.pack.lines:
            rate = c.rate(ln.item_id)
            if rate is None:
                raise CostingError("rate_missing", f"the standard cost card has no rate for {ln.item_code}")
            flexible = ln.qty_base * p.good_units
            used = p.used.get(ln.item_id, ZERO)
            std_of_good += flexible * rate
            pkg_std_at_actual[ln.item_id] = pkg_std_at_actual.get(ln.item_id, ZERO) + rate * used
            damaged = p.damaged.get(ln.item_id, ZERO)
            parts.append(
                _part(
                    "USAGE",
                    f"{ln.item_code} usage",
                    ln.item_code,
                    (used - flexible) * rate,
                    "(used - qty per good unit x good units) x standard rate",
                    (
                        ExplainedInput("used", normalise(used), ln.stock_uom, run),
                        ExplainedInput("flexible standard", normalise(flexible), ln.stock_uom, run),
                        ExplainedInput("standard rate", normalise(rate), f"INR/{ln.stock_uom}", cref),
                    ),
                    note=f"{normalise(damaged)} damaged" if damaged else None,
                )
            )
    unallocated = exp_bulk - sum((p.bulk_allocated_g for p in facts.packs), ZERO)
    if unallocated:
        parts.append(
            _part(
                "UNALLOCATED",
                "bulk not allocated to a pack",
                None,
                per_batch_std * unallocated / exp_bulk,
                "per-batch standard x unallocated bulk / expected bulk",
                (ExplainedInput("unallocated bulk", normalise(unallocated / 1000), "kg", run),),
            )
        )
    for m in facts.materials:
        if m.role == "PACKAGING":
            at_std = pkg_std_at_actual.get(m.item_id, ZERO)
            parts.append(
                _part(
                    "PRICE",
                    f"{m.item_code} price",
                    m.item_code,
                    m.value - at_std,
                    "actual value - standard rate x actual qty",
                    (
                        ExplainedInput("actual value", m.value, "INR", run),
                        ExplainedInput("actual qty at standard rates", normalise(at_std), "INR", cref),
                    ),
                )
            )

    actual_total = sum((m.value for m in facts.materials), ZERO) + conv_actual
    standard_total = round_money(std_of_good)
    total = actual_total - standard_total
    rounding = total - sum((c.value for c in parts), ZERO)
    if rounding:
        parts.append(
            Component(
                "ROUNDING",
                "rounding (parts rounded to paise)",
                None,
                rounding,
                Explained(rounding, "INR", "total variance - Σ rounded parts"),
            )
        )
    return Waterfall(
        actual=Explained(actual_total, "INR", "materials + direct run costs", (ExplainedInput("run", ZERO, "", run),)),
        standard=Explained(
            standard_total,
            "INR",
            "per-batch standard x good share + packaging standard x good units",
            (ExplainedInput("card per unit", card.per_unit, "INR", cref),),
        ),
        total=Explained(
            total,
            "INR",
            "actual - standard of the good output = Σ parts",
            (
                ExplainedInput("actual", actual_total, "INR", run),
                ExplainedInput("standard", standard_total, "INR", cref),
            ),
        ),
        components=tuple(c for c in parts if c.value != 0 or c.kind in ("YIELD", "CONVERSION")),
    )


# ---------- sensitivity (decision F6) ----------


@dataclass(frozen=True)
class MethodValue:
    item_code: str
    book: Decimal  # posted (WAC)
    value: Decimal  # under the method
    fallback: bool  # True when the method had no answer and the book value was used


def sensitivity(
    run_total: Decimal, good_units: int, by_method: Mapping[str, Sequence[MethodValue]], unit: str
) -> dict[str, dict[str, Any]]:
    """Run cost and cost per good unit under each method. Only WAC posts."""
    out: dict[str, dict[str, Any]] = {}
    for method, values in by_method.items():
        total = run_total - sum((v.book for v in values), ZERO) + sum((v.value for v in values), ZERO)
        per = None if good_units <= 0 else round_unit_cost(total / good_units)
        out[method] = {
            "posts": method == "WAC",
            "total": Explained(
                total,
                "INR",
                "run cost with each issue re-valued under this method, as of that issue",
                tuple(ExplainedInput(v.item_code, v.value, "INR") for v in values),
                method=method,
            ).to_json(),
            "per_good_unit": None if per is None else str(per),
            "per_good_unit_display": None if per is None else str(round_money(per)),
            "unit": f"INR/{unit}",
            "book_value_used_for": sorted({v.item_code for v in values if v.fallback}),
        }
    return out
