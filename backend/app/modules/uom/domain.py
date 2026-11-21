"""Pure unit rules (MP04). No database.

- Every quantity the ledger stores is in the item's base unit: g (MASS), mL (VOLUME) or piece (COUNT).
- Converting *to* the base unit only multiplies, so it is exact. A result with more than 6 decimal places is refused
  (the ledger stores NUMERIC(18,6) and quantities are never rounded).
- Converting *back* to a larger unit is for display only.
- Packet and carton are COUNT units. A carton has no global size: its factor comes from the pack spec version
  (`units_per_carton`), so a 500 g pack with 12 per carton needs no code change.
- MASS <-> VOLUME needs an explicit density for that item (`uom_conversions.item_id`), stored as "base units of the
  item per base unit of the other dimension", so it is a multiplication too.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.core.errors import DomainError

MASS: Final = "MASS"
VOLUME: Final = "VOLUME"
COUNT: Final = "COUNT"
DIMENSIONS: Final = (MASS, VOLUME, COUNT)
BASE_UNIT: Final = {MASS: "g", VOLUME: "mL", COUNT: "piece"}

CARTON: Final = "carton"
"""A COUNT packing unit whose size is set per pack spec version, never globally."""

QTY_PLACES: Final = 6
"""Quantities are NUMERIC(18,6) in base units."""


class UomError(DomainError):
    """A quantity or conversion that the ledger cannot represent exactly."""


@dataclass(frozen=True)
class Unit:
    code: str
    dimension: str
    to_base: Decimal  # 1 of this unit = to_base base units


# Mirrors the seed in migration 0005; tests/db/test_uom.py keeps the two equal.
SYSTEM_UNITS: Final[dict[str, Unit]] = {
    u.code: u
    for u in (
        Unit("g", MASS, Decimal(1)),
        Unit("kg", MASS, Decimal(1000)),
        Unit("mL", VOLUME, Decimal(1)),
        Unit("L", VOLUME, Decimal(1000)),
        Unit("piece", COUNT, Decimal(1)),
        Unit("packet", COUNT, Decimal(1)),
    )
}


@dataclass(frozen=True)
class ItemUnits:
    """What the ledger needs to know about an item's units."""

    base_uom: str  # g, mL or piece
    stock_uom: str  # the unit people count in: kg, L, piece, packet
    lot_tracked: bool = False
    density: Decimal | None = None  # item base units per base unit of the other dimension (MASS <-> VOLUME only)

    @property
    def dimension(self) -> str:
        return unit(self.base_uom).dimension


def require_decimal(value: object, what: str = "quantity") -> Decimal:
    """Decimal only. Floats are refused so they can never reach a quantity or money path."""
    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        raise UomError("not_decimal", f"{what} must be a Decimal, got {type(value).__name__}", {"what": what})
    result = Decimal(value)
    if not result.is_finite():
        raise UomError("not_finite", f"{what} must be a finite number", {"what": what})
    return result


def unit(code: str) -> Unit:
    found = SYSTEM_UNITS.get(code)
    if found is None:
        raise UomError("unknown_unit", f"unknown unit {code!r}", {"unit": code})
    return found


_QTY_STEP: Final = Decimal(1).scaleb(-QTY_PLACES)


def _check_places(qty_base: Decimal, base_uom: str) -> Decimal:
    if qty_base != qty_base.quantize(_QTY_STEP):  # by value: 0.000001000 is fine, 0.0000001 is not
        raise UomError(
            "too_precise",
            f"{qty_base} {base_uom} has more than {QTY_PLACES} decimal places; quantities are never rounded",
            {"qty_base": str(qty_base)},
        )
    if unit(base_uom).dimension == COUNT and qty_base != qty_base.to_integral_value():
        raise UomError("fractional_count", f"{qty_base} {base_uom} is not a whole number", {"qty_base": str(qty_base)})
    return qty_base


def to_base(qty: Decimal, unit_code: str, item: ItemUnits, *, units_per_carton: int | None = None) -> Decimal:
    """Convert a quantity in `unit_code` to the item's base unit. Exact: multiplication only."""
    qty = require_decimal(qty)
    target = unit(item.base_uom)
    if unit_code == CARTON:
        if target.dimension != COUNT:
            raise UomError("carton_needs_count_item", "cartons convert only for items counted in pieces")
        if units_per_carton is None or isinstance(units_per_carton, bool) or units_per_carton <= 0:
            raise UomError(
                "carton_needs_pack_spec",
                "carton size comes from the pack spec version (units_per_carton); none was given",
            )
        return _check_places(qty * units_per_carton, item.base_uom)
    source = unit(unit_code)
    in_source_base = qty * source.to_base
    if source.dimension == target.dimension:
        return _check_places(in_source_base, item.base_uom)
    if {source.dimension, target.dimension} == {MASS, VOLUME}:
        if item.density is None:
            raise UomError(
                "cross_dimension",
                f"cannot convert {source.dimension} ({unit_code}) to {target.dimension} ({item.base_uom})"
                " without a density for this item",
                {"from": unit_code, "to": item.base_uom},
            )
        return _check_places(in_source_base * item.density, item.base_uom)
    raise UomError(
        "cross_dimension",
        f"cannot convert {source.dimension} ({unit_code}) to {target.dimension} ({item.base_uom})",
        {"from": unit_code, "to": item.base_uom},
    )


def from_base(qty_base: Decimal, unit_code: str, item: ItemUnits, *, units_per_carton: int | None = None) -> Decimal:
    """Display only: a base quantity in a larger unit of the same dimension (120000 g -> 120 kg)."""
    qty_base = require_decimal(qty_base)
    if unit_code == CARTON:
        if units_per_carton is None or units_per_carton <= 0:
            raise UomError("carton_needs_pack_spec", "carton size comes from the pack spec version")
        return normalise(qty_base / units_per_carton)
    target = unit(unit_code)
    if target.dimension != item.dimension:
        raise UomError(
            "cross_dimension",
            f"display of {item.base_uom} in {unit_code} is a cross-dimension conversion",
            {"from": item.base_uom, "to": unit_code},
        )
    return normalise(qty_base / target.to_base)


def normalise(value: Decimal) -> Decimal:
    """Drop trailing zeros without switching to exponent notation (120.000 -> 120, 19.500 -> 19.5)."""
    if value == value.to_integral_value():
        return value.quantize(Decimal(1))
    return value.normalize()


@dataclass(frozen=True)
class CartonSplit:
    full_cartons: int
    loose: int


def split_into_cartons(units: Decimal | int, units_per_carton: int) -> CartonSplit:
    """188 packets at 20 per carton -> 9 cartons + 8 loose. Counted items only, so this is integer divmod."""
    count = require_decimal(units)
    if count != count.to_integral_value() or count < 0:
        raise UomError("fractional_count", f"{count} is not a whole, non-negative number of units")
    if isinstance(units_per_carton, bool) or not isinstance(units_per_carton, int) or units_per_carton <= 0:
        raise UomError("carton_needs_pack_spec", "units_per_carton must be a positive whole number")
    full, loose = divmod(int(count), units_per_carton)
    return CartonSplit(full_cartons=full, loose=loose)
