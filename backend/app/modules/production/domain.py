"""Pure production rules (MP06, ADR-0003, ADR-0013): the variance engine, packing, mass balance and the completion
journal. No database, and no product knowledge: every number comes from the snapshot a run froze when it started.

Formulas (docs/architecture/bom.md section 2):
    expected bulk       = recipe bulk yield x batch multiplier
    expected units      = bulk allocated / net per unit
    batch standard      = recipe qty x batch multiplier                    (PER_BATCH lines: ingredients)
    flexible standard   = qty per good unit x good units                   (PER_GOOD_UNIT lines: packaging)
    usage variance %    = (actual - standard) / standard x 100
    yield variance %    = (good - expected) / expected x 100
    flagged             = beyond tolerance AND unfavourable                (decision E2; strict, unrounded)
    packing             = divmod(good units, units per carton)
    mass balance        = expected bulk = good x net + scrap + loss + unexplained gap (never forced to 0)
    giveaway            = (mean sampled net - declared net) x good units   (part of the gap, shown)

The completion journal (ADR-0013): the run's own net issues WIP -> PRODUCTION; packaging PACK_STORE -> PRODUCTION at
WAC with damaged units to SCRAP at no value; one FG lot per pack line PRODUCTION -> FG_STORE. Ingredient value is
split between pack lines by bulk allocated, packaging goes to its own line, and the last line takes the rounding
remainder. A pack line with no good units writes its share off to SCRAP as an explicit valued line (decision E4).
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money
from app.modules.ledger.domain import LineSpec
from app.modules.uom.domain import ItemUnits, from_base, normalise, require_decimal, split_into_cartons

ZERO: Final = Decimal(0)
HUNDRED: Final = Decimal(100)
PCT_DISPLAY: Final = Decimal("0.01")
MASS_DISPLAY: Final = Decimal("0.000001")
UNFAVOURABLE: Final = "UNFAVOURABLE"
FAVOURABLE: Final = "FAVOURABLE"
ON_STANDARD: Final = "ON_STANDARD"
TOLERANCE_SETTING: Final = "variance_tolerance_pct"
MAX_PACK_LINES: Final = 26  # lot suffixes -A .. -Z


class RunError(DomainError):
    """A production run the books refuse."""


def _d(text: str | None) -> Decimal | None:
    return None if text is None else Decimal(text)


def _n(d: Decimal) -> str:
    return str(normalise(d))


# ---------- numbering (decision E3) ----------


def run_no(n: int) -> str:
    """B-001, B-002, ... per organization, a perpetual sequence."""
    return f"B-{n:03d}"


def issue_no(fy: str, n: int) -> str:
    """MI/26-27/000001, gapless per organization and financial year."""
    return f"MI/{fy}/{n:06d}"


def lot_numbers(run_number: str, pack_lines: int) -> list[str]:
    """The lot no. is the run no.; a run with several pack lines gets -A, -B, ... in pack-line order."""
    if pack_lines < 1:
        raise RunError("no_pack_lines", "a run needs at least one pack line")
    if pack_lines > MAX_PACK_LINES:
        raise RunError("too_many_pack_lines", f"a run can have at most {MAX_PACK_LINES} pack lines")
    if pack_lines == 1:
        return [run_number]
    return [f"{run_number}-{chr(ord('A') + i)}" for i in range(pack_lines)]


def best_before(run_date: date, shelf_life_days: int) -> date:
    return run_date + timedelta(days=shelf_life_days)


# ---------- the frozen standards ----------


@dataclass(frozen=True)
class StdLine:
    item_id: uuid.UUID
    item_code: str
    base_uom: str
    stock_uom: str
    qty_base: Decimal  # per batch (recipe) or per good unit (pack spec)
    tolerance_pct: Decimal | None

    @property
    def units(self) -> ItemUnits:
        return ItemUnits(base_uom=self.base_uom, stock_uom=self.stock_uom)


def _std_lines(raw: Sequence[Mapping[str, Any]]) -> tuple[StdLine, ...]:
    return tuple(
        StdLine(
            item_id=uuid.UUID(ln["item_id"]),
            item_code=ln["item_code"],
            base_uom=ln["base_uom"],
            stock_uom=ln["stock_uom"],
            qty_base=Decimal(ln["qty_base"]),
            tolerance_pct=_d(ln.get("tolerance_pct")),
        )
        for ln in raw
    )


@dataclass(frozen=True)
class RecipeStd:
    version_id: uuid.UUID
    code: str
    version: int
    bulk_item_id: uuid.UUID
    bulk_item_code: str
    bulk_yield_g: Decimal
    lines: tuple[StdLine, ...]

    @staticmethod
    def from_snapshot(snap: Mapping[str, Any]) -> "RecipeStd":
        return RecipeStd(
            version_id=uuid.UUID(snap["version_id"]),
            code=snap["code"],
            version=int(snap["version"]),
            bulk_item_id=uuid.UUID(snap["bulk_item_id"]),
            bulk_item_code=snap["bulk_item_code"],
            bulk_yield_g=Decimal(snap["bulk_yield_g"]),
            lines=_std_lines(snap["lines"]),
        )


@dataclass(frozen=True)
class PackStd:
    version_id: uuid.UUID
    code: str
    name: str
    version: int
    recipe_id: uuid.UUID
    fg_item_id: uuid.UUID
    fg_item_code: str
    fg_stock_uom: str
    net_g: Decimal
    units_per_carton: int
    shelf_life_days: int
    lines: tuple[StdLine, ...]

    @staticmethod
    def from_snapshot(snap: Mapping[str, Any]) -> "PackStd":
        return PackStd(
            version_id=uuid.UUID(snap["version_id"]),
            code=snap["code"],
            name=snap["name"],
            version=int(snap["version"]),
            recipe_id=uuid.UUID(snap["recipe_id"]),
            fg_item_id=uuid.UUID(snap["fg_item_id"]),
            fg_item_code=snap["fg_item_code"],
            fg_stock_uom=snap["fg_stock_uom"],
            net_g=Decimal(snap["net_g"]),
            units_per_carton=int(snap["units_per_carton"]),
            shelf_life_days=int(snap["shelf_life_days"]),
            lines=_std_lines(snap["lines"]),
        )

    def line_for(self, item_id: uuid.UUID) -> StdLine | None:
        return next((ln for ln in self.lines if ln.item_id == item_id), None)

    def is_carton_line(self, line: StdLine) -> bool:
        """The packaging line that is the carton itself: one per `units_per_carton` good units."""
        return line.qty_base * self.units_per_carton == 1


# ---------- allocation ----------


def expected_bulk(recipe: RecipeStd | Decimal, batch_multiplier: Decimal) -> Decimal:
    multiplier = require_decimal(batch_multiplier, "batch_multiplier")
    if multiplier <= 0:
        raise RunError("bad_batch_multiplier", "the batch multiplier must be positive")
    yield_g = recipe.bulk_yield_g if isinstance(recipe, RecipeStd) else recipe
    return yield_g * multiplier


def expected_units(bulk_allocated_g: Decimal, net_g: Decimal) -> Decimal:
    """Bulk allocated / net per unit, exact (Decimal context). Stored rounded half up to 6 dp for display only."""
    if net_g <= 0:
        raise RunError("bad_net_weight", "net weight per unit must be positive")
    return require_decimal(bulk_allocated_g, "bulk_allocated_g") / net_g


def stored_expected_units(bulk_allocated_g: Decimal, net_g: Decimal) -> Decimal:
    return expected_units(bulk_allocated_g, net_g).quantize(MASS_DISPLAY, rounding=ROUND_HALF_UP)


def check_allocation(expected_bulk_g: Decimal, allocations: Sequence[Decimal]) -> Decimal:
    """Every pack line gets a positive share; together they may not exceed the expected bulk. Returns unallocated."""
    if not allocations:
        raise RunError("no_pack_lines", "a run needs at least one pack line")
    for a in allocations:
        if require_decimal(a, "bulk_allocated_g") <= 0:
            raise RunError("bad_allocation", "every pack line needs a positive bulk allocation")
        if a != a.quantize(MASS_DISPLAY):
            raise RunError("too_precise", f"bulk allocated {a} g has more than 6 decimal places")
    total = sum(allocations, ZERO)
    if total > expected_bulk_g:
        raise RunError(
            "over_allocated",
            f"pack lines take {_n(total)} g of bulk but the batch makes {_n(expected_bulk_g)} g",
            {"allocated_g": _n(total), "expected_bulk_g": _n(expected_bulk_g)},
        )
    return expected_bulk_g - total


# ---------- the variance engine ----------


def pct_display(pct: Decimal | None) -> Decimal | None:
    return None if pct is None else pct.quantize(PCT_DISPLAY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Variance:
    label: str
    view: str  # PER_BATCH, PER_GOOD_UNIT, BATCH_VIEW, YIELD
    item_id: uuid.UUID | None
    unit: str  # display unit of standard and actual
    standard: Decimal  # display unit
    actual: Decimal  # display unit
    pct: Decimal | None  # exact; None when the standard is zero
    direction: str
    tolerance_pct: Decimal
    beyond_tolerance: bool
    flagged: bool
    explained: Explained
    note: str | None = None
    drives_alert: bool = True  # the batch view of packaging is shown alongside but never drives the alert

    @property
    def pct_display(self) -> Decimal | None:
        return pct_display(self.pct)

    def to_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "view": self.view,
            "item_id": None if self.item_id is None else str(self.item_id),
            "unit": self.unit,
            "standard": _n(self.standard),
            "actual": _n(self.actual),
            "variance_pct": None if self.pct is None else str(self.pct_display),
            "direction": self.direction,
            "tolerance_pct": _n(self.tolerance_pct),
            "beyond_tolerance": self.beyond_tolerance,
            "flagged": self.flagged,
            "drives_alert": self.drives_alert,
            "note": self.note,
            "explained": self.explained.to_json(),
        }


def variance(
    *,
    label: str,
    view: str,
    item_id: uuid.UUID | None,
    unit: str,
    standard: Decimal,
    actual: Decimal,
    tolerance_pct: Decimal,
    higher_is_worse: bool,
    formula: str,
    standard_inputs: Sequence[ExplainedInput] = (),
    source: SourceRef | None = None,
    method: str | None = None,
    drives_alert: bool = True,
    note: str | None = None,
) -> Variance:
    """(actual - standard) / standard x 100, its direction, and the E2 flag (beyond tolerance and unfavourable).

    The comparison uses the exact percentage and is strict, so exactly the tolerance is not flagged. A zero
    standard has no percentage; any actual use against it is beyond tolerance.
    """
    diff = actual - standard
    pct = None if standard == 0 else diff / standard * HUNDRED
    if diff == 0:
        direction = ON_STANDARD
    elif (diff > 0) == higher_is_worse:
        direction = UNFAVOURABLE
    else:
        direction = FAVOURABLE
    beyond = (abs(pct) > tolerance_pct) if pct is not None else diff != 0
    flagged = beyond and direction == UNFAVOURABLE
    explained = Explained(
        value=ZERO if pct is None else pct_display(pct) or ZERO,
        unit="%",
        formula=formula,
        method=method,
        inputs=(
            ExplainedInput("standard", normalise(standard), unit, source),
            ExplainedInput("actual", normalise(actual), unit, source),
            *standard_inputs,
            ExplainedInput("tolerance", normalise(tolerance_pct), "%", source),
        ),
    )
    return Variance(
        label=label,
        view=view,
        item_id=item_id,
        unit=unit,
        standard=standard,
        actual=actual,
        pct=pct,
        direction=direction,
        tolerance_pct=tolerance_pct,
        beyond_tolerance=beyond,
        flagged=flagged and drives_alert,
        explained=explained,
        note=note,
        drives_alert=drives_alert,
    )


USAGE_FORMULA: Final = "(actual - standard) / standard x 100"
YIELD_FORMULA: Final = "(good - expected) / expected x 100"


def ingredient_variances(
    recipe: RecipeStd,
    batch_multiplier: Decimal,
    issued: Mapping[uuid.UUID, Decimal],
    tolerance_pct: Decimal,
    extra_items: Mapping[uuid.UUID, StdLine] | None = None,
    source: SourceRef | None = None,
) -> list[Variance]:
    """PER_BATCH lines against the batch standard. Items issued but not in the recipe are shown with standard 0."""
    out = []
    lines = list(recipe.lines)
    for item_id, line in (extra_items or {}).items():
        if all(ln.item_id != item_id for ln in lines):
            lines.append(line)
    in_recipe = {ln.item_id for ln in recipe.lines}
    for ln in lines:
        std_base = ln.qty_base * batch_multiplier if ln.item_id in in_recipe else ZERO
        actual_base = issued.get(ln.item_id, ZERO)
        u = ln.units
        out.append(
            variance(
                label=ln.item_code,
                view="PER_BATCH",
                item_id=ln.item_id,
                unit=ln.stock_uom,
                standard=from_base(std_base, ln.stock_uom, u),
                actual=from_base(actual_base, ln.stock_uom, u),
                tolerance_pct=ln.tolerance_pct if ln.tolerance_pct is not None else tolerance_pct,
                higher_is_worse=True,
                formula=f"{USAGE_FORMULA}; standard = recipe qty per batch x batch multiplier",
                standard_inputs=(
                    ExplainedInput(
                        "recipe qty per batch", from_base(ln.qty_base, ln.stock_uom, u), ln.stock_uom, source
                    )
                    if ln.item_id in in_recipe
                    else ExplainedInput("not in the recipe", ZERO, ln.stock_uom, source),
                    ExplainedInput("batch multiplier", normalise(batch_multiplier), "x", source),
                ),
                source=source,
                method="batch standard",
            )
        )
    return out


@dataclass(frozen=True)
class Packing:
    full_cartons: int
    loose: int
    units_per_carton: int
    explained: Explained

    def to_json(self) -> dict[str, Any]:
        return {
            "full_cartons": self.full_cartons,
            "loose_units": self.loose,
            "units_per_carton": self.units_per_carton,
            "explained": self.explained.to_json(),
        }


def packing(good_units: int, units_per_carton: int, source: SourceRef | None = None) -> Packing:
    split = split_into_cartons(good_units, units_per_carton)
    return Packing(
        full_cartons=split.full_cartons,
        loose=split.loose,
        units_per_carton=units_per_carton,
        explained=Explained(
            value=Decimal(split.full_cartons),
            unit="carton",
            formula="full cartons, loose = divmod(good units, units per carton)",
            inputs=(
                ExplainedInput("good units", Decimal(good_units), "unit", source),
                ExplainedInput("units per carton", Decimal(units_per_carton), "unit", source),
                ExplainedInput("loose units", Decimal(split.loose), "unit", source),
            ),
        ),
    )


def yield_variance(
    pack: PackStd, bulk_allocated_g: Decimal, good_units: int, tolerance_pct: Decimal, source: SourceRef | None = None
) -> Variance:
    expected = expected_units(bulk_allocated_g, pack.net_g)
    return variance(
        label=f"yield {pack.code}",
        view="YIELD",
        item_id=pack.fg_item_id,
        unit=pack.fg_stock_uom,
        standard=expected,
        actual=Decimal(good_units),
        tolerance_pct=tolerance_pct,
        higher_is_worse=False,
        formula=f"{YIELD_FORMULA}; expected = bulk allocated / net per unit",
        standard_inputs=(
            ExplainedInput("bulk allocated", normalise(bulk_allocated_g), "g", source),
            ExplainedInput("net per unit", normalise(pack.net_g), "g", source),
        ),
        source=source,
        method="yield",
    )


def packaging_variances(
    pack: PackStd,
    bulk_allocated_g: Decimal,
    good_units: int,
    used: Mapping[uuid.UUID, Decimal],
    tolerance_pct: Decimal,
    source: SourceRef | None = None,
) -> list[tuple[Variance, Variance]]:
    """Per packaging line: (flexible standard for the good units made, batch view for the expected units).

    The flexible view drives the alert; the batch view is shown alongside so the difference is visible.
    """
    expected = expected_units(bulk_allocated_g, pack.net_g)
    split = split_into_cartons(good_units, pack.units_per_carton)
    out = []
    for ln in pack.lines:
        u = ln.units
        tol = ln.tolerance_pct if ln.tolerance_pct is not None else tolerance_pct
        actual = from_base(used.get(ln.item_id, ZERO), ln.stock_uom, u)
        per_unit = ExplainedInput("qty per good unit", normalise(ln.qty_base), ln.stock_uom, source)
        flexible = variance(
            label=ln.item_code,
            view="PER_GOOD_UNIT",
            item_id=ln.item_id,
            unit=ln.stock_uom,
            standard=from_base(ln.qty_base * good_units, ln.stock_uom, u),
            actual=actual,
            tolerance_pct=tol,
            higher_is_worse=True,
            formula=f"{USAGE_FORMULA}; standard = qty per good unit x good units",
            standard_inputs=(per_unit, ExplainedInput("good units", Decimal(good_units), pack.fg_stock_uom, source)),
            source=source,
            method="flexible standard",
        )
        if flexible.direction == FAVOURABLE and flexible.beyond_tolerance and pack.is_carton_line(ln) and split.loose:
            flexible = _with_note(flexible, f"{split.loose} loose {pack.fg_stock_uom}s not cartoned")
        batch = variance(
            label=ln.item_code,
            view="BATCH_VIEW",
            item_id=ln.item_id,
            unit=ln.stock_uom,
            standard=from_base(ln.qty_base * expected, ln.stock_uom, u),
            actual=actual,
            tolerance_pct=tol,
            higher_is_worse=True,
            formula=f"{USAGE_FORMULA}; standard = qty per good unit x expected units",
            standard_inputs=(
                per_unit,
                ExplainedInput("expected units", normalise(expected), pack.fg_stock_uom, source),
            ),
            source=source,
            method="batch standard (shown for comparison only)",
            drives_alert=False,
        )
        out.append((flexible, batch))
    return out


def _with_note(v: Variance, note: str) -> Variance:
    return replace(v, note=note)


# ---------- mass balance ----------


def giveaway_g(sample_nets: Sequence[Decimal], declared_net_g: Decimal, good_units: int) -> Decimal | None:
    """(mean sampled net - declared net) x good units, shown to 6 dp. None without samples."""
    if not sample_nets:
        return None
    mean = sum(sample_nets, ZERO) / len(sample_nets)
    return ((mean - declared_net_g) * good_units).quantize(MASS_DISPLAY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PackedMass:
    code: str
    good_units: int
    net_g: Decimal
    giveaway_g: Decimal | None

    @property
    def packed_g(self) -> Decimal:
        return self.net_g * self.good_units


@dataclass(frozen=True)
class MassBalance:
    expected_bulk_g: Decimal
    unallocated_g: Decimal
    good_packed_g: Decimal
    scrap_g: Decimal
    loss_g: Decimal
    unexplained_g: Decimal
    giveaway_g: Decimal | None
    explained: Explained
    lines: tuple[PackedMass, ...] = field(default_factory=tuple)

    @property
    def gap_after_giveaway_g(self) -> Decimal:
        return self.unexplained_g - (self.giveaway_g or ZERO)

    def to_json(self) -> dict[str, Any]:
        def kg(g: Decimal) -> str:
            return _n(g / 1000)

        return {
            "unit": "kg",
            "expected_bulk": kg(self.expected_bulk_g),
            "unallocated_bulk": kg(self.unallocated_g),
            "good_packed": kg(self.good_packed_g),
            "scrap": kg(self.scrap_g),
            "loss": kg(self.loss_g),
            "unexplained_gap": kg(self.unexplained_g),
            "giveaway": None if self.giveaway_g is None else kg(self.giveaway_g),
            "gap_after_giveaway": kg(self.gap_after_giveaway_g),
            "pack_lines": [
                {
                    "pack_spec": p.code,
                    "good_units": p.good_units,
                    "net_g": _n(p.net_g),
                    "packed": kg(p.packed_g),
                    "giveaway": None if p.giveaway_g is None else kg(p.giveaway_g),
                }
                for p in self.lines
            ],
            "explained": self.explained.to_json(),
        }


def mass_balance(
    expected_bulk_g: Decimal,
    unallocated_g: Decimal,
    packed: Sequence[PackedMass],
    scrap_g: Decimal,
    loss_g: Decimal,
    source: SourceRef | None = None,
) -> MassBalance:
    """Law 3: expected bulk = good packed + scrap + loss + unexplained. The gap is shown, never forced to zero."""
    good = sum((p.packed_g for p in packed), ZERO)
    gap = expected_bulk_g - good - scrap_g - loss_g
    gives = [p.giveaway_g for p in packed if p.giveaway_g is not None]
    giveaway = sum(gives, ZERO) if gives else None
    inputs = [
        ExplainedInput("expected bulk", normalise(expected_bulk_g / 1000), "kg", source),
        ExplainedInput("good packed (good units x net)", normalise(good / 1000), "kg", source),
        ExplainedInput("recorded scrap", normalise(scrap_g / 1000), "kg", source),
        ExplainedInput("recorded loss", normalise(loss_g / 1000), "kg", source),
    ]
    if unallocated_g:
        inputs.append(
            ExplainedInput("bulk not allocated to a pack line", normalise(unallocated_g / 1000), "kg", source)
        )
    if giveaway is not None:
        inputs.append(
            ExplainedInput("giveaway (over-filled packs, part of the gap)", normalise(giveaway / 1000), "kg", source)
        )
    return MassBalance(
        expected_bulk_g=expected_bulk_g,
        unallocated_g=unallocated_g,
        good_packed_g=good,
        scrap_g=scrap_g,
        loss_g=loss_g,
        unexplained_g=gap,
        giveaway_g=giveaway,
        lines=tuple(packed),
        explained=Explained(
            value=normalise(gap / 1000),
            unit="kg",
            formula="expected bulk - good packed - scrap - loss",
            method="mass balance",
            inputs=tuple(inputs),
        ),
    )


# ---------- completion ----------


@dataclass(frozen=True)
class IssuedMaterial:
    """What the run holds in WIP for one item: its net issues (issues - returns), at the value they were issued."""

    item_id: uuid.UUID
    base_uom: str
    qty_base: Decimal
    value: Decimal


@dataclass(frozen=True)
class PackagingUse:
    item_id: uuid.UUID
    base_uom: str
    used_base: Decimal  # taken out of PACK_STORE, damaged included
    damaged_base: Decimal
    value: Decimal  # book value of `used_base` at WAC

    @property
    def consumed_base(self) -> Decimal:
        return self.used_base - self.damaged_base


@dataclass(frozen=True)
class PackOutcome:
    pack_line_id: uuid.UUID
    bulk_allocated_g: Decimal
    good_units: int
    fg_item_id: uuid.UUID
    fg_base_uom: str
    lot_id: uuid.UUID | None  # None when there are no good units
    packaging: tuple[PackagingUse, ...]

    def absorbs(self, use: PackagingUse) -> bool:
        """Packaging cost stays in the lot when the line made good units and some of it went into them."""
        return self.good_units > 0 and use.consumed_base > 0


@dataclass(frozen=True)
class CompletionPlan:
    lines: tuple[LineSpec, ...]
    lot_value: dict[uuid.UUID, Decimal]  # pack line -> value of its FG lot (0 when it made nothing)
    ingredient_share: dict[uuid.UUID, Decimal]
    written_off: dict[uuid.UUID, Decimal]  # pack line -> value written off to SCRAP (decision E4)


def split_value(total: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Split rupees by weight, rounded half up to paise; the last share takes the remainder, so the sum is exact."""
    if not weights or any(w <= 0 for w in weights):
        raise RunError("bad_weights", "a value split needs positive weights")
    whole = sum(weights, ZERO)
    shares = [round_money(total * w / whole) for w in weights[:-1]]
    return [*shares, total - sum(shares, ZERO)]


