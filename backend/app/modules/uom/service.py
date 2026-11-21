"""Unit lookups that need the database: the seeded system units and per-item densities.

Other modules call only this file (module rule in CLAUDE.md). The conversion rules themselves are in domain.py.
"""

import uuid
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.uom.domain import BASE_UNIT, Unit
from app.modules.uom.models import Uom, UomConversion


def seeded_units(session: Session) -> dict[str, Unit]:
    """The `uoms` table as domain units (a test keeps it equal to `domain.SYSTEM_UNITS`)."""
    return {u.code: Unit(u.code, u.dimension, u.to_base) for u in session.execute(select(Uom)).scalars()}


def densities(session: Session, items: Iterable[tuple[uuid.UUID, str]]) -> dict[uuid.UUID, Decimal]:
    """Explicit MASS <-> VOLUME factors per item: base units of the item per base unit of the other dimension.

    `items` is (item id, item base uom). A density row is `item_id` set, `to_uom` = the item's base unit and
    `from_uom` = the base unit of the other dimension (g -> mL for an oil counted in mL).
    """
    wanted = dict(items)
    if not wanted:
        return {}
    other = {"g": BASE_UNIT["VOLUME"], "mL": BASE_UNIT["MASS"]}
    rows = session.execute(select(UomConversion).where(UomConversion.item_id.in_(list(wanted)))).scalars()
    found: dict[uuid.UUID, Decimal] = {}
    for row in rows:
        assert row.item_id is not None  # the query filters on it
        base = wanted[row.item_id]
        if row.to_uom == base and row.from_uom == other.get(base):
            found[row.item_id] = row.factor
    return found
