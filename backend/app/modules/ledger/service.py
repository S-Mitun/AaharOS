"""Ledger use cases (MP04, ADR-0011): post, reverse, reserve / release, and the read models.

Other modules call only this file. Every function runs in the caller's transaction and does not commit; the caller
commits once its whole use case is done (a production run posts its journal and its run rows atomically).

`post()` in one savepoint:
  1. claim the Idempotency-Key (same key + same meaning returns the original journal; a different meaning is 409)
  2. take a per-(item, location) transaction lock on every store the journal takes stock out of
  3. insert the journal and its lines; the database trigger updates `inventory_balances` (ADR-0009)
  4. consume the order reservations this journal fulfils
  5. fire the deferred balance triggers now, so a refusal surfaces here rather than at the caller's commit
  6. check available >= 0 (on hand minus active reservations) for every store it took stock out of
  7. write the hash-chained audit row
Any refusal rolls the savepoint back, so a refused journal leaves no trace.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import idempotency
from app.core.calendar import business_date
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.ledger import domain
from app.modules.ledger.domain import JournalDraft, JournalError, JournalLine, LineSpec
from app.modules.ledger.models import (
    InventoryBalance,
    Location,
    Lot,
    PeriodLock,
    Reservation,
    StockJournal,
    StockLine,
)
from app.modules.uom.domain import ItemUnits, from_base, normalise, require_decimal, to_base

DEFERRED_TRIGGERS = "trg_stock_lines_balanced, trg_stock_journals_have_lines"
__all__ = ["business_date"]  # re-exported for callers that already import it from here


# ---------- locations and lots ----------


@dataclass(frozen=True)
class LocationRef:
    id: uuid.UUID
    code: str
    kind: str


def ensure_locations(session: Session, organization_id: uuid.UUID) -> dict[str, LocationRef]:
    """Create any missing standard location for this organization and return them all by code."""
    existing = locations(session)
    for code, (kind, name) in domain.STANDARD_LOCATIONS.items():
        if code not in existing:
            session.execute(
                pg_insert(Location)
                .values(organization_id=organization_id, code=code, name=name, kind=kind)
                .on_conflict_do_nothing(index_elements=["organization_id", "code"])
            )
    return locations(session)


def locations(session: Session) -> dict[str, LocationRef]:
    rows = session.execute(select(Location.id, Location.code, Location.kind)).all()
    return {r.code: LocationRef(r.id, r.code, r.kind) for r in rows}


def create_lot(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    item_id: uuid.UUID,
    lot_no: str,
    source_type: str,
    source_id: uuid.UUID | None = None,
    mfg_date: date | None = None,
    best_before: date | None = None,
) -> uuid.UUID:
    lot_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                pg_insert(Lot).values(
                    id=lot_id,
                    organization_id=organization_id,
                    item_id=item_id,
                    lot_no=lot_no,
                    source_type=source_type,
                    source_id=source_id,
                    mfg_date=mfg_date,
                    best_before=best_before,
                    created_by=actor_id,
                )
            )
    except DBAPIError as exc:
        raise _translate(exc) from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="lot.create",
        entity_type="lot",
        entity_id=lot_id,
        after={"item_id": item_id, "lot_no": lot_no, "source_type": source_type, "best_before": best_before},
    )
    return lot_id


def lot_id_by_no(session: Session, item_id: uuid.UUID, lot_no: str) -> uuid.UUID | None:
    return session.execute(select(Lot.id).where(Lot.item_id == item_id, Lot.lot_no == lot_no)).scalar_one_or_none()


def lot_no(session: Session, lot_id: uuid.UUID) -> str:
    found = session.execute(select(Lot.lot_no).where(Lot.id == lot_id)).scalar_one_or_none()
    if found is None:
        raise NotFoundError("lot_not_found", "unknown lot", {"lot_id": str(lot_id)})
    return found


# ---------- posting ----------


@dataclass(frozen=True)
class Posted:
    journal_id: uuid.UUID
    replayed: bool  # True when an Idempotency-Key replay returned the original journal
    draft: JournalDraft


def post(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    kind: str,
    source_type: str,
    source_id: uuid.UUID,
    posting_date: date,
    lines: Sequence[LineSpec],
    reason: str | None = None,
    approved_by: uuid.UUID | None = None,
    idempotency_key: uuid.UUID | None = None,
    consume_reservation_ids: Sequence[uuid.UUID] = (),
) -> Posted:
    """Post one stock journal. Raises DomainError (422), ConflictError (409) or NotFoundError (404) on refusal."""
    if kind == "REVERSAL":
        raise JournalError("use_reverse", "post a reversal with ledger.service.reverse(journal_id, reason)")
    return _post(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        kind=kind,
        source_type=source_type,
        source_id=source_id,
        posting_date=posting_date,
        lines=lines,
        reason=reason,
        approved_by=approved_by,
        idempotency_key=idempotency_key,
        consume_reservation_ids=consume_reservation_ids,
        reverses_journal_id=None,
    )


def reverse(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    journal_id: uuid.UUID,
    reason: str,
    posting_date: date | None = None,
    idempotency_key: uuid.UUID | None = None,
) -> Posted:
    """Post the exact mirror of a journal. A reversal itself cannot be reversed; a journal is reversed at most once."""
    original = session.execute(select(StockJournal).where(StockJournal.id == journal_id)).scalar_one_or_none()
    if original is None:
        raise NotFoundError("journal_not_found", "unknown stock journal", {"journal_id": str(journal_id)})
    if original.kind == "REVERSAL":
        raise JournalError(
            "cannot_reverse_reversal", "a reversal cannot be reversed: post the original movement again instead"
        )
    already = session.execute(
        select(StockJournal.id).where(StockJournal.reverses_journal_id == journal_id)
    ).scalar_one_or_none()
    if already is not None and idempotency_key is None:
        raise JournalError("already_reversed", "this journal has already been reversed", {"reversal_id": str(already)})
    original_lines = _journal_lines(session, journal_id)
    items = catalog.units_for(session, {ln.item_id for ln in original_lines})
    return _post(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        kind="REVERSAL",
        source_type="stock_journal",
        source_id=journal_id,
        posting_date=posting_date or business_date(),
        lines=domain.mirror_lines(original_lines, items),
        reason=reason,
        approved_by=None,
        idempotency_key=idempotency_key,
        consume_reservation_ids=(),
        reverses_journal_id=journal_id,
    )


def _post(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    kind: str,
    source_type: str,
    source_id: uuid.UUID,
    posting_date: date,
    lines: Sequence[LineSpec],
    reason: str | None,
    approved_by: uuid.UUID | None,
    idempotency_key: uuid.UUID | None,
    consume_reservation_ids: Sequence[uuid.UUID],
    reverses_journal_id: uuid.UUID | None,
) -> Posted:
    locs = locations(session)
    items = catalog.units_for(session, {spec.item_id for spec in lines})
    draft = domain.build_journal(
        kind=kind,
        source_type=source_type,
        source_id=source_id,
        posting_date=posting_date,
        lines=lines,
        items=items,
        locations=locs,
        reason=reason,
        approved_by=approved_by,
        reverses_journal_id=reverses_journal_id,
        consume_reservation_ids=consume_reservation_ids,
    )
    try:
        with session.begin_nested():
            if idempotency_key is not None:
                original = _claim_idempotency_key(session, organization_id, idempotency_key, draft.request_hash())
                if original is not None:
                    return Posted(journal_id=original, replayed=True, draft=draft)
            reservations = _load_reservations(session, draft.consume_reservation_ids)
            taken_from_stores = {
                (item, locs[loc].id)
                for item, loc in domain.outgoing_positions(draft.lines)
                if locs[loc].kind == "STORE"
            }
            lock_positions(
                session, organization_id, taken_from_stores | {(r.item_id, r.location_id) for r in reservations}
            )
            journal_id = _insert_journal(session, organization_id, actor_id, draft, idempotency_key, locs)
            _consume(session, draft, reservations, locs)
            session.execute(text(f"SET CONSTRAINTS {DEFERRED_TRIGGERS} IMMEDIATE"))
            session.execute(text(f"SET CONSTRAINTS {DEFERRED_TRIGGERS} DEFERRED"))
            _check_available(session, taken_from_stores, items)
            if idempotency_key is not None:
                idempotency.complete(session, organization_id, idempotency_key, 201, {"journal_id": journal_id})
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="stock.reverse" if kind == "REVERSAL" else "stock.post",
                entity_type="stock_journal",
                entity_id=journal_id,
                after=_audit_summary(draft),
                note=draft.reason,
            )
    except DBAPIError as exc:
        raise _translate(exc) from exc
    return Posted(journal_id=journal_id, replayed=False, draft=draft)


def _translate(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


def _claim_idempotency_key(
    session: Session, organization_id: uuid.UUID, key: uuid.UUID, request_hash: bytes
) -> uuid.UUID | None:
    """None if this call now owns the key; the original journal id if this exact request was already posted."""
    stored = idempotency.claim(session, organization_id, key, request_hash)
    if stored is None:
        return None
    journal = stored.body.get("journal_id")
    if not isinstance(journal, str):
        raise ConflictError(
            "idempotency_key_reused",
            "this Idempotency-Key belongs to a different kind of request",
            {"idempotency_key": str(key)},
        )
    return uuid.UUID(journal)


def lock_positions(
    session: Session, organization_id: uuid.UUID, positions: Iterable[tuple[uuid.UUID, uuid.UUID]]
) -> None:
    """Serialise everything that changes availability of one (item, store): posts that take stock out, and
    reservations. A transaction-level advisory lock, taken in a fixed order so two posts cannot deadlock.

    Not `SELECT ... FOR UPDATE` on `inventory_balances`: that needs UPDATE privilege, and the app role may only read
    the projection (ADR-0009). The trigger's own UPDATE still row-locks each balance it changes.
    """
    for item_id, location_id in sorted(positions):
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"stock:{organization_id}:{item_id}:{location_id}"},
        )


def _insert_journal(
    session: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    draft: JournalDraft,
    idempotency_key: uuid.UUID | None,
    locs: dict[str, LocationRef],
) -> uuid.UUID:
    journal_id = uuid.uuid4()
    session.execute(
        pg_insert(StockJournal).values(
            id=journal_id,
            organization_id=organization_id,
            kind=draft.kind,
            source_type=draft.source_type,
            source_id=draft.source_id,
            posting_date=draft.posting_date,
            # clock_timestamp, not now(): several journals posted in one transaction keep their order.
            posted_at=func.clock_timestamp(),
            reverses_journal_id=draft.reverses_journal_id,
            reason=draft.reason,
            approved_by=draft.approved_by,
            idempotency_key=idempotency_key,
            created_by=actor_id,
        )
    )
    # Executed one row at a time, in line order: incoming lines first (domain.build_journal sorts them).
    session.execute(
        pg_insert(StockLine),
        [
            {
                "organization_id": organization_id,
                "journal_id": journal_id,
                "line_no": ln.line_no,
                "item_id": ln.item_id,
                "location_id": locs[ln.location].id,
                "lot_id": ln.lot_id,
                "qty_base": ln.qty_base,
                "value": ln.value,
                "line_role": ln.role,  # posted_at is copied from the journal by trg_stock_lines_posted_at
                "created_by": actor_id,
            }
            for ln in draft.lines
        ],
    )
    return journal_id


def _load_reservations(session: Session, ids: Sequence[uuid.UUID]) -> list[Reservation]:
    if not ids:
        return []
    if len(set(ids)) != len(ids):
        raise JournalError("duplicate_reservation", "a reservation is listed twice")
    rows = list(session.execute(select(Reservation).where(Reservation.id.in_(ids)).with_for_update()).scalars())
    if len(rows) != len(ids):
        raise NotFoundError("reservation_not_found", "unknown reservation")
    return rows


def _consume(
    session: Session, draft: JournalDraft, reservations: list[Reservation], locs: dict[str, LocationRef]
) -> None:
    if not reservations:
        return
    taken: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = defaultdict(Decimal)
    for ln in draft.lines:
        if ln.qty_base < 0:
            taken[(ln.item_id, locs[ln.location].id)] -= ln.qty_base
    consumed: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = defaultdict(Decimal)
    for r in reservations:
        if r.status != "ACTIVE":
            raise JournalError("reservation_not_active", f"reservation is {r.status}", {"reservation_id": str(r.id)})
        key = (r.item_id, r.location_id)
        consumed[key] += r.qty_base
        if consumed[key] > taken.get(key, Decimal(0)):
            raise JournalError(
                "reservation_exceeds_movement",
                "the reservations consumed are larger than what this journal takes out of that store",
                {"reservation_id": str(r.id)},
            )
        r.status = "CONSUMED"
    session.flush()


def _check_available(
    session: Session, positions: set[tuple[uuid.UUID, uuid.UUID]], items: dict[uuid.UUID, ItemUnits]
) -> None:
    for item_id, location_id in sorted(positions):
        on_hand, reserved = _on_hand_and_reserved(session, item_id, location_id)
        if on_hand - reserved < 0:
            unit_code = items[item_id].base_uom
            raise JournalError(
                "insufficient_available",
                f"this would leave {normalise(on_hand)} {unit_code} on hand against {normalise(reserved)}"
                f" {unit_code} reserved for"
                " approved orders: release or reduce those reservations first",
                {
                    "item_id": str(item_id),
                    "location_id": str(location_id),
                    "on_hand_after": str(normalise(on_hand)),
                    "reserved": str(normalise(reserved)),
                    "short_by": str(normalise(reserved - on_hand)),
                },
            )


def _on_hand_and_reserved(session: Session, item_id: uuid.UUID, location_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    on_hand = session.execute(
        select(func.coalesce(func.sum(InventoryBalance.qty_base), 0)).where(
            InventoryBalance.item_id == item_id, InventoryBalance.location_id == location_id
        )
    ).scalar_one()
    reserved = session.execute(
        select(func.coalesce(func.sum(Reservation.qty_base), 0)).where(
            Reservation.item_id == item_id, Reservation.location_id == location_id, Reservation.status == "ACTIVE"
        )
    ).scalar_one()
    return Decimal(on_hand), Decimal(reserved)


def _audit_summary(draft: JournalDraft) -> dict[str, Any]:
    return {
        "kind": draft.kind,
        "source": {"type": draft.source_type, "id": draft.source_id},
        "posting_date": draft.posting_date,
        "reverses": draft.reverses_journal_id,
        "lines": [
            {
                "item_id": ln.item_id,
                "location": ln.location,
                "lot_id": ln.lot_id,
                "qty_base": ln.qty_base,
                "value": ln.value,
                "role": ln.role,
            }
            for ln in draft.lines
        ],
        "consumed_reservations": list(draft.consume_reservation_ids),
    }


def _journal_lines(session: Session, journal_id: uuid.UUID) -> list[JournalLine]:
    rows = session.execute(
        select(StockLine, Location.code)
        .join(Location, Location.id == StockLine.location_id)
        .where(StockLine.journal_id == journal_id)
        .order_by(StockLine.line_no)
    ).all()
    return [
        JournalLine(
            line_no=ln.line_no,
            item_id=ln.item_id,
            location=code,
            lot_id=ln.lot_id,
            qty_base=ln.qty_base,
            value=ln.value,
            role=ln.line_role,
        )
        for ln, code in rows
    ]


def journal_lines(session: Session, journal_id: uuid.UUID) -> list[JournalLine]:
    """The stored lines of one journal (base units, signed values, location codes)."""
    return _journal_lines(session, journal_id)


def journal_for(session: Session, kind: str, source_type: str, source_id: uuid.UUID) -> uuid.UUID | None:
    """The journal of one kind posted for a source document (e.g. a run's RUN_COMPLETION), if any."""
    return session.execute(
        select(StockJournal.id).where(
            StockJournal.kind == kind, StockJournal.source_type == source_type, StockJournal.source_id == source_id
        )
    ).scalar_one_or_none()


# ---------- reservations ----------


def available_to_promise(
    session: Session, item_id: uuid.UUID, *, location: str = "FG_STORE", as_of: date | None = None
) -> dict[str, Decimal]:
    """On hand in non-expired lots minus active reservations, at one store."""
    loc = _location(session, location)
    return _atp(session, item_id, loc.id, as_of or business_date())


def _atp(session: Session, item_id: uuid.UUID, location_id: uuid.UUID, as_of: date) -> dict[str, Decimal]:
    on_hand = session.execute(
        select(func.coalesce(func.sum(InventoryBalance.qty_base), 0))
        .select_from(InventoryBalance)
        .outerjoin(Lot, Lot.id == InventoryBalance.lot_id)
        .where(
            InventoryBalance.item_id == item_id,
            InventoryBalance.location_id == location_id,
            (Lot.best_before.is_(None)) | (Lot.best_before >= as_of),
        )
    ).scalar_one()
    _, reserved = _on_hand_and_reserved(session, item_id, location_id)
    on_hand = Decimal(on_hand)
    return {"on_hand": on_hand, "reserved": reserved, "available": on_hand - reserved}


def reserve(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    order_line_id: uuid.UUID,
    item_id: uuid.UUID,
    qty_base: Decimal,
    location: str = "FG_STORE",
    as_of: date | None = None,
) -> uuid.UUID:
    """Hold finished goods for an approved order line. Refused (nothing written) if it exceeds available to promise."""
    qty = require_decimal(qty_base)
    if qty <= 0:
        raise JournalError("qty_not_positive", "a reservation must be for a positive quantity")
    units = catalog.units_for(session, [item_id])[item_id]
    to_base(qty, units.base_uom, units)  # whole pieces, at most 6 dp: the same rule as a posted line
    loc = _location(session, location)
    if loc.kind != "STORE":
        raise JournalError("not_a_store", "stock can be reserved only in a store")
    lock_positions(session, organization_id, [(item_id, loc.id)])
    atp = _atp(session, item_id, loc.id, as_of or business_date())
    if qty > atp["available"]:
        raise JournalError(
            "insufficient_available",
            f"only {normalise(atp['available'])} {units.base_uom} is available to promise;"
            f" {normalise(qty)} was requested",
            {
                "requested": str(normalise(qty)),
                "on_hand": str(normalise(atp["on_hand"])),
                "reserved": str(normalise(atp["reserved"])),
                "available": str(normalise(atp["available"])),
                "shortage": str(normalise(qty - atp["available"])),
            },
        )
    reservation_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                pg_insert(Reservation).values(
                    id=reservation_id,
                    organization_id=organization_id,
                    order_line_id=order_line_id,
                    item_id=item_id,
                    location_id=loc.id,
                    qty_base=qty,
                    created_by=actor_id,
                )
            )
    except DBAPIError as exc:
        raise _translate(exc) from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="stock.reserve",
        entity_type="reservation",
        entity_id=reservation_id,
        after={"order_line_id": order_line_id, "item_id": item_id, "location": location, "qty_base": qty},
    )
    return reservation_id


