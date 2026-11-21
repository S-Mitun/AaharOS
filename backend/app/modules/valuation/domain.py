"""Pure valuation rules (MP05, ADR-0004, ADR-0012). No database.

- **Book method: moving weighted average (WAC).** The pool is an item's (qty, value) over its pool stores. An issue
  takes round_half_up(qty / pool_qty x pool_value) to paise; the last unit out takes exactly what is left, so the
  pool drains to ₹0.00 and never drifts. No rounded unit cost is ever multiplied back.
- **Sensitivity only: FIFO and LAST** (last purchase price). They replay the item's pool history and never post.
- Every method answers the same question through one interface: what would issuing `qty` now be valued at?
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Protocol

from app.core.errors import DomainError
from app.core.money import round_money, round_unit_cost
from app.modules.uom.domain import require_decimal

ZERO: Final = Decimal(0)

# Raw and packaging stock is pooled across these stores. WIP holds what a run has been issued (valued at issue);
# finished goods are valued per lot (ADR-0005), never pooled.
POOL_LOCATIONS: Final = ("RAW_STORE", "PACK_STORE")

BOOK_METHOD: Final = "WAC"
SENSITIVITY_METHODS: Final = ("FIFO", "LAST")


class ValuationError(DomainError):
    """A valuation the books cannot make."""


@dataclass(frozen=True)
class Pool:
    qty_base: Decimal
    value: Decimal

    @property
    def empty(self) -> bool:
        return self.qty_base == 0


def proportional_value(pool: Pool, qty_base: Decimal) -> Decimal:
    """Value of `qty_base` taken out of `pool`: proportional, and the last unit takes the rest (exact drain)."""
    qty = require_decimal(qty_base)
    if qty <= 0:
        raise ValuationError("qty_not_positive", "an issue must be for a positive quantity")
    if pool.qty_base <= 0:
        raise ValuationError("pool_empty", "there is no stock to value this issue from", {"requested": str(qty)})
    if qty > pool.qty_base:
        raise ValuationError(
            "pool_short",
            f"only {pool.qty_base} is in stock; {qty} was requested",
            {"available": str(pool.qty_base), "requested": str(qty)},
        )
    if qty == pool.qty_base:
        return pool.value
    return round_money(qty * pool.value / pool.qty_base)


def unit_cost(pool: Pool, base_per_unit: Decimal) -> Decimal | None:
    """Average cost per display unit (₹/kg when base_per_unit = 1000 g), to 6 dp. Display only; None if empty."""
    if pool.qty_base <= 0:
        return None
    return round_unit_cost(pool.value * base_per_unit / pool.qty_base)


def line_value(qty: Decimal, rate: Decimal) -> Decimal:
    """Receipt and opening value: quantity in the rate's unit x rate, rounded once to paise."""
    q, r = require_decimal(qty), require_decimal(rate, "rate")
    if q < 0 or r < 0:
        raise ValuationError("negative_value", "quantity and rate must not be negative")
    return round_money(q * r)


# ---------- the pool history and the three methods ----------


@dataclass(frozen=True)
class Movement:
    """One change to an item's pool, in posting order. `key` identifies the journal; `reverses` its original."""

    qty_base: Decimal  # > 0 into the pool, < 0 out of it
    value: Decimal
    kind: str  # journal kind: OPENING, RECEIPT, ISSUE, RETURN, ADJUSTMENT, REVERSAL, ...
    key: str = ""
    reverses: str | None = None


def replay_pool(history: Sequence[Movement]) -> Pool:
    qty, value = ZERO, ZERO
    for m in history:
        qty, value = qty + m.qty_base, value + m.value
    return Pool(qty, value)


@dataclass(frozen=True)
class Layer:
    key: str
    qty_base: Decimal
    value: Decimal  # the layer's remaining value; unit cost = value / qty, never rounded


def fifo_layers(history: Sequence[Movement]) -> list[Layer]:
    """FIFO layers after replaying the history: every inflow is a layer; outflows consume the oldest first.

    A reversal of an inflow removes that inflow's own layer first (a returned delivery is not "the oldest flour").
    """
    layers: list[Layer] = []
    for m in history:
        if m.qty_base > 0:
            layers.append(Layer(m.key, m.qty_base, m.value))
            continue
        if m.qty_base == 0:
            continue
        need = -m.qty_base
        if m.reverses is not None:
            for i, layer in enumerate(layers):
                if layer.key == m.reverses:
                    take = min(need, layer.qty_base)
                    layers[i] = _shrink(layer, take)
                    need -= take
                    break
        layers, _ = _consume(layers, need)
    return [layer for layer in layers if layer.qty_base > 0]


def _shrink(layer: Layer, take: Decimal) -> Layer:
    if take >= layer.qty_base:
        return Layer(layer.key, ZERO, ZERO)
    taken_value = layer.value * take / layer.qty_base
    return Layer(layer.key, layer.qty_base - take, layer.value - taken_value)


def _consume(layers: list[Layer], need: Decimal) -> tuple[list[Layer], Decimal]:
    """Take `need` from the oldest layers. Returns the remaining layers and the unrounded value taken."""
    out: list[Layer] = []
    taken = ZERO
    for layer in layers:
        if need > 0 and layer.qty_base > 0:
            take = min(need, layer.qty_base)
            taken += layer.value if take == layer.qty_base else layer.value * take / layer.qty_base
            layer = _shrink(layer, take)
            need -= take
        out.append(layer)
    return out, taken


class ValuationMethod(Protocol):
    name: str
    posts: bool  # only the book method's values are ever posted

    def issue_value(self, history: Sequence[Movement], qty_base: Decimal) -> Decimal: ...


class WeightedAverage:
    name = "WAC"
    posts = True

    def issue_value(self, history: Sequence[Movement], qty_base: Decimal) -> Decimal:
        return proportional_value(replay_pool(history), qty_base)


class Fifo:
    name = "FIFO"
    posts = False

    def issue_value(self, history: Sequence[Movement], qty_base: Decimal) -> Decimal:
        layers = fifo_layers(history)
        available = sum((layer.qty_base for layer in layers), ZERO)
        qty = require_decimal(qty_base)
        if qty <= 0 or qty > available:
            raise ValuationError("pool_short", "not enough FIFO layers for this quantity", {"requested": str(qty)})
        _, taken = _consume(layers, qty)
        return round_money(taken)


class LastPrice:
    """Last purchase price: the most recent receipt's unit cost x qty. Not a recognised inventory method."""

    name = "LAST"
    posts = False

    def issue_value(self, history: Sequence[Movement], qty_base: Decimal) -> Decimal:
        receipts = [m for m in history if m.kind == "RECEIPT" and m.qty_base > 0]
        if not receipts:
            raise ValuationError("no_receipt", "no purchase receipt yet, so there is no last price")
        last = receipts[-1]
        return round_money(require_decimal(qty_base) * last.value / last.qty_base)


METHODS: Final[dict[str, ValuationMethod]] = {m.name: m for m in (WeightedAverage(), Fifo(), LastPrice())}


def gain_value(history: Sequence[Movement], qty_base: Decimal) -> tuple[Decimal, str]:
    """Value of stock found in a count: at the current WAC; at the last receipt price when the pool is empty;
    ₹0 (and said so) when the item was never bought. Returns (value, basis)."""
    qty = require_decimal(qty_base)
    pool = replay_pool(history)
    if pool.qty_base > 0:
        return round_money(qty * pool.value / pool.qty_base), "WAC"
    try:
        return LastPrice().issue_value(history, qty), "LAST"
    except ValuationError:
        return ZERO, "NO_COST_YET"