def check_completion(outcomes: Sequence[PackOutcome], scrap_g: Decimal, loss_g: Decimal, reason: str | None) -> None:
    for name, g in (("scrap_g", scrap_g), ("loss_g", loss_g)):
        if require_decimal(g, name) < 0:
            raise RunError("negative_mass", f"{name} cannot be negative")
        if g != g.quantize(MASS_DISPLAY):
            raise RunError("too_precise", f"{name} has more than 6 decimal places")
    needs_reason = scrap_g > 0 or loss_g > 0 or any(o.good_units == 0 for o in outcomes)
    if needs_reason and not (reason or "").strip():
        raise RunError(
            "scrap_reason_required",
            "a reason is required when the run records scrap or loss, or a pack line makes no good units",
        )
    for o in outcomes:
        if isinstance(o.good_units, bool) or not isinstance(o.good_units, int) or o.good_units < 0:
            raise RunError("bad_good_units", "good units must be a whole number, 0 or more")
        for use in o.packaging:
            if use.used_base < 0 or use.damaged_base < 0:
                raise RunError("negative_packaging", "packaging used and damaged cannot be negative")
            if use.damaged_base > use.used_base:
                raise RunError(
                    "damaged_exceeds_used",
                    "damaged packaging is part of what was used, so it cannot be more",
                    {"item_id": str(use.item_id)},
                )