def release(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reservation_id: uuid.UUID,
    reason: str,
) -> None:
    """Give reserved stock back to available (order rejected, cancelled or amended down)."""
    if not reason.strip():
        raise JournalError("reason_required", "releasing a reservation needs a reason")
    r = session.execute(
        select(Reservation).where(Reservation.id == reservation_id).with_for_update()
    ).scalar_one_or_none()
    if r is None:
        raise NotFoundError("reservation_not_found", "unknown reservation")
    if r.status != "ACTIVE":
        raise JournalError("reservation_not_active", f"reservation is {r.status}", {"reservation_id": str(r.id)})
    r.status = "RELEASED"
    session.flush()
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="stock.release",
        entity_type="reservation",
        entity_id=reservation_id,
        before={"status": "ACTIVE"},
        after={"status": "RELEASED"},
        note=reason.strip(),
    )


def _location(session: Session, code: str) -> LocationRef:
    found = locations(session).get(code)
    if found is None:
        raise NotFoundError("location_not_found", f"unknown location {code!r}")
    return found


# ---------- read models (GET /api/stock/...) ----------


def _qty_view(qty_base: Decimal, units: ItemUnits) -> dict[str, str]:
    return {
        "qty_base": str(qty_base),
        "base_uom": units.base_uom,
        "qty": str(from_base(qty_base, units.stock_uom, units)),
        "uom": units.stock_uom,
    }


