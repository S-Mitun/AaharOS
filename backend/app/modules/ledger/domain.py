"""Pure double-entry rules for stock journals (MP04, ADR-0002, ADR-0011). No database.

`build_journal()` turns what a caller means ("40 kg flour from RAW_STORE to WIP") into the exact rows the ledger
stores, and refuses anything the ledger must never hold:

- every line converted to the item's base unit (exact, uom.domain)
- Σ qty = 0 per item and Σ value = 0 over the journal (laws 1 and 2; PostgreSQL re-checks both at commit)
- the line role (IN / OUT / SCRAP_IN / VALUE_ONLY) derived from the signs, never typed by hand
- value-only lines only in COST_TRUE_UP and REVERSAL journals
- a reason for ADJUSTMENT and REVERSAL, an approver for ADJUSTMENT
- values already rounded to paise (rounding happens once, at posting, in the caller's valuation step)
- lot-tracked items always carry a lot
- floats refused everywhere
- incoming lines ordered before outgoing ones, because the store-not-negative CHECK runs per line (ADR-0009)
"""

import hashlib
import json
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Final

from app.core.errors import DomainError
from app.modules.uom.domain import ItemUnits, require_decimal, to_base

# Kinds and the source document each one must reference (every movement names its source, CLAUDE.md).
SOURCE_FOR_KIND: Final[dict[str, str]] = {
    "OPENING": "opening",
    "RECEIPT": "purchase_receipt",
    "ISSUE": "material_issue",
    "RETURN": "material_issue",
    "RUN_COMPLETION": "production_run",
    "COST_TRUE_UP": "run_cost",
    "DISPATCH": "dispatch",
    "SALES_RETURN": "sales_return",
    "ADJUSTMENT": "stock_count",
    "REVERSAL": "stock_journal",
}
KINDS: Final = tuple(SOURCE_FOR_KIND)
REASON_REQUIRED: Final = frozenset({"ADJUSTMENT", "REVERSAL"})
VALUE_ONLY_KINDS: Final = frozenset({"COST_TRUE_UP", "REVERSAL"})

SCRAP_LOCATION: Final = "SCRAP"

# The standard locations of every organization (docs/architecture/ledger.md section 1).
STANDARD_LOCATIONS: Final[dict[str, tuple[str, str]]] = {
    "RAW_STORE": ("STORE", "Raw-material store"),
    "PACK_STORE": ("STORE", "Packaging store"),
    "WIP": ("STORE", "Production floor"),
    "FG_STORE": ("STORE", "Finished goods store"),
    "IN_TRANSIT": ("STORE", "In transit"),
    "OPENING": ("VIRTUAL", "Opening balances"),
    "SUPPLIER": ("VIRTUAL", "Suppliers"),
    "PRODUCTION": ("VIRTUAL", "Conversion"),
    "CONVERSION_COST": ("VIRTUAL", "Run costs absorbed"),
    "SCRAP": ("VIRTUAL", "Damaged and waste"),
    "CUSTOMER": ("VIRTUAL", "Sold and dispatched"),
    "ADJUSTMENT": ("VIRTUAL", "Count differences"),
}

PAISE_PLACES: Final = 2
_PAISE_STEP: Final = Decimal(1).scaleb(-PAISE_PLACES)


class JournalError(DomainError):
    """A journal the ledger refuses to post."""


@dataclass(frozen=True)
class LineSpec:
    """One line as a caller means it. `qty` is signed: negative leaves `location`, positive arrives there."""

    item_id: uuid.UUID
    location: str  # location code, e.g. RAW_STORE
    qty: Decimal
    unit: str  # kg, g, L, mL, piece, packet, carton
    value: Decimal = Decimal(0)  # rupees, signed like qty, already rounded to paise
    lot_id: uuid.UUID | None = None
    units_per_carton: int | None = None  # from the pack spec version, only when unit == "carton"


@dataclass(frozen=True)
class JournalLine:
    """One stored line: base-unit quantity, rupee value and the derived role."""

    line_no: int
    item_id: uuid.UUID
    location: str
    lot_id: uuid.UUID | None
    qty_base: Decimal
    value: Decimal
    role: str


