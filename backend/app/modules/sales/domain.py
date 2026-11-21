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

from app.core.errors import ConflictError, DomainError
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


# ---------- MP09: deciding on an order (ADR-0016) ----------

# Which statuses each decision may start from. Anything else is a conflict (409): the order was already decided.
ALLOWED_FROM: Final[dict[str, frozenset[str]]] = {
    "approve": frozenset({"SUBMITTED"}),
    "approve_backorder": frozenset({"PART_APPROVED"}),
    "reject": frozenset({"SUBMITTED", "PART_APPROVED"}),
    "cancel": frozenset({"APPROVED", "PART_APPROVED"}),
    "amend_price": frozenset({"SUBMITTED", "PART_APPROVED", "APPROVED"}),
    "amend_qty": frozenset({"PART_APPROVED", "APPROVED"}),
    "wait": frozenset({"SUBMITTED"}),
}
OPEN_STATUSES: Final = frozenset({"SUBMITTED", "PART_APPROVED"})


def require_status(action: str, status: str) -> None:
    if status not in ALLOWED_FROM[action]:
        raise ConflictError(
            "order_already_decided",
            f"this order is {status}, so it cannot take this action now",
            {"status": status, "action": action},
        )


def require_reason(reason: str | None, what: str) -> str:
    text = (reason or "").strip()
    if len(text) < 3:
        raise OrderError("reason_required", f"{what} needs a reason")
    return text


@dataclass(frozen=True)
class LineState:
    line_no: int
    item_id: uuid.UUID
    requested: int
    approved: int
    backordered: int


@dataclass(frozen=True)
class LineDecision:
    line_no: int
    item_id: uuid.UUID
    target: int  # packets the factory agrees to supply (requested, or less with a reason)
    reserve: int  # packets reserved now
    backorder: int  # packets owed later


def agreed_quantities(lines: Sequence[LineState], agreed: Mapping[int, int]) -> dict[int, int]:
    """Packets to supply per line: the request, or a lower agreed quantity (an amendment, which needs a reason)."""
    by_no = {ln.line_no: ln for ln in lines}
    for line_no in agreed:
        if line_no not in by_no:
            raise OrderError("unknown_line", "no such line on this order", {"line_no": line_no})
    out: dict[int, int] = {}
    for ln in lines:
        qty = agreed.get(ln.line_no, ln.requested)
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0 or qty > ln.requested:
            raise OrderError(
                "bad_agreed_qty",
                "an agreed quantity is a whole number of packets from 0 to the quantity ordered",
                {"line_no": ln.line_no, "requested": ln.requested},
            )
        out[ln.line_no] = qty
    if not any(out.values()):
        raise OrderError("nothing_to_supply", "every line is at zero: reject the order instead")
    return out


def approval_plan(
    lines: Sequence[LineState], agreed: Mapping[int, int], available: Mapping[uuid.UUID, int], partial: bool
) -> list[LineDecision]:
    """Full approval reserves every agreed packet or nothing (refused with the shortage per line). Partial approval
    reserves what is available and backorders the rest; it is refused only if nothing at all can be reserved."""
    plan = []
    short: list[dict[str, Any]] = []
    for ln in lines:
        target = agreed[ln.line_no]
        avail = max(0, available.get(ln.item_id, 0))
        reserve = min(target, avail)
        if reserve < target and not partial:
            short.append(
                {
                    "line_no": ln.line_no,
                    "item_id": str(ln.item_id),
                    "requested": target,
                    "available": avail,
                    "shortage": target - avail,
                }
            )
        plan.append(LineDecision(ln.line_no, ln.item_id, target, reserve, target - reserve))
    if short:
        raise OrderError(
            "insufficient_available",
            "not enough stock is available to promise for a full approval: send what is available and backorder"
            " the rest, wait for the next batch, or reject",
            {"lines": short},
        )
    if sum(d.reserve for d in plan) == 0:
        raise OrderError("nothing_available", "no stock is available to promise for this order today")
    return plan