def balance(
    session: Session, item_id: uuid.UUID, location: str, lot_id: uuid.UUID | None = None
) -> tuple[Decimal, Decimal]:
    """(qty in base units, value in rupees) of one item at one location; all lots unless `lot_id` is given."""
    loc = _location(session, location)
    query = select(
        func.coalesce(func.sum(InventoryBalance.qty_base), 0), func.coalesce(func.sum(InventoryBalance.value), 0)
    ).where(InventoryBalance.item_id == item_id, InventoryBalance.location_id == loc.id)
    if lot_id is not None:
        query = query.where(InventoryBalance.lot_id == lot_id)
    qty, value = session.execute(query).one()
    return Decimal(qty), Decimal(value)


def balance_at(session: Session, item_id: uuid.UUID, location_codes: Sequence[str]) -> tuple[Decimal, Decimal]:
    """(qty, value) of one item summed over several locations and all lots (e.g. the WAC pool stores)."""
    qty, value = session.execute(
        select(
            func.coalesce(func.sum(InventoryBalance.qty_base), 0), func.coalesce(func.sum(InventoryBalance.value), 0)
        )
        .join(Location, Location.id == InventoryBalance.location_id)
        .where(InventoryBalance.item_id == item_id, Location.code.in_(list(location_codes)))
    ).one()
    return Decimal(qty), Decimal(value)


