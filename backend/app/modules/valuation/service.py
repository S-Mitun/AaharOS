"""Valuation use cases (MP05, ADR-0012). Other modules call only this file.

The WAC pool is **read from the ledger projection** (`inventory_balances` at the pool stores), never kept in a
second table the app would write (decision D1). FIFO and last price are **replayed from the item's ledger history**
on demand and never post (decision D2).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.modules.catalog import service as catalog
from app.modules.ledger import service as ledger
from app.modules.ledger.domain import LineSpec
from app.modules.uom.domain import from_base, to_base
from app.modules.valuation import domain
from app.modules.valuation.domain import POOL_LOCATIONS, Movement, Pool, ValuationError


def pool(session: Session, item_id: uuid.UUID) -> Pool:
    """The item's WAC pool: Σ (qty, value) of its balances at the pool stores."""
    return Pool(*ledger.balance_at(session, item_id, POOL_LOCATIONS))


def history(session: Session, item_id: uuid.UUID) -> list[Movement]:
    """Every journal's net change to the item's pool, in posting order (one movement per journal)."""
    return [
        Movement(
            qty_base=m.qty_base,
            value=m.value,
            kind=m.kind,
            key=str(m.journal_id),
            reverses=None if m.reverses_journal_id is None else str(m.reverses_journal_id),
        )
        for m in ledger.net_movements(session, item_id, POOL_LOCATIONS)
    ]


def wac(session: Session, item_id: uuid.UUID) -> Explained:
    """Average cost per stock unit (₹/kg, ₹/L, ₹/piece), with its formula and inputs. Display only (6 dp)."""
    units = catalog.units_for(session, [item_id])[item_id]
    p = pool(session, item_id)
    per = to_base(Decimal(1), units.stock_uom, units)
    value = domain.unit_cost(p, per)
    if value is None:
        raise ValuationError("pool_empty", "no stock in the pool, so there is no average cost yet")
    source = SourceRef("inventory_balances", str(item_id))
    return Explained(
        value=value,
        unit=f"INR/{units.stock_uom}",
        formula="pool value / pool quantity",
        method=domain.BOOK_METHOD,
        inputs=(
            ExplainedInput("pool value", p.value, "INR", source),
            ExplainedInput("pool quantity", from_base(p.qty_base, units.stock_uom, units), units.stock_uom, source),
        ),
    )


def issue_value(
    session: Session,
    *,
    organization_id: uuid.UUID,
    item_id: uuid.UUID,
    qty_base: Decimal,
    from_location: str,
    lot_id: uuid.UUID | None = None,
) -> Decimal:
    """The book value of taking `qty_base` out of `from_location`, under the same lock `ledger.post` takes.

    Pool stores use WAC over the whole pool; any other store (WIP, or a finished-goods lot) gives its own position's
    proportional value. The lock is held until the caller's transaction ends, so the value cannot go stale before
    the journal posts.
    """
    loc = ledger.locations(session).get(from_location)
    if loc is None:
        raise DomainError("location_not_found", f"unknown location {from_location!r}")
    ledger.lock_positions(session, organization_id, [(item_id, loc.id)])
    if from_location in POOL_LOCATIONS:
        source = pool(session, item_id)
    else:
        source = Pool(*ledger.balance(session, item_id, from_location, lot_id))
    try:
        return domain.proportional_value(source, qty_base)
    except ValuationError as exc:
        if exc.code not in ("pool_short", "pool_empty"):
            raise
        raise _short(session, item_id, source.qty_base, qty_base, exc.code) from exc


def _short(session: Session, item_id: uuid.UUID, have_base: Decimal, want_base: Decimal, code: str) -> ValuationError:
    """The same refusal in the user's words: the item's name and its stock unit, e.g. 'only 3 carton 20 in stock'."""
    units = catalog.units_for(session, [item_id])[item_id]
    name = catalog.names_for(session, [item_id]).get(item_id, ("", "this item"))[1]
    have = from_base(max(have_base, Decimal(0)), units.stock_uom, units).normalize()
    want = from_base(want_base, units.stock_uom, units).normalize()
    return ValuationError(
        code,
        f"Not enough {name} in stock: {have:f} {units.stock_uom} available, {want:f} {units.stock_uom} needed.",
        {"available": str(have), "requested": str(want), "unit": units.stock_uom},
    )