def backorder_plan(lines: Sequence[LineState], available: Mapping[uuid.UUID, int]) -> list[LineDecision]:
    """Cover backordered packets from stock that has become available. Refused if none can be covered."""
    plan = []
    for ln in lines:
        reserve = min(ln.backordered, max(0, available.get(ln.item_id, 0)))
        plan.append(
            LineDecision(ln.line_no, ln.item_id, ln.approved + ln.backordered, reserve, ln.backordered - reserve)
        )
    if sum(d.reserve for d in plan) == 0:
        raise OrderError("nothing_available", "no stock is available to promise for the backorder yet")
    return plan


def status_after(lines: Sequence[tuple[int, int]]) -> str:
    """(approved, backordered) per line -> APPROVED when nothing is owed, else PART_APPROVED."""
    return "APPROVED" if all(back == 0 for _, back in lines) else "PART_APPROVED"


def reduce_line(approved: int, backordered: int, new_target: int) -> tuple[int, int]:
    """Amend an approved line down: the backorder shrinks first, then the approved (reserved) packets.
    Returns (approved, backordered)."""
    current = approved + backordered
    if isinstance(new_target, bool) or not isinstance(new_target, int) or new_target < 0 or new_target >= current:
        raise OrderError(
            "bad_agreed_qty",
            "an amendment can only lower the agreed quantity (raise it with a new order)",
            {"agreed": current},
        )
    cut = current - new_target
    from_back = min(cut, backordered)
    return approved - (cut - from_back), backordered - from_back


def shortage(open_qty: int, available: int) -> int:
    return max(0, open_qty - max(0, available))


def stock_explained(on_hand: int, reserved: int) -> Explained:
    """Available to promise = on hand (in non-expired lots, at FG_STORE) - reserved for approved orders."""
    return Explained(
        value=Decimal(on_hand - reserved),
        unit="packets",
        formula="on hand - reserved",
        inputs=(
            ExplainedInput("On hand (finished-goods store, not expired)", Decimal(on_hand), "packets"),
            ExplainedInput("Reserved for approved orders", Decimal(reserved), "packets"),
        ),
        method="Available to promise",
    )


def shortage_explained(open_qty: int, available: int) -> Explained:
    return Explained(
        value=Decimal(shortage(open_qty, available)),
        unit="packets",
        formula="max(0, packets to decide - available to promise)",
        inputs=(
            ExplainedInput("Packets to decide on this order", Decimal(open_qty), "packets"),
            ExplainedInput("Available to promise", Decimal(max(0, available)), "packets"),
        ),
        method="Shortage",
    )


BILLING_STATUSES: Final = frozenset({"APPROVED", "PART_APPROVED", "INVOICED", "DISPATCHED"})


def billing_status(lines: Sequence[tuple[int, int, int, int]]) -> str:
    """MP10: (approved, backordered, invoiced, dispatched) per line -> the order's status once it is approved.
    DISPATCHED when every agreed packet has left, INVOICED when every agreed packet is invoiced, else APPROVED or
    PART_APPROVED (a backorder is still owed)."""
    owed = any(back for _, back, _, _ in lines)
    if not owed and all(disp == appr for appr, _, _, disp in lines) and any(appr for appr, *_ in lines):
        return "DISPATCHED"
    if not owed and all(inv == appr for appr, _, inv, _ in lines) and any(appr for appr, *_ in lines):
        return "INVOICED"
    return "PART_APPROVED" if owed else "APPROVED"


@dataclass(frozen=True)
class CreditCheck:
    limit: Decimal | None  # None: no limit set (0 in the master data)
    outstanding: Explained
    exposure: Explained
    over_limit: bool


def credit_check(limit: Decimal, outstanding: Explained, order_value: Decimal) -> CreditCheck:
    """Outstanding + this order (ex-tax) against the customer's credit limit. A limit of 0 means none is set."""
    exposure = Explained(
        value=round_money(outstanding.value + order_value),
        unit="INR",
        formula="outstanding + this order (ex-tax)",
        inputs=(
            ExplainedInput("Outstanding", outstanding.value, "INR"),
            ExplainedInput("This order (ex-tax)", order_value, "INR"),
        ),
        method="Credit exposure",
    )
    has_limit = limit > 0
    return CreditCheck(
        limit=limit if has_limit else None,
        outstanding=outstanding,
        exposure=exposure,
        over_limit=has_limit and exposure.value > limit,
    )
