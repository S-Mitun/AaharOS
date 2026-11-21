"""Pure recipe and pack-spec rules (MP06, ADR-0003, ADR-0013). No database.

- A **recipe version** makes BULK per batch: ingredient lines (RAW items) with driver PER_BATCH, quantities in the
  item's base unit (g, mL), and a bulk yield in grams.
- A **pack spec version** packs bulk per good unit: net grams per unit, units per carton, shelf life, and
  packaging lines (PACK items) with driver PER_GOOD_UNIT, quantity per good unit in the item's base unit.
- Versions move DRAFT -> ACTIVE -> RETIRED. Activating a version retires the version that was ACTIVE. Lines are
  frozen by the database once a version leaves DRAFT, and only ACTIVE versions can start a run, so a version used by
  a run can never change (bom.md section 5).
- `recipe_snapshot` / `pack_snapshot` turn a version into the plain JSON a run freezes. Decimals become strings.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final

from app.core.errors import DomainError
from app.modules.uom.domain import QTY_PLACES, ItemUnits, normalise, require_decimal, to_base

PER_BATCH: Final = "PER_BATCH"
PER_GOOD_UNIT: Final = "PER_GOOD_UNIT"
DRAFT: Final = "DRAFT"
ACTIVE: Final = "ACTIVE"
RETIRED: Final = "RETIRED"
_QTY_STEP: Final = Decimal(1).scaleb(-QTY_PLACES)
_PCT_STEP: Final = Decimal("0.0001")  # NUMERIC(9,4)


class RecipeError(DomainError):
    """A recipe or pack spec the books refuse."""


@dataclass(frozen=True)
class RecipeLineIn:
    item_id: uuid.UUID
    qty: Decimal  # per batch, in `unit`
    unit: str
    tolerance_pct: Decimal | None = None  # overrides the organization's variance tolerance for this line


@dataclass(frozen=True)
class PackLineIn:
    item_id: uuid.UUID
    qty_per_good_unit: Decimal  # in the item's base unit (pieces); may be a fraction, e.g. 0.05 carton per packet
    tolerance_pct: Decimal | None = None


@dataclass(frozen=True)
class RecipeLinePlan:
    item_id: uuid.UUID
    qty_base: Decimal
    tolerance_pct: Decimal | None


def _tolerance(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    pct = require_decimal(value, "tolerance_pct")
    if pct < 0 or pct > 100 or pct != pct.quantize(_PCT_STEP):
        raise RecipeError("bad_tolerance", "a tolerance is a percentage from 0 to 100 with at most 4 decimals")
    return pct


def _positive_qty(value: Decimal, what: str) -> Decimal:
    qty = require_decimal(value, what)
    if qty <= 0:
        raise RecipeError("qty_not_positive", f"{what} must be positive")
    if qty != qty.quantize(_QTY_STEP):
        raise RecipeError("too_precise", f"{what} {qty} has more than {QTY_PLACES} decimal places")
    return qty


def _no_duplicates(item_ids: Sequence[uuid.UUID]) -> None:
    if len(set(item_ids)) != len(item_ids):
        raise RecipeError("duplicate_item", "an item may appear only once in a version")


def plan_recipe_lines(
    lines: Sequence[RecipeLineIn], items: Mapping[uuid.UUID, tuple[ItemUnits, str]]
) -> list[RecipeLinePlan]:
    """Ingredient lines in base units. Only RAW items; at least one line; each item once."""
    if not lines:
        raise RecipeError("no_lines", "a recipe version needs at least one ingredient")
    _no_duplicates([ln.item_id for ln in lines])
    out = []
    for ln in lines:
        found = items.get(ln.item_id)
        if found is None:
            raise RecipeError("unknown_item", "unknown item", {"item_id": str(ln.item_id)})
        units, kind = found
        if kind != "RAW":
            raise RecipeError("not_an_ingredient", f"recipe lines take raw materials, not {kind} items")
        qty_base = to_base(_positive_qty(ln.qty, "qty"), ln.unit, units)
        out.append(RecipeLinePlan(ln.item_id, qty_base, _tolerance(ln.tolerance_pct)))
    return out


def plan_pack_lines(lines: Sequence[PackLineIn], kinds: Mapping[uuid.UUID, str]) -> list[PackLineIn]:
    """Packaging lines: PACK items only, a positive quantity per good unit (6 dp at most), each item once."""
    if not lines:
        raise RecipeError("no_lines", "a pack spec version needs at least one packaging line")
    _no_duplicates([ln.item_id for ln in lines])
    out = []
    for ln in lines:
        kind = kinds.get(ln.item_id)
        if kind is None:
            raise RecipeError("unknown_item", "unknown item", {"item_id": str(ln.item_id)})
        if kind != "PACK":
            raise RecipeError("not_packaging", f"pack spec lines take packaging items, not {kind} items")
        out.append(
            PackLineIn(
                ln.item_id, _positive_qty(ln.qty_per_good_unit, "qty_per_good_unit"), _tolerance(ln.tolerance_pct)
            )
        )
    return out


def check_pack_header(net_g: Decimal, units_per_carton: int, shelf_life_days: int) -> None:
    _positive_qty(net_g, "net_g")
    for name, n in (("units_per_carton", units_per_carton), ("shelf_life_days", shelf_life_days)):
        if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
            raise RecipeError("bad_pack_header", f"{name} must be a positive whole number")


def check_bulk_yield(bulk_yield_g: Decimal) -> Decimal:
    return _positive_qty(bulk_yield_g, "bulk_yield_g")


def check_activation(status: str, line_count: int) -> None:
    if status != DRAFT:
        raise RecipeError("not_draft", f"only a DRAFT version can be activated; this one is {status}")
    if line_count == 0:
        raise RecipeError("no_lines", "a version with no lines cannot be activated")


# ---------- snapshots (what a run freezes) ----------


def _s(d: Decimal | None) -> str | None:
    return None if d is None else str(normalise(d))


@dataclass(frozen=True)
class SnapshotLine:
    item_id: uuid.UUID
    item_code: str
    base_uom: str
    stock_uom: str
    qty_base: Decimal  # per batch (recipe) or per good unit (pack spec)
    driver: str
    tolerance_pct: Decimal | None

    def to_json(self) -> dict[str, Any]:
        return {
            "item_id": str(self.item_id),
            "item_code": self.item_code,
            "base_uom": self.base_uom,
            "stock_uom": self.stock_uom,
            "qty_base": _s(self.qty_base),
            "driver": self.driver,
            "tolerance_pct": _s(self.tolerance_pct),
        }


def recipe_snapshot(
    *,
    recipe_id: uuid.UUID,
    code: str,
    name: str,
    version_id: uuid.UUID,
    version: int,
    effective_from: date,
    bulk_item_id: uuid.UUID,
    bulk_item_code: str,
    bulk_yield_g: Decimal,
    lines: Sequence[SnapshotLine],
) -> dict[str, Any]:
    return {
        "recipe_id": str(recipe_id),
        "code": code,
        "name": name,
        "version_id": str(version_id),
        "version": version,
        "effective_from": effective_from.isoformat(),
        "bulk_item_id": str(bulk_item_id),
        "bulk_item_code": bulk_item_code,
        "bulk_yield_g": _s(bulk_yield_g),
        "lines": [ln.to_json() for ln in lines],
    }


def pack_snapshot(
    *,
    pack_spec_id: uuid.UUID,
    code: str,
    name: str,
    version_id: uuid.UUID,
    version: int,
    effective_from: date,
    recipe_id: uuid.UUID,
    fg_item_id: uuid.UUID,
    fg_item_code: str,
    fg_stock_uom: str,
    net_g: Decimal,
    units_per_carton: int,
    shelf_life_days: int,
    lines: Sequence[SnapshotLine],
) -> dict[str, Any]:
    return {
        "pack_spec_id": str(pack_spec_id),
        "code": code,
        "name": name,
        "version_id": str(version_id),
        "version": version,
        "effective_from": effective_from.isoformat(),
        "recipe_id": str(recipe_id),
        "fg_item_id": str(fg_item_id),
        "fg_item_code": fg_item_code,
        "fg_stock_uom": fg_stock_uom,
        "net_g": _s(net_g),
        "units_per_carton": units_per_carton,
        "shelf_life_days": shelf_life_days,
        "lines": [ln.to_json() for ln in lines],
    }