def sensitivity(session: Session, item_id: uuid.UUID, qty_base: Decimal) -> dict[str, dict[str, Any]]:
    """What issuing `qty_base` now would cost under each method. Only WAC ever posts."""
    moves = history(session, item_id)
    out: dict[str, dict[str, Any]] = {}
    for name, method in domain.METHODS.items():
        try:
            out[name] = {"value": method.issue_value(moves, qty_base), "posts": method.posts}
        except ValuationError as exc:
            out[name] = {"value": None, "posts": method.posts, "reason": exc.message}
    return out


def sensitivity_at(
    session: Session, item_id: uuid.UUID, qty_base: Decimal, before_journal_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """What issuing `qty_base` would have cost under each method **as of** the journal that issued it: the history
    is replayed up to, not including, that journal, so later purchases never leak in (ADR-0014, decision F6)."""
    moves = history(session, item_id)
    keys = [m.key for m in moves]
    if str(before_journal_id) not in keys:
        raise ValuationError("journal_not_in_history", "that journal did not move this item's pool")
    earlier = moves[: keys.index(str(before_journal_id))]
    out: dict[str, dict[str, Any]] = {}
    for name, method in domain.METHODS.items():
        try:
            out[name] = {"value": method.issue_value(earlier, qty_base), "posts": method.posts}
        except ValuationError as exc:
            out[name] = {"value": None, "posts": method.posts, "reason": exc.message}
    return out


def gain_value(session: Session, item_id: uuid.UUID, qty_base: Decimal) -> tuple[Decimal, str]:
    """Value for stock found in a count (WAC, else last receipt price, else ₹0 with basis NO_COST_YET)."""
    return domain.gain_value(history(session, item_id), qty_base)


@dataclass(frozen=True)
class OpeningLine:
    item_id: uuid.UUID
    location: str  # the store the opening stock sits in
    qty: Decimal
    unit: str
    rate: Decimal  # rupees per `unit`
    lot_id: uuid.UUID | None = None
    units_per_carton: int | None = None


def post_opening(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    posting_date: date,
    lines: Sequence[OpeningLine],
    idempotency_key: uuid.UUID | None = None,
) -> ledger.Posted:
    """Opening balances as one OPENING journal: OPENING → store at qty x rate, rounded once to paise per line."""
    specs: list[LineSpec] = []
    for line in lines:
        value = domain.line_value(line.qty, line.rate)
        specs += [
            LineSpec(line.item_id, line.location, line.qty, line.unit, value, line.lot_id, line.units_per_carton),
            LineSpec(line.item_id, "OPENING", -line.qty, line.unit, -value, line.lot_id, line.units_per_carton),
        ]
    return ledger.post(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        kind="OPENING",
        source_type="opening",
        source_id=uuid.uuid5(organization_id, f"opening:{posting_date.isoformat()}"),
        posting_date=posting_date,
        lines=specs,
        idempotency_key=idempotency_key,
    )


def valuation_summary(session: Session) -> list[dict[str, Any]]:
    """Pool and average cost for every pooled item that has stock (GET /api/stock/valuation)."""
    ids = ledger.items_held_at(session, POOL_LOCATIONS)
    codes = catalog.codes_for(session, ids)
    units = catalog.units_for(session, ids)
    out = []
    for item_id in sorted(ids, key=lambda i: codes[i]):
        p = pool(session, item_id)
        u = units[item_id]
        out.append(
            {
                "item_id": str(item_id),
                "item_code": codes[item_id],
                "qty": str(from_base(p.qty_base, u.stock_uom, u)),
                "uom": u.stock_uom,
                "value": str(p.value),
                "average_cost": wac(session, item_id).to_json(),
            }
        )
    return out