@dataclass(frozen=True)
class NetMovement:
    journal_id: uuid.UUID
    kind: str
    reverses_journal_id: uuid.UUID | None
    qty_base: Decimal
    value: Decimal


def net_movements(session: Session, item_id: uuid.UUID, location_codes: Sequence[str]) -> list[NetMovement]:
    """Each journal's net change to one item over a set of locations, in posting order (zero changes dropped)."""
    rows = session.execute(
        select(
            StockJournal.id,
            StockJournal.kind,
            StockJournal.reverses_journal_id,
            func.sum(StockLine.qty_base),
            func.sum(StockLine.value),
        )
        .join(StockLine, StockLine.journal_id == StockJournal.id)
        .join(Location, Location.id == StockLine.location_id)
        .where(StockLine.item_id == item_id, Location.code.in_(list(location_codes)))
        .group_by(
            StockJournal.id,
            StockJournal.kind,
            StockJournal.reverses_journal_id,
            StockJournal.posting_date,
            StockJournal.posted_at,
        )
        .order_by(StockJournal.posting_date, StockJournal.posted_at, StockJournal.id)
    ).all()
    return [NetMovement(jid, kind, rev, Decimal(q), Decimal(v)) for jid, kind, rev, q, v in rows if q != 0 or v != 0]


