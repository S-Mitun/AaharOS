"""Pure purchase-receipt rules (MP05, ADR-0004, ADR-0012). No database.

- Stock value of a line = accepted quantity (in the entered unit) x rate, rounded once to paise.
- Freight and other charges are recorded on the line but **excluded** from stock value (ADR-0004 landed cost, v1).
  GST paid on purchases is input credit, never stock value, so it is not part of a receipt line at all.
- Rejected quantity is recorded and never enters stock.
- Only raw materials and packaging are purchased; finished goods are produced.
- A supplier lot number and its dates are recorded on the line (decision D4); raw stock itself carries no lot.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final

from app.core.errors import DomainError
from app.modules.uom.domain import ItemUnits, require_decimal, to_base
from app.modules.valuation.domain import line_value

HOME_STORE: Final = {"RAW": "RAW_STORE", "PACK": "PACK_STORE"}
RATE_PLACES: Final = 6
MONEY_PLACES: Final = 2


class ReceiptError(DomainError):
    """A purchase receipt the books refuse."""


@dataclass(frozen=True)
class ReceiptLineIn:
    item_id: uuid.UUID
    qty: Decimal  # delivered, in `unit`
    unit: str
    rate: Decimal  # rupees per `unit`, before GST
    freight: Decimal = Decimal(0)  # rupees, recorded but not in stock value
    rejected_qty: Decimal = Decimal(0)  # in `unit`, part of `qty`
    lot_no: str | None = None
    mfg_date: date | None = None
    best_before: date | None = None


@dataclass(frozen=True)
class ReceiptLinePlan:
    line_no: int
    item_id: uuid.UUID
    qty_entered: Decimal
    unit: str
    qty_base: Decimal
    accepted_base: Decimal
    rejected_base: Decimal
    rate: Decimal
    value: Decimal  # accepted value, the amount that enters stock
    freight: Decimal
    lot_no: str | None
    mfg_date: date | None
    best_before: date | None
    store: str


def _places(value: Decimal, places: int, what: str) -> Decimal:
    if value != value.quantize(Decimal(1).scaleb(-places)):
        raise ReceiptError("too_precise", f"{what} {value} has more than {places} decimal places", {"what": what})
    return value


def plan_receipt(
    lines: Sequence[ReceiptLineIn], items: Mapping[uuid.UUID, tuple[ItemUnits, str]]
) -> list[ReceiptLinePlan]:
    """Validate a receipt and compute every stored figure. `items` maps item id -> (units, item kind)."""
    if not lines:
        raise ReceiptError("no_lines", "a receipt needs at least one line")
    planned: list[ReceiptLinePlan] = []
    for n, line in enumerate(lines, start=1):
        units, kind = items[line.item_id]
        if kind not in HOME_STORE:
            raise ReceiptError(
                "not_purchasable", f"only raw materials and packaging are purchased, not {kind} items", {"line": n}
            )
        qty = require_decimal(line.qty)
        rejected = require_decimal(line.rejected_qty, "rejected quantity")
        rate = _places(require_decimal(line.rate, "rate"), RATE_PLACES, "rate")
        freight = _places(require_decimal(line.freight, "freight"), MONEY_PLACES, "freight")
        if qty <= 0:
            raise ReceiptError("qty_not_positive", "the delivered quantity must be positive", {"line": n})
        if rejected < 0 or rejected > qty:
            raise ReceiptError("bad_rejection", "rejected quantity must be between 0 and the delivered quantity")
        if rate < 0 or freight < 0:
            raise ReceiptError("negative_money", "rate and freight must not be negative", {"line": n})
        if line.mfg_date and line.best_before and line.best_before < line.mfg_date:
            raise ReceiptError("dates_out_of_order", "best-before is earlier than the manufacturing date")
        lot_no = (line.lot_no or "").strip() or None
        qty_base = to_base(qty, line.unit, units)
        rejected_base = to_base(rejected, line.unit, units)
        planned.append(
            ReceiptLinePlan(
                line_no=n,
                item_id=line.item_id,
                qty_entered=qty,
                unit=line.unit,
                qty_base=qty_base,
                accepted_base=qty_base - rejected_base,
                rejected_base=rejected_base,
                rate=rate,
                value=line_value(qty - rejected, rate),
                freight=freight,
                lot_no=lot_no,
                mfg_date=line.mfg_date,
                best_before=line.best_before,
                store=HOME_STORE[kind],
            )
        )
    if all(p.accepted_base == 0 for p in planned):
        raise ReceiptError("nothing_accepted", "every line was rejected: nothing enters stock, so there is no receipt")
    return planned


def receipt_no(fy: str, n: int) -> str:
    """GRN/26-27/000001: 16 characters, gapless per organization and financial year."""
    return f"GRN/{fy}/{n:06d}"


def request_doc(
    supplier_id: uuid.UUID, supplier_invoice_ref: str | None, received_on: date, plan: Sequence[ReceiptLinePlan]
) -> dict[str, Any]:
    """What a receipt request means, for its Idempotency-Key hash (60 kg and 60000 g hash alike)."""
    return {
        "supplier_id": supplier_id,
        "supplier_invoice_ref": (supplier_invoice_ref or "").strip() or None,
        "received_on": received_on,
        "lines": [
            [p.item_id, p.qty_base, p.rejected_base, p.value, p.freight, p.lot_no, p.mfg_date, p.best_before]
            for p in plan
        ],
    }
