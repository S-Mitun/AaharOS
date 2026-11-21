"""Pure order-taking rules (MP08, ADR-0015). No database.

- G1 Prices come from the server's price list, never from the phone. The price in force for a customer on a date is
  its customer-specific list if one is in force, else the general list's highest version in force. The phone sends
  the version it showed and the price per line; any line whose price differs from that version is refused
  (`price_mismatch`). If the version shown is no longer the one in force when the order arrives, the order is accepted
  and flagged **stale**.
- G2 Orders are in whole packets: each line a positive integer, each item once.
- G3 Numbers: `SO/26-27/000001`, gapless per financial year, given when the factory receives the order.
- G4 The idempotency request hash covers what the order means, independent of line order.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final

from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money

DOC_TYPE: Final = "SO"
MAX_LINES: Final = 100
MAX_PACKETS_PER_LINE: Final = 1_000_000


class OrderError(DomainError):
    """An order the factory refuses."""


@dataclass(frozen=True)
class PriceListVersion:
    id: uuid.UUID
    code: str
    version: int
    customer_id: uuid.UUID | None
    effective_from: date
    effective_to: date | None
    created_at: datetime | None = None

    def in_force_on(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on <= self.effective_to)


def price_list_in_force(
    versions: Sequence[PriceListVersion],
    customer_id: uuid.UUID,
    on: date,
    known_at: datetime | None = None,
) -> PriceListVersion | None:
    """The version that prices this customer's order on `on`: the customer's own list if one is in force, else the
    general list's highest version in force. `known_at` ignores versions published after that instant, so the
    answer for an order received earlier never changes when a later version is published."""

    def candidates(own: bool) -> list[PriceListVersion]:
        return [
            v
            for v in versions
            if v.in_force_on(on)
            and (v.customer_id == customer_id if own else v.customer_id is None)
            and (known_at is None or v.created_at is None or v.created_at <= known_at)
        ]

    for own in (True, False):
        found = candidates(own)
        if found:
            return max(found, key=lambda v: (v.effective_from, v.version))
    return None


@dataclass(frozen=True)
class OrderLineIn:
    item_id: uuid.UUID
    qty: int  # whole packets
    price: Decimal  # ex tax, per packet, as the phone showed it


@dataclass(frozen=True)
class OrderLinePlan:
    line_no: int
    item_id: uuid.UUID
    qty: int
    price: Decimal  # from the price list version, never from the phone

    @property
    def value(self) -> Decimal:
        return round_money(self.price * self.qty)


def plan_order(lines: Sequence[OrderLineIn], list_prices: Mapping[uuid.UUID, Decimal]) -> list[OrderLinePlan]:
    """Check the lines against the price list version the phone showed. Returns the lines to store."""
    if not lines:
        raise OrderError("empty_order", "an order needs at least one product")
    if len(lines) > MAX_LINES:
        raise OrderError("too_many_lines", f"an order holds at most {MAX_LINES} products")
    seen: set[uuid.UUID] = set()
    plan: list[OrderLinePlan] = []
    for n, line in enumerate(lines, start=1):
        if isinstance(line.qty, bool) or not isinstance(line.qty, int):
            raise OrderError("whole_packets_only", "order quantities are whole packets")
        if line.qty <= 0:
            raise OrderError("qty_not_positive", "each product needs at least one packet", {"line": n})
        if line.qty > MAX_PACKETS_PER_LINE:
            raise OrderError("qty_too_large", "this quantity is not plausible for one order", {"line": n})
        if line.item_id in seen:
            raise OrderError("duplicate_item", "each product appears once per order", {"item_id": str(line.item_id)})
        seen.add(line.item_id)
        if not isinstance(line.price, Decimal):
            raise TypeError("prices are Decimals")
        listed = list_prices.get(line.item_id)
        if listed is None:
            raise OrderError(
                "item_not_on_price_list",
                "this product is not on the price list the phone showed",
                {"item_id": str(line.item_id)},
            )
        if line.price != listed:
            raise OrderError(
                "price_mismatch",
                "the price sent does not match the factory's price list",
                {"item_id": str(line.item_id), "sent": str(line.price), "price_list": str(listed)},
            )
        plan.append(OrderLinePlan(n, line.item_id, line.qty, listed))
    return plan


def order_total(
    lines: Sequence[tuple[str, int, Decimal]], source: SourceRef | None = None, label: str = "Order value ex-tax"
) -> Explained:
    """Σ packets x price ex-tax, exactly (each product's (name, packets, price)). GST is added at invoicing (MP10)."""
    total = round_money(sum((Decimal(qty) * price for _, qty, price in lines), Decimal(0)))
    inputs: list[ExplainedInput] = []
    for name, qty, price in lines:
        inputs.append(ExplainedInput(f"{name}: packets", Decimal(qty), "packets", source))
        inputs.append(ExplainedInput(f"{name}: price ex-tax", price, "INR/packet", source))
    return Explained(
        value=total,
        unit="INR",
        formula="Σ (packets x price ex-tax)",
        inputs=tuple(inputs),
        method=label,
    )


def is_stale(shown: uuid.UUID, in_force: PriceListVersion | None) -> bool:
    """True when the version the phone showed is not the one in force when the factory received the order."""
    return in_force is None or in_force.id != shown


def request_doc(
    customer_id: uuid.UUID, price_list_id: uuid.UUID, plan: Sequence[OrderLinePlan], captured_at: datetime | None
) -> dict[str, Any]:
    """What the order means, for the idempotency hash: the same products in any order hash alike."""
    return {
        "kind": "sales_order",
        "customer_id": customer_id,
        "price_list_id": price_list_id,
        "captured_at": None if captured_at is None else captured_at.isoformat(),
        "lines": sorted(([str(p.item_id), p.qty, p.price] for p in plan), key=lambda x: str(x[0])),
    }


def order_no(fy: str, number: int) -> str:
    if number < 1:
        raise ValueError("document numbers start at 1")
    return f"SO/{fy}/{number:06d}"


def check_new_price_list(items: Mapping[uuid.UUID, Decimal], fg_items: set[uuid.UUID]) -> None:
    """A new price list version: at least one product, finished goods only, prices ≥ 0 in whole paise."""
    if not items:
        raise OrderError("empty_price_list", "a price list needs at least one product")
    for item_id, price in items.items():
        if item_id not in fg_items:
            raise OrderError(
                "not_a_finished_good", "only finished goods are sold from a price list", {"item_id": str(item_id)}
            )
        if not isinstance(price, Decimal):
            raise TypeError("prices are Decimals")
        if price < 0 or price != round_money(price):
            raise OrderError("bad_price", "prices are in rupees with at most two decimals", {"item_id": str(item_id)})