def plan_completion(
    issued: Sequence[IssuedMaterial],
    outcomes: Sequence[PackOutcome],
    *,
    bulk_item_id: uuid.UUID,
    scrap_g: Decimal,
) -> CompletionPlan:
    """The RUN_COMPLETION journal lines. Σ qty = 0 per item and Σ value = 0 by construction (laws 1 and 2)."""
    if not outcomes:
        raise RunError("no_pack_lines", "a run needs at least one pack line")
    if not any(m.qty_base > 0 for m in issued):
        raise RunError("nothing_issued", "nothing has been issued to this run, so there is nothing to complete")
    lines: list[LineSpec] = []
    ingredient_total = ZERO
    for m in issued:
        if m.qty_base == 0:
            continue
        ingredient_total += m.value
        lines += [
            LineSpec(m.item_id, "PRODUCTION", m.qty_base, m.base_uom, m.value),
            LineSpec(m.item_id, "WIP", -m.qty_base, m.base_uom, -m.value),
        ]

    shares = split_value(ingredient_total, [o.bulk_allocated_g for o in outcomes])
    lot_value: dict[uuid.UUID, Decimal] = {}
    written_off: dict[uuid.UUID, Decimal] = {}
    for o, share in zip(outcomes, shares, strict=True):
        absorbed = ZERO
        off = ZERO
        for use in o.packaging:
            if use.used_base == 0:
                continue
            lines.append(LineSpec(use.item_id, "PACK_STORE", -use.used_base, use.base_uom, -use.value))
            if o.absorbs(use):
                absorbed += use.value
                lines.append(LineSpec(use.item_id, "PRODUCTION", use.consumed_base, use.base_uom, use.value))
                if use.damaged_base:
                    lines.append(LineSpec(use.item_id, "SCRAP", use.damaged_base, use.base_uom))  # quantity, no value
            else:
                off += use.value
                lines.append(LineSpec(use.item_id, "SCRAP", use.used_base, use.base_uom, use.value))
        if o.good_units > 0:
            if o.lot_id is None:
                raise RunError("lot_required", "a pack line with good units needs its lot")
            value = share + absorbed
            lines += [
                LineSpec(o.fg_item_id, "FG_STORE", Decimal(o.good_units), o.fg_base_uom, value, o.lot_id),
                LineSpec(o.fg_item_id, "PRODUCTION", -Decimal(o.good_units), o.fg_base_uom, -value, o.lot_id),
            ]
            lot_value[o.pack_line_id] = value
        else:
            off += share  # decision E4: a burnt batch is real; its bulk is written off at its share of the cost
            lines += [
                LineSpec(bulk_item_id, "SCRAP", o.bulk_allocated_g, "g", share),
                LineSpec(bulk_item_id, "PRODUCTION", -o.bulk_allocated_g, "g", -share),
            ]
            lot_value[o.pack_line_id] = ZERO
        written_off[o.pack_line_id] = off
    if scrap_g > 0:  # process waste carries quantity, not value (ADR-0002): its cost stays in the good output
        lines += [LineSpec(bulk_item_id, "SCRAP", scrap_g, "g"), LineSpec(bulk_item_id, "PRODUCTION", -scrap_g, "g")]
    return CompletionPlan(
        lines=tuple(lines),
        lot_value=lot_value,
        ingredient_share={o.pack_line_id: s for o, s in zip(outcomes, shares, strict=True)},
        written_off=written_off,
    )