@dataclass(frozen=True)
class JournalDraft:
    kind: str
    source_type: str
    source_id: uuid.UUID
    posting_date: date
    lines: tuple[JournalLine, ...]
    reason: str | None = None
    approved_by: uuid.UUID | None = None
    reverses_journal_id: uuid.UUID | None = None
    consume_reservation_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)

    def request_hash(self) -> bytes:
        """A digest of everything the journal means, for Idempotency-Key replays (60 kg and 60000 g hash alike)."""
        doc = {
            "kind": self.kind,
            "source_type": self.source_type,
            "source_id": str(self.source_id),
            "posting_date": self.posting_date.isoformat(),
            "reason": self.reason,
            "approved_by": None if self.approved_by is None else str(self.approved_by),
            "reverses": None if self.reverses_journal_id is None else str(self.reverses_journal_id),
            "consume": sorted(str(r) for r in self.consume_reservation_ids),
            "lines": [
                [
                    str(ln.item_id),
                    ln.location,
                    None if ln.lot_id is None else str(ln.lot_id),
                    _canon(ln.qty_base),
                    _canon(ln.value),
                ]
                for ln in self.lines
            ],
        }
        return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).digest()


Position = tuple[uuid.UUID, str, uuid.UUID | None]
"""(item, location code, lot): one balance row of `inventory_balances`."""


def _canon(d: Decimal) -> str:
    return "0" if d == 0 else format(d.normalize(), "f")


def require_money(value: object, what: str = "value") -> Decimal:
    """A rupee amount: Decimal (never float) with at most 2 decimal places."""
    try:
        money = require_decimal(value, what)
    except DomainError as exc:
        raise JournalError(exc.code, exc.message, exc.details) from exc
    if money != money.quantize(_PAISE_STEP):  # by value: 2700.000 is fine, 2700.005 is not
        raise JournalError(
            "value_not_rounded",
            f"{what} {money} has more than 2 decimal places: round to paise (core.money.round_money) before posting",
            {"value": str(money)},
        )
    return money


def derive_role(qty_base: Decimal, value: Decimal, location: str, kind: str) -> str:
    """The line role follows from the signs (and the SCRAP location), so it can never be mistyped."""
    if qty_base > 0:
        if value < 0:
            raise JournalError(
                "sign_mismatch", "an incoming line cannot carry a negative value", {"location": location}
            )
        return "SCRAP_IN" if value == 0 and location == SCRAP_LOCATION else "IN"
    if qty_base < 0:
        if value > 0:
            raise JournalError(
                "sign_mismatch", "an outgoing line cannot carry a positive value", {"location": location}
            )
        return "OUT"
    if value == 0:
        raise JournalError("empty_line", "a line needs a quantity or a value", {"location": location})
    if kind not in VALUE_ONLY_KINDS:
        raise JournalError(
            "value_only_not_allowed",
            f"value-only lines are allowed only in COST_TRUE_UP or REVERSAL journals, not {kind}",
            {"kind": kind},
        )
    return "VALUE_ONLY"


def _incoming_first(qty_base: Decimal, value: Decimal) -> int:
    return 0 if qty_base > 0 or (qty_base == 0 and value > 0) else 1


