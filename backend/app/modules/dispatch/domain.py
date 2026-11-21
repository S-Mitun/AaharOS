"""Pure dispatch rules (MP10, ADR-0017, ADR-0005). No database.

- J6 FEFO: packets leave from the lots in First-Expiry-First-Out order (the ledger lists them in that order,
  expired lots left out). An admin may pick other lots with a reason (e.g. a customer asks for one batch).
- Value: a lot's share of its value, proportional and rounded half up to paise; taking the last packets of a lot
  takes all of its remaining value, so nothing is ever left behind on an empty lot.
- The consignment value for the e-way bill check is the dispatched share of each invoice line, tax included.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.core.errors import DomainError
from app.core.money import round_money

DOC_TYPE: Final = "DSP"


class DispatchError(DomainError):
    """A dispatch the books refuse."""


@dataclass(frozen=True)
class LotAvailable:
    lot_id: uuid.UUID
    lot_no: str
    qty: int
    value: Decimal


@dataclass(frozen=True)
class Pick:
    lot_id: uuid.UUID
    lot_no: str
    qty: int
    value: Decimal


def lot_share(lot: LotAvailable, take: int) -> Decimal:
    if take == lot.qty:
        return lot.value
    return round_money(lot.value * take / lot.qty)


def pick_fefo(lots: Sequence[LotAvailable], qty: int) -> list[Pick]:
    """Take `qty` packets from the lots in the order given (FEFO). Refused, nothing picked, if they hold too few."""
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise DispatchError("qty_not_positive", "a dispatch moves a positive whole number of packets")
    held = sum(lot.qty for lot in lots)
    if held < qty:
        raise DispatchError(
            "insufficient_lot_stock",
            f"only {held} packets are in unexpired lots; {qty} were asked",
            {"held": held, "asked": qty},
        )
    picks, left = [], qty
    for lot in lots:
        if left == 0:
            break
        take = min(lot.qty, left)
        picks.append(Pick(lot.lot_id, lot.lot_no, take, lot_share(lot, take)))
        left -= take
    return picks


def pick_chosen(
    lots: Sequence[LotAvailable], chosen: Mapping[uuid.UUID, int], qty: int, reason: str | None
) -> list[Pick]:
    """An admin's own lot choice (not FEFO): needs a reason, each lot must hold what is taken, and the packets must
    add up to the quantity dispatched."""
    if len((reason or "").strip()) < 3:
        raise DispatchError(
            "override_reason_required", "choosing lots other than first-expiry-first-out needs a reason"
        )
    by_id = {lot.lot_id: lot for lot in lots}
    if sum(chosen.values()) != qty:
        raise DispatchError("chosen_lots_mismatch", "the packets taken from the chosen lots must equal the dispatch")
    picks = []
    for lot_id, take in chosen.items():
        lot = by_id.get(lot_id)
        if lot is None:
            raise DispatchError(
                "lot_not_available", "that lot is not in stock (or has expired)", {"lot_id": str(lot_id)}
            )
        if take <= 0 or take > lot.qty:
            raise DispatchError("lot_too_small", f"lot {lot.lot_no} holds {lot.qty} packets", {"lot_id": str(lot_id)})
        picks.append(Pick(lot.lot_id, lot.lot_no, take, lot_share(lot, take)))
    return picks


def is_fefo(lots: Sequence[LotAvailable], picks: Sequence[Pick]) -> bool:
    return [(p.lot_id, p.qty) for p in picks] == [(p.lot_id, p.qty) for p in pick_fefo(lots, sum(p.qty for p in picks))]


def consignment_value(lines: Sequence[tuple[int, Decimal, int]]) -> Decimal:
    """(invoiced qty, line total incl. tax, packets dispatched now) per line -> the dispatched share, tax included."""
    return sum((round_money(total * now / qty) for qty, total, now in lines if now), Decimal(0))