def returned_value(net_qty: Decimal, net_value: Decimal, return_qty: Decimal) -> Decimal:
    """A return comes back at the run's own issued average, not the shared WIP average; the last unit takes the rest."""
    if return_qty <= 0:
        raise RunError("qty_not_positive", "a return must be for a positive quantity")
    if return_qty > net_qty:
        raise RunError(
            "return_exceeds_issued",
            f"only {_n(net_qty)} was issued to this run; {_n(return_qty)} cannot come back",
            {"issued": _n(net_qty), "requested": _n(return_qty)},
        )
    if return_qty == net_qty:
        return net_value
    return round_money(return_qty * net_value / net_qty)


# ---------- run costs: the value-only true-up (ADR-0004, ADR-0014 decisions F1, F2) ----------

RUN_COST_KINDS: Final = ("LABOUR", "GAS_POWER", "OTHER")
ON_HAND: Final = "FG_STORE"


@dataclass(frozen=True)
class LotPosition:
    location: str
    qty_base: Decimal
    value: Decimal


@dataclass(frozen=True)
class LotState:
    """One pack line of a completed run, as the ledger holds it now."""

    pack_line_id: uuid.UUID
    bulk_allocated_g: Decimal
    item_id: uuid.UUID  # the FG item (or, for a pack line with no good units, unused)
    base_uom: str
    lot_id: uuid.UUID | None  # None when the pack line made no good units
    positions: tuple[LotPosition, ...] = ()  # where the lot's units are now (qty > 0), e.g. FG_STORE, CUSTOMER

    @property
    def qty(self) -> Decimal:
        return sum((p.qty_base for p in self.positions), ZERO)

    @property
    def value(self) -> Decimal:
        return sum((p.value for p in self.positions), ZERO)


