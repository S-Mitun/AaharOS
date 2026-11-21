"""Catalog use cases available from MP04: create an item and look up what the ledger needs about its units.

Full master-data management (HSN, pack links, price lists) arrives with MP05. Other modules call only this file.
"""

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog.models import ITEM_KINDS, Item
from app.modules.uom import service as uom
from app.modules.uom.domain import ItemUnits, unit


def create_item(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    code: str,
    name: str,
    kind: str,
    base_uom: str,
    stock_uom: str,
    lot_tracked: bool = False,
) -> uuid.UUID:
    """Insert one item in the caller's transaction (the caller commits). Units must share a dimension."""
    if kind not in ITEM_KINDS:
        raise DomainError("unknown_item_kind", f"item kind must be one of {', '.join(ITEM_KINDS)}")
    base, stock = unit(base_uom), unit(stock_uom)
    if base.to_base != 1:
        raise DomainError("not_a_base_unit", f"{base_uom} is not a base unit (g, mL or piece)")
    if base.dimension != stock.dimension:
        raise DomainError("cross_dimension", f"stock unit {stock_uom} is not a {base.dimension} unit")
    item_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                _insert_item(item_id, organization_id, actor_id, code, name, kind, base_uom, stock_uom, lot_tracked)
            )
    except DBAPIError as exc:
        err = domain_error_from_db(exc)
        if err is None:
            raise
        if err.code == "duplicate":
            raise DomainError("item_code_taken", f"an item with code {code!r} already exists", {"code": code}) from exc
        raise err from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="item.create",
        entity_type="item",
        entity_id=item_id,
        after={"code": code, "kind": kind, "base_uom": base_uom, "stock_uom": stock_uom, "lot_tracked": lot_tracked},
    )
    return item_id


def _insert_item(
    item_id: uuid.UUID,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    code: str,
    name: str,
    kind: str,
    base_uom: str,
    stock_uom: str,
    lot_tracked: bool,
) -> Any:
    return insert(Item).values(
        id=item_id,
        organization_id=organization_id,
        code=code,
        name=name,
        kind=kind,
        base_uom=base_uom,
        stock_uom=stock_uom,
        lot_tracked=lot_tracked,
        created_by=actor_id,
    )


def units_for(session: Session, item_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, ItemUnits]:
    """Units, lot tracking and density for each item (visible to this organization). Unknown ids raise 404."""
    wanted = set(item_ids)
    if not wanted:
        return {}
    rows = session.execute(
        select(Item.id, Item.base_uom, Item.stock_uom, Item.lot_tracked).where(Item.id.in_(wanted))
    ).all()
    missing = wanted - {r.id for r in rows}
    if missing:
        raise NotFoundError("item_not_found", "unknown item", {"item_ids": sorted(str(m) for m in missing)})
    density = uom.densities(session, ((r.id, r.base_uom) for r in rows))
    return {
        r.id: ItemUnits(
            base_uom=r.base_uom, stock_uom=r.stock_uom, lot_tracked=r.lot_tracked, density=density.get(r.id)
        )
        for r in rows
    }


def hsn_for(session: Session, item_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    """The HSN code per item (MP10: the GST rule is found by HSN). None where it is not set."""
    wanted = set(item_ids)
    if not wanted:
        return {}
    return dict(session.execute(select(Item.id, Item.hsn).where(Item.id.in_(wanted))).tuples().all())


def set_hsn(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, item_id: uuid.UUID, hsn: str
) -> None:
    """Master data: an item's HSN code (digits only, 4 to 8), audited."""
    code = hsn.strip()
    if not code.isdigit() or not 4 <= len(code) <= 8:
        raise DomainError("bad_hsn", "an HSN code is 4 to 8 digits")
    item = session.execute(select(Item).where(Item.id == item_id)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("item_not_found", "unknown item")
    before = item.hsn
    item.hsn = code
    session.flush()
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="item.hsn",
        entity_type="item",
        entity_id=item_id,
        before={"hsn": before},
        after={"hsn": code},
    )


def codes_for(session: Session, item_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    wanted = set(item_ids)
    if not wanted:
        return {}
    return dict(session.execute(select(Item.id, Item.code).where(Item.id.in_(wanted))).tuples().all())


def names_for(session: Session, item_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
    """(code, name) per item visible to this organization."""
    wanted = set(item_ids)
    if not wanted:
        return {}
    rows = session.execute(select(Item.id, Item.code, Item.name).where(Item.id.in_(wanted))).tuples().all()
    return {i: (c, n) for i, c, n in rows}


def id_by_code(session: Session, code: str) -> uuid.UUID:
    found = session.execute(select(Item.id).where(Item.code == code)).scalar_one_or_none()
    if found is None:
        raise NotFoundError("item_not_found", f"unknown item {code!r}")
    return found


def kinds_for(session: Session, item_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    """RAW, PACK, BULK or FG per item (visible to this organization). Unknown ids raise 404."""
    wanted = set(item_ids)
    found = (
        dict(session.execute(select(Item.id, Item.kind).where(Item.id.in_(wanted))).tuples().all()) if wanted else {}
    )
    if set(found) != wanted:
        raise NotFoundError("item_not_found", "unknown item", {"item_ids": sorted(str(m) for m in wanted - set(found))})
    return found