def lot_positions(session: Session, item_id: uuid.UUID, lot_id: uuid.UUID) -> list[tuple[str, Decimal, Decimal]]:
    """(location code, qty_base, value) of every non-zero balance of one lot, virtual locations included."""
    rows = session.execute(
        select(Location.code, InventoryBalance.qty_base, InventoryBalance.value)
        .join(Location, Location.id == InventoryBalance.location_id)
        .where(InventoryBalance.item_id == item_id, InventoryBalance.lot_id == lot_id)
        .where((InventoryBalance.qty_base != 0) | (InventoryBalance.value != 0))
        .order_by(Location.code)
    ).all()
    return [(code, Decimal(q), Decimal(v)) for code, q, v in rows]


def lock_item_stores(session: Session, organization_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """Take the per-(item, store) lock on every store of one item, as `post()` does, before reading its values."""
    stores = [loc.id for loc in locations(session).values() if loc.kind == "STORE"]
    lock_positions(session, organization_id, [(item_id, loc) for loc in stores])


def active_reservations(
    session: Session, order_line_ids: Sequence[uuid.UUID]
) -> list[tuple[uuid.UUID, uuid.UUID, Decimal]]:
    """(reservation, order line, qty) for every ACTIVE reservation of these order lines (MP09)."""
    if not order_line_ids:
        return []
    rows = session.execute(
        select(Reservation.id, Reservation.order_line_id, Reservation.qty_base)
        .where(Reservation.order_line_id.in_(set(order_line_ids)), Reservation.status == "ACTIVE")
        .order_by(Reservation.created_at)
    ).tuples()
    return list(rows.all())


@dataclass(frozen=True)
class LotStock:
    lot_id: uuid.UUID
    lot_no: str
    mfg_date: date | None
    best_before: date | None
    qty_base: Decimal
    value: Decimal


def fefo_lots(
    session: Session, item_id: uuid.UUID, *, location: str = "FG_STORE", as_of: date | None = None
) -> list[LotStock]:
    """MP10 (J6, A3): the lots of an item held at a store, First-Expiry-First-Out: best-before ascending, lots
    with no date (opening stock) first, then manufacture date and creation. Expired lots are left out."""
    loc = _location(session, location)
    on = as_of or business_date()
    rows = session.execute(
        select(Lot.id, Lot.lot_no, Lot.mfg_date, Lot.best_before, InventoryBalance.qty_base, InventoryBalance.value)
        .join(InventoryBalance, InventoryBalance.lot_id == Lot.id)
        .where(
            InventoryBalance.item_id == item_id,
            InventoryBalance.location_id == loc.id,
            InventoryBalance.qty_base > 0,
            (Lot.best_before.is_(None)) | (Lot.best_before >= on),
        )
        .order_by(Lot.best_before.asc().nulls_first(), Lot.mfg_date.asc().nulls_first(), Lot.created_at, Lot.lot_no)
    ).tuples()
    return [LotStock(i, n, m, b, Decimal(q), Decimal(v)) for i, n, m, b, q, v in rows]


def movement_summary(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """MP11 stock summary: per item and store, opening (before the range), quantity in and out, value-only
    adjustments (cost true-ups) and closing (end of the range), by quantity and value. Closing = opening + in - out +
    adjustments, exactly. Scoped to the caller's organization by row-level security."""
    rows = session.execute(
        text(
            """
            SELECT sl.item_id, l.code,
              coalesce(sum(sl.qty_base) FILTER (WHERE j.posting_date < :f), 0),
              coalesce(sum(sl.value) FILTER (WHERE j.posting_date < :f), 0),
              coalesce(sum(sl.qty_base) FILTER (WHERE j.posting_date BETWEEN :f AND :t AND sl.qty_base > 0), 0),
              coalesce(sum(sl.value) FILTER (WHERE j.posting_date BETWEEN :f AND :t AND sl.qty_base > 0), 0),
              coalesce(-sum(sl.qty_base) FILTER (WHERE j.posting_date BETWEEN :f AND :t AND sl.qty_base < 0), 0),
              coalesce(-sum(sl.value) FILTER (WHERE j.posting_date BETWEEN :f AND :t AND sl.qty_base < 0), 0),
              coalesce(sum(sl.value) FILTER (WHERE j.posting_date BETWEEN :f AND :t AND sl.qty_base = 0), 0),
              coalesce(sum(sl.qty_base) FILTER (WHERE j.posting_date <= :t), 0),
              coalesce(sum(sl.value) FILTER (WHERE j.posting_date <= :t), 0)
              FROM stock_lines sl
              JOIN stock_journals j ON j.id = sl.journal_id
              JOIN locations l ON l.id = sl.location_id
             WHERE l.kind = 'STORE' AND j.posting_date <= :t
             GROUP BY sl.item_id, l.code
             ORDER BY l.code
            """
        ),
        {"f": date_from, "t": date_to},
    ).all()
    item_ids = {r[0] for r in rows}
    units = catalog.units_for(session, item_ids)
    codes = catalog.codes_for(session, item_ids)
    out = []
    for item, loc, oq, ov, iq, iv, xq, xv, adj, cq, cv in rows:
        u = units[item]
        out.append(
            {
                "item_id": str(item),
                "item_code": codes[item],
                "store": loc,
                "unit": u.stock_uom,
                "opening_qty": str(from_base(Decimal(oq), u.stock_uom, u)),
                "opening_value": str(Decimal(ov)),
                "in_qty": str(from_base(Decimal(iq), u.stock_uom, u)),
                "in_value": str(Decimal(iv)),
                "out_qty": str(from_base(Decimal(xq), u.stock_uom, u)),
                "out_value": str(Decimal(xv)),
                "value_adjustments": str(Decimal(adj)),
                "closing_qty": str(from_base(Decimal(cq), u.stock_uom, u)),
                "closing_value": str(Decimal(cv)),
            }
        )
    return out


# ---------- month-end close (MP11, ADR-0018 K5) ----------


def _month_start(month: date) -> date:
    return month.replace(day=1)


def period_locks(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": str(p.id),
            "period": p.period.isoformat(),
            "locked_at": p.locked_at.isoformat(),
            "locked_by": None if p.locked_by is None else str(p.locked_by),
            "reason": p.reason,
            "reopened_at": None if p.reopened_at is None else p.reopened_at.isoformat(),
            "reopened_by": None if p.reopened_by is None else str(p.reopened_by),
            "reopen_reason": p.reopen_reason,
            "active": p.reopened_at is None,
        }
        for p in session.execute(select(PeriodLock).order_by(PeriodLock.period, PeriodLock.locked_at)).scalars()
    ]


def is_locked(session: Session, month: date) -> bool:
    return (
        session.execute(
            select(PeriodLock.id).where(PeriodLock.period == _month_start(month), PeriodLock.reopened_at.is_(None))
        ).first()
        is not None
    )


def lock_period(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, month: date, reason: str
) -> uuid.UUID:
    """Close a month: from now on the database refuses any posting dated in it (SQLSTATE AH003)."""
    text_reason = (reason or "").strip()
    if len(text_reason) < 3:
        raise DomainError("reason_required", "closing a month needs a reason")
    period = _month_start(month)
    if period >= _month_start(business_date()) and period != _month_start(business_date()):
        raise DomainError("future_period", "a month in the future cannot be closed")
    if is_locked(session, period):
        raise ConflictError("already_locked", f"{period.strftime('%B %Y')} is already closed")
    lock_id = uuid.uuid4()
    session.execute(
        pg_insert(PeriodLock).values(
            id=lock_id,
            organization_id=organization_id,
            period=period,
            locked_by=actor_id,
            reason=text_reason,
            created_by=actor_id,
        )
    )
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="period.lock",
        entity_type="period_lock",
        entity_id=lock_id,
        after={"period": period, "reason": text_reason},
    )
    return lock_id