@dataclass(frozen=True)
class TrueUpPlan:
    lines: tuple[LineSpec, ...]
    share: dict[uuid.UUID, Decimal]  # pack line -> its part of this cost
    written_off: dict[uuid.UUID, Decimal]  # pack line -> part sent to SCRAP (no good units)


def check_run_cost(kind: str, amount: Decimal) -> Decimal:
    if kind not in RUN_COST_KINDS:
        raise RunError("bad_cost_kind", f"run cost kind must be one of {', '.join(RUN_COST_KINDS)}")
    money = require_decimal(amount, "amount")
    if money <= 0:
        raise RunError("amount_not_positive", "a run cost must be positive")
    if money != money.quantize(PCT_DISPLAY):
        raise RunError("amount_not_rounded", "a run cost is rupees with at most 2 decimal places")
    return money


def plan_true_up(amount: Decimal, lots: Sequence[LotState], *, bulk_item_id: uuid.UUID) -> TrueUpPlan:
    """Spread one direct run cost over the run's lots (value only, quantities untouched).

    - Each pack line's share is by bulk allocated; the last line takes the rounding remainder.
    - Within a lot the spread is cumulative (ledger.md J8): the lot's new total = what it holds + its share; each
      position that holds units gets round(qty / lot qty x new total) - what it already holds; FG_STORE (on hand)
      takes the remainder, or the last position when nothing is on hand. Two true-ups end where one would.
    - A pack line with no good units sends its share to SCRAP on the bulk item (decision E4).
    Σ value = 0 by construction: every share leaves CONVERSION_COST and lands somewhere.
    """
    if not lots:
        raise RunError("no_pack_lines", "a run needs at least one pack line")
    shares = split_value(amount, [lot.bulk_allocated_g for lot in lots])
    lines: list[LineSpec] = []
    written_off: dict[uuid.UUID, Decimal] = {}
    for lot, share in zip(lots, shares, strict=True):
        written_off[lot.pack_line_id] = ZERO
        if share == 0:
            continue
        held = [p for p in lot.positions if p.qty_base > 0]
        if lot.lot_id is None or not held:
            written_off[lot.pack_line_id] = share
            lines += [
                LineSpec(bulk_item_id, "SCRAP", ZERO, "g", share),
                LineSpec(bulk_item_id, "CONVERSION_COST", ZERO, "g", -share),
            ]
            continue
        lot_qty = sum((p.qty_base for p in held), ZERO)
        target = sum((p.value for p in held), ZERO) + share
        remainder_at = next((p for p in held if p.location == ON_HAND), held[-1])
        deltas: dict[str, Decimal] = {}
        for p in held:
            if p is not remainder_at:
                deltas[p.location] = round_money(p.qty_base * target / lot_qty) - p.value
        deltas[remainder_at.location] = share - sum(deltas.values(), ZERO)
        for location, delta in deltas.items():
            if delta != 0:
                lines.append(LineSpec(lot.item_id, location, ZERO, lot.base_uom, delta, lot.lot_id))
        lines.append(LineSpec(lot.item_id, "CONVERSION_COST", ZERO, lot.base_uom, -share, lot.lot_id))
    return TrueUpPlan(
        lines=tuple(lines),
        share={lot.pack_line_id: s for lot, s in zip(lots, shares, strict=True)},
        written_off=written_off,
    )