def build_journal(
    *,
    kind: str,
    source_type: str,
    source_id: uuid.UUID,
    posting_date: date,
    lines: Sequence[LineSpec],
    items: Mapping[uuid.UUID, ItemUnits],
    locations: Iterable[str],
    reason: str | None = None,
    approved_by: uuid.UUID | None = None,
    reverses_journal_id: uuid.UUID | None = None,
    consume_reservation_ids: Sequence[uuid.UUID] = (),
) -> JournalDraft:
    """Validate a journal and return the exact rows to store. Raises JournalError (or UomError) on any violation."""
    if kind not in SOURCE_FOR_KIND:
        raise JournalError("unknown_kind", f"journal kind must be one of {', '.join(KINDS)}", {"kind": kind})
    if source_type != SOURCE_FOR_KIND[kind]:
        raise JournalError(
            "wrong_source",
            f"a {kind} journal must reference a {SOURCE_FOR_KIND[kind]} document, not {source_type}",
            {"kind": kind, "source_type": source_type},
        )
    if not isinstance(posting_date, date):
        raise JournalError("posting_date_required", "posting_date must be a date")
    clean_reason = (reason or "").strip() or None
    if kind in REASON_REQUIRED and clean_reason is None:
        raise JournalError("reason_required", f"a {kind} journal needs a reason", {"kind": kind})
    if kind == "ADJUSTMENT" and approved_by is None:
        raise JournalError("approval_required", "a stock adjustment needs an approver")
    if (kind == "REVERSAL") != (reverses_journal_id is not None):
        raise JournalError("reversal_link", "a REVERSAL (and only a REVERSAL) names the journal it reverses")
    if not lines:
        raise JournalError("no_lines", "a journal needs at least one line")

    known_locations = set(locations)
    built: list[tuple[uuid.UUID, str, uuid.UUID | None, Decimal, Decimal, str]] = []
    for spec in lines:
        if spec.location not in known_locations:
            raise JournalError("unknown_location", f"unknown location {spec.location!r}", {"location": spec.location})
        units = items.get(spec.item_id)
        if units is None:
            raise JournalError("unknown_item", "unknown item", {"item_id": str(spec.item_id)})
        if units.lot_tracked and spec.lot_id is None:
            raise JournalError(
                "lot_required", "this item is lot-tracked: every line needs a lot", {"item_id": str(spec.item_id)}
            )
        qty_base = to_base(spec.qty, spec.unit, units, units_per_carton=spec.units_per_carton)
        value = require_money(spec.value)
        role = derive_role(qty_base, value, spec.location, kind)
        built.append((spec.item_id, spec.location, spec.lot_id, qty_base, value, role))

    qty_by_item: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for item_id, _, _, qty_base, _, _ in built:
        qty_by_item[item_id] += qty_base
    unbalanced = {str(i): str(q) for i, q in qty_by_item.items() if q != 0}
    if unbalanced:
        raise JournalError(
            "unbalanced_quantity",
            "every item's quantity must sum to zero across the journal (law 1)",
            {"sum_by_item": unbalanced},
        )
    total_value = sum((b[4] for b in built), Decimal(0))
    if total_value != 0:
        raise JournalError(
            "unbalanced_value", f"the journal's value sums to {total_value}, not 0 (law 2)", {"sum": str(total_value)}
        )

    ordered = sorted(built, key=lambda b: _incoming_first(b[3], b[4]))  # stable: callers' order within each group
    return JournalDraft(
        kind=kind,
        source_type=source_type,
        source_id=source_id,
        posting_date=posting_date,
        reason=clean_reason,
        approved_by=approved_by,
        reverses_journal_id=reverses_journal_id,
        consume_reservation_ids=tuple(consume_reservation_ids),
        lines=tuple(
            JournalLine(line_no=n, item_id=i, location=loc, lot_id=lot, qty_base=q, value=v, role=r)
            for n, (i, loc, lot, q, v, r) in enumerate(ordered, start=1)
        ),
    )


def mirror_lines(lines: Iterable[JournalLine], items: Mapping[uuid.UUID, ItemUnits]) -> list[LineSpec]:
    """The exact mirror of a posted journal, line for line and at the same values (history is never revalued)."""
    return [
        LineSpec(
            item_id=ln.item_id,
            location=ln.location,
            qty=-ln.qty_base,
            unit=items[ln.item_id].base_uom,
            value=-ln.value,
            lot_id=ln.lot_id,
        )
        for ln in lines
    ]


def position_deltas(lines: Iterable[JournalLine]) -> dict[Position, tuple[Decimal, Decimal]]:
    """Net (qty, value) change per balance row."""
    out: dict[Position, tuple[Decimal, Decimal]] = {}
    for ln in lines:
        key = (ln.item_id, ln.location, ln.lot_id)
        q, v = out.get(key, (Decimal(0), Decimal(0)))
        out[key] = (q + ln.qty_base, v + ln.value)
    return out


def outgoing_positions(lines: Iterable[JournalLine]) -> set[tuple[uuid.UUID, str]]:
    """(item, location) pairs this journal takes quantity out of."""
    return {(ln.item_id, ln.location) for ln in lines if ln.qty_base < 0}


@dataclass(frozen=True)
class LedgerRow:
    """One line of the stock ledger report, with the running balance of its item within the filter."""

    journal_id: uuid.UUID
    line_no: int
    item_id: uuid.UUID
    location: str
    lot_id: uuid.UUID | None
    posting_date: date
    kind: str
    source_type: str
    source_id: uuid.UUID
    qty_base: Decimal
    value: Decimal
    running_qty_base: Decimal = Decimal(0)
    running_value: Decimal = Decimal(0)


def with_running_balance(
    rows: Iterable[LedgerRow], opening: Mapping[uuid.UUID, tuple[Decimal, Decimal]]
) -> list[LedgerRow]:
    """Add a running (qty, value) per item, starting from that item's opening balance. Rows must be in order."""
    running = {item: (q, v) for item, (q, v) in opening.items()}
    out: list[LedgerRow] = []
    for row in rows:
        q, v = running.get(row.item_id, (Decimal(0), Decimal(0)))
        q, v = q + row.qty_base, v + row.value
        running[row.item_id] = (q, v)
        out.append(replace(row, running_qty_base=q, running_value=v))
    return out