def reopen_period(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, month: date, reason: str
) -> None:
    """Reopen a closed month with a reason. The lock row stays, with who reopened it, when and why."""
    text_reason = (reason or "").strip()
    if len(text_reason) < 3:
        raise DomainError("reason_required", "reopening a month needs a reason")
    period = _month_start(month)
    lock = session.execute(
        select(PeriodLock).where(PeriodLock.period == period, PeriodLock.reopened_at.is_(None)).with_for_update()
    ).scalar_one_or_none()
    if lock is None:
        raise ConflictError("not_locked", f"{period.strftime('%B %Y')} is not closed")
    lock.reopened_at = func.now()
    lock.reopened_by = actor_id
    lock.reopen_reason = text_reason
    session.flush()
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="period.reopen",
        entity_type="period_lock",
        entity_id=lock.id,
        before={"period": period, "active": True},
        after={"period": period, "active": False},
        note=text_reason,
    )


def stock_lines_export(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """MP11 evidence pack: every stock line of the range with its journal, source document and lot."""
    rows = session.execute(
        text(
            """
            SELECT j.posting_date, j.kind, j.source_type, j.source_id, j.id, sl.line_no, i.code, l.code, lt.lot_no,
                   sl.qty_base, sl.value, j.reason
              FROM stock_lines sl
              JOIN stock_journals j ON j.id = sl.journal_id
              JOIN items i ON i.id = sl.item_id
              JOIN locations l ON l.id = sl.location_id
              LEFT JOIN lots lt ON lt.id = sl.lot_id
             WHERE j.posting_date BETWEEN :f AND :t
             ORDER BY j.posting_date, j.posted_at, j.id, sl.line_no
            """
        ),
        {"f": date_from, "t": date_to},
    ).all()
    keys = (
        "posting_date",
        "kind",
        "source_type",
        "source_id",
        "journal_id",
        "line_no",
        "item",
        "location",
        "lot",
        "qty_base",
        "value",
        "reason",
    )
    return [dict(zip(keys, (str(v) if v is not None else None for v in r), strict=True)) for r in rows]


def over_reserved(session: Session) -> list[dict[str, str]]:
    """Integrity (MP09): no store position may have more ACTIVE reservations than it holds on hand. Empty means
    every promise is covered by stock (sees all orgs as the owner)."""
    rows = session.execute(
        text(
            """
            WITH r AS (
              SELECT organization_id, item_id, location_id, sum(qty_base) AS reserved
                FROM reservations WHERE status = 'ACTIVE' GROUP BY organization_id, item_id, location_id
            ), b AS (
              SELECT organization_id, item_id, location_id, sum(qty_base) AS on_hand
                FROM inventory_balances GROUP BY organization_id, item_id, location_id
            )
            SELECT r.organization_id, r.item_id, r.reserved, coalesce(b.on_hand, 0)
              FROM r LEFT JOIN b USING (organization_id, item_id, location_id)
             WHERE r.reserved > coalesce(b.on_hand, 0)
            """
        )
    ).all()
    return [
        {"organization_id": str(o), "item_id": str(i), "reserved": str(normalise(r)), "on_hand": str(normalise(h))}
        for o, i, r, h in rows
    ]


def items_held_at(session: Session, location_codes: Sequence[str]) -> list[uuid.UUID]:
    """Items with a non-zero quantity summed over the given locations."""
    return list(
        session.execute(
            select(InventoryBalance.item_id)
            .join(Location, Location.id == InventoryBalance.location_id)
            .where(Location.code.in_(list(location_codes)))
            .group_by(InventoryBalance.item_id)
            .having(func.sum(InventoryBalance.qty_base) != 0)
        ).scalars()
    )


def balances(
    session: Session,
    *,
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,
    include_virtual: bool = False,
    include_zero: bool = False,
) -> list[dict[str, Any]]:
    query = (
        select(InventoryBalance, Location.code, Lot.lot_no, Lot.best_before)
        .join(Location, Location.id == InventoryBalance.location_id)
        .outerjoin(Lot, Lot.id == InventoryBalance.lot_id)
        .order_by(Location.code, InventoryBalance.item_id, Lot.lot_no)
    )
    if item_id is not None:
        query = query.where(InventoryBalance.item_id == item_id)
    if location_id is not None:
        query = query.where(InventoryBalance.location_id == location_id)
    if lot_id is not None:
        query = query.where(InventoryBalance.lot_id == lot_id)
    if not include_virtual:
        query = query.where(InventoryBalance.location_kind == "STORE")
    if not include_zero:
        query = query.where((InventoryBalance.qty_base != 0) | (InventoryBalance.value != 0))
    rows = session.execute(query).all()
    item_ids = {b.item_id for b, *_ in rows}
    units = catalog.units_for(session, item_ids)
    codes = catalog.codes_for(session, item_ids)
    return [
        {
            "item_id": str(b.item_id),
            "item_code": codes[b.item_id],
            "location_id": str(b.location_id),
            "location": code,
            "location_kind": b.location_kind,
            "lot_id": None if b.lot_id is None else str(b.lot_id),
            "lot_no": lot_no,
            "best_before": None if best_before is None else best_before.isoformat(),
            **_qty_view(b.qty_base, units[b.item_id]),
            "value": str(b.value),
            "updated_at": b.updated_at.isoformat(),
        }
        for b, code, lot_no, best_before in rows
    ]


def stock_ledger(
    session: Session,
    *,
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Stock movements in posting order with an opening balance and a running balance per item, and the source
    document of every row. The running balance covers exactly the locations and lots the filter selects."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise DomainError("bad_date_range", "date_from is after date_to")

    def filtered(query: Any) -> Any:
        if item_id is not None:
            query = query.where(StockLine.item_id == item_id)
        if location_id is not None:
            query = query.where(StockLine.location_id == location_id)
        if lot_id is not None:
            query = query.where(StockLine.lot_id == lot_id)
        return query

    opening: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
    if date_from is not None:
        query = filtered(
            select(StockLine.item_id, func.sum(StockLine.qty_base), func.sum(StockLine.value))
            .join(StockJournal, StockJournal.id == StockLine.journal_id)
            .where(StockJournal.posting_date < date_from)
            .group_by(StockLine.item_id)
        )
        opening = {i: (Decimal(q), Decimal(v)) for i, q, v in session.execute(query).all()}

    query = filtered(
        select(StockLine, StockJournal, Location.code)
        .join(StockJournal, StockJournal.id == StockLine.journal_id)
        .join(Location, Location.id == StockLine.location_id)
    )
    if date_from is not None:
        query = query.where(StockJournal.posting_date >= date_from)
    if date_to is not None:
        query = query.where(StockJournal.posting_date <= date_to)
    query = query.order_by(StockJournal.posting_date, StockJournal.posted_at, StockJournal.id, StockLine.line_no)
    fetched = session.execute(query.limit(limit + 1)).all()
    truncated = len(fetched) > limit
    fetched = fetched[:limit]

    rows = domain.with_running_balance(
        (
            domain.LedgerRow(
                journal_id=j.id,
                line_no=ln.line_no,
                item_id=ln.item_id,
                location=code,
                lot_id=ln.lot_id,
                posting_date=j.posting_date,
                kind=j.kind,
                source_type=j.source_type,
                source_id=j.source_id,
                qty_base=ln.qty_base,
                value=ln.value,
            )
            for ln, j, code in fetched
        ),
        opening,
    )
    item_ids = {r.item_id for r in rows} | set(opening)
    units = catalog.units_for(session, item_ids)
    codes = catalog.codes_for(session, item_ids)
    reasons = {j.id: (j.reason, j.reverses_journal_id) for _, j, _ in fetched}
    return {
        "opening": [
            {"item_id": str(i), "item_code": codes[i], **_qty_view(q, units[i]), "value": str(v)}
            for i, (q, v) in sorted(opening.items(), key=lambda kv: codes[kv[0]])
        ],
        "rows": [
            {
                "journal_id": str(r.journal_id),
                "line_no": r.line_no,
                "posting_date": r.posting_date.isoformat(),
                "kind": r.kind,
                "source": {"type": r.source_type, "id": str(r.source_id)},
                "reason": reasons[r.journal_id][0],
                "reverses_journal_id": None if reasons[r.journal_id][1] is None else str(reasons[r.journal_id][1]),
                "item_id": str(r.item_id),
                "item_code": codes[r.item_id],
                "location": r.location,
                "lot_id": None if r.lot_id is None else str(r.lot_id),
                **_qty_view(r.qty_base, units[r.item_id]),
                "value": str(r.value),
                "running": {**_qty_view(r.running_qty_base, units[r.item_id]), "value": str(r.running_value)},
            }
            for r in rows
        ],
        "truncated": truncated,
    }


# ---------- integrity (make integrity, the state-machine test) ----------


def journal_imbalances(session: Session) -> list[dict[str, str]]:
    """Law 1 and law 2 re-summed from the stored lines: every (journal, item) with Σ qty != 0, every journal with
    Σ value != 0. Empty means the law holds. Sees what the session may see (all organizations as the owner)."""
    qty = session.execute(
        text(
            "SELECT organization_id, journal_id, item_id, sum(qty_base) FROM stock_lines"
            " GROUP BY organization_id, journal_id, item_id HAVING sum(qty_base) <> 0"
        )
    ).all()
    value = session.execute(
        text(
            "SELECT organization_id, journal_id, sum(value) FROM stock_lines"
            " GROUP BY organization_id, journal_id HAVING sum(value) <> 0"
        )
    ).all()
    return [
        {"organization_id": str(o), "journal_id": str(j), "item_id": str(i), "qty_sum": str(q)} for o, j, i, q in qty
    ] + [{"organization_id": str(o), "journal_id": str(j), "value_sum": str(v)} for o, j, v in value]


_NO_LOT = "'00000000-0000-0000-0000-000000000000'::uuid"


def projection_diff(session: Session) -> list[dict[str, str | None]]:
    """Rebuild every balance from `stock_lines` and diff it with `inventory_balances`. Diff only, never repair:
    nothing may write a balance directly (CLAUDE.md). Empty means the projection is exact."""
    rows = session.execute(
        text(
            f"""
            WITH rebuilt AS (
              SELECT organization_id, item_id, location_id, coalesce(lot_id, {_NO_LOT}) AS lot_key,
                     sum(qty_base) AS qty, sum(value) AS value
                FROM stock_lines GROUP BY 1, 2, 3, 4
            ), projected AS (
              SELECT organization_id, item_id, location_id, coalesce(lot_id, {_NO_LOT}) AS lot_key, qty_base, value
                FROM inventory_balances
            )
            SELECT coalesce(r.organization_id, p.organization_id), coalesce(r.item_id, p.item_id),
                   coalesce(r.location_id, p.location_id), coalesce(r.lot_key, p.lot_key),
                   coalesce(r.qty, 0), coalesce(p.qty_base, 0), coalesce(r.value, 0), coalesce(p.value, 0)
              FROM rebuilt r
              FULL OUTER JOIN projected p
                ON r.organization_id = p.organization_id AND r.item_id = p.item_id
               AND r.location_id = p.location_id AND r.lot_key = p.lot_key
             WHERE coalesce(r.qty, 0) <> coalesce(p.qty_base, 0) OR coalesce(r.value, 0) <> coalesce(p.value, 0)
            """  # noqa: S608 - constant SQL, no user input
        )
    ).all()
    return [
        {
            "organization_id": str(o),
            "item_id": str(i),
            "location_id": str(loc),
            "lot_id": None if str(lot) == _NO_LOT.split("'")[1] else str(lot),
            "rebuilt_qty": str(rq),
            "projected_qty": str(pq),
            "rebuilt_value": str(rv),
            "projected_value": str(pv),
        }
        for o, i, loc, lot, rq, pq, rv, pv in rows
    ]