# ---------- what costing reads about a completed run (MP07) ----------


@dataclass(frozen=True)
class IssueMove:
    journal_id: uuid.UUID
    direction: str  # ISSUE, RETURN, or ISSUE for packaging taken at completion
    qty_base: Decimal
    value: Decimal


@dataclass(frozen=True)
class MaterialFacts:
    item_id: uuid.UUID
    item_code: str
    role: str  # INGREDIENT (issued to WIP) or PACKAGING (taken at completion)
    base_uom: str
    stock_uom: str
    qty_base: Decimal  # net issued, or used (damaged included)
    value: Decimal  # at book value (WAC)
    moves: tuple[IssueMove, ...]


@dataclass(frozen=True)
class ConversionFacts:
    run_cost_id: uuid.UUID
    kind: str
    amount: Decimal
    incurred_on: date
    journal_id: uuid.UUID | None


@dataclass(frozen=True)
class PackFacts:
    pack_line_id: uuid.UUID
    pack: PackStd
    bulk_allocated_g: Decimal
    good_units: int
    used: dict[uuid.UUID, Decimal]  # packaging item -> base qty used, damaged included
    damaged: dict[uuid.UUID, Decimal]
    lot_id: uuid.UUID | None
    lot_no: str | None
    lot_qty: Decimal  # units of the lot wherever they are now (on hand, in transit, sold)
    lot_value: Decimal


@dataclass(frozen=True)
class RunCostingFacts:
    run_id: uuid.UUID
    run_no: str
    cost_status: str
    run_date: date
    batch_multiplier: Decimal
    recipe: RecipeStd
    packs: tuple[PackFacts, ...]
    materials: tuple[MaterialFacts, ...]
    conversion: tuple[ConversionFacts, ...]
    completion_journal_id: uuid.UUID
    written_off: Decimal  # value the completion and true-ups sent to SCRAP (decision E4)
