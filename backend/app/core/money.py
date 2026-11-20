"""Money and quantity rounding rules (CLAUDE.md golden rules).

Money is Decimal, rounded only at posting, ROUND_HALF_UP to paise. Unit costs keep 6 dp.
Floats are rejected so they can never leak into a money path.
"""

from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")
UNIT_COST = Decimal("0.000001")


def _require_decimal(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"expected Decimal, got {type(value).__name__}")
    return value


def round_money(value: Decimal) -> Decimal:
    """Round a rupee amount to paise, half up."""
    return _require_decimal(value).quantize(PAISE, rounding=ROUND_HALF_UP)


def round_unit_cost(value: Decimal) -> Decimal:
    """Round a per-unit cost to 6 decimal places, half up."""
    return _require_decimal(value).quantize(UNIT_COST, rounding=ROUND_HALF_UP)


def to_paise(value: Decimal) -> int:
    """Convert a rupee amount to integer paise after rounding."""
    return int(round_money(value) * 100)
