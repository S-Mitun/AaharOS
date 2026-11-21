"""Database kernel: declarative base, column types, the org-scoped mixin and the RLS session helper.

Column types follow ADR-0008: money is NUMERIC(14,2) rupees, quantities NUMERIC(18,6) in base units,
unit costs NUMERIC(18,6). Never float.
"""

import uuid
from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache

from sqlalchemy import (
    Connection,
    DateTime,
    Engine,
    ForeignKey,
    ForeignKeyConstraint,
    MetaData,
    Numeric,
    create_engine,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, SessionTransaction, mapped_column, sessionmaker

from app.core.config import get_settings

# Deterministic constraint names, so migrations and downgrades are stable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Money = Numeric(14, 2, asdecimal=True)
"""Rupees, rounded to paise at posting (ADR-0008)."""
Qty = Numeric(18, 6, asdecimal=True)
"""Quantity in the item's base unit: g, mL or piece."""
UnitCost = Numeric(18, 6, asdecimal=True)
"""A per-unit rate or cost, kept to 6 dp."""
Pct = Numeric(9, 4, asdecimal=True)
"""A percentage such as 5.0000 (GST) or -6.0000 (yield variance)."""


class Base(DeclarativeBase):
    """Declarative base for every module's models.py."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


class OrgScoped:
    """Every business row belongs to one organization. Row-level security filters on this column (ADR-0006)."""

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


def same_org_fk(column: str, parent_table: str) -> ForeignKeyConstraint:
    """A composite FK (column, organization_id) -> parent (id, organization_id).

    Used on stock and money paths so a child row can never point at another tenant's parent,
    even though FK checks themselves bypass row-level security.
    """
    return ForeignKeyConstraint(
        [column, "organization_id"],
        [f"{parent_table}.id", f"{parent_table}.organization_id"],
    )


def lot_of_item_fk(lot_column: str = "lot_id", item_column: str = "item_id") -> ForeignKeyConstraint:
    """A composite FK (lot, item, organization) -> lots, so a row's lot always belongs to that row's item."""
    return ForeignKeyConstraint(
        [lot_column, item_column, "organization_id"],
        ["lots.id", "lots.item_id", "lots.organization_id"],
    )


def in_list(column: str, values: tuple[str, ...]) -> str:
    """SQL text for a CHECK that a text column holds one of a fixed set of codes."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session (and one transaction boundary) per request."""
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        yield session


# session.info key -> PostgreSQL setting read by RLS policies and audit (`aahar_current_org()`, `aahar_current_user()`)
_SCOPE_SETTINGS = (
    ("aahar_org_id", "app.org_id"),
    ("aahar_user_id", "app.user_id"),
)


def _apply_scope(session: Session, connection: Connection) -> None:
    for key, setting in _SCOPE_SETTINGS:
        value = session.info.get(key)
        if value is not None:
            connection.execute(text("SELECT set_config(:k, :v, true)"), {"k": setting, "v": str(value)})


@event.listens_for(Session, "after_begin")
def _reapply_scope(session: Session, _transaction: SessionTransaction, connection: Connection) -> None:
    """Re-apply the scope at the start of every transaction, so a commit inside a request cannot drop it."""
    _apply_scope(session, connection)


def org_scope(session: Session, organization_id: uuid.UUID, user_id: uuid.UUID | None = None) -> None:
    """Bind this session to one organization (and user) for row-level security.

    `set_config(..., true)` is transaction-local (like SET LOCAL), so it cannot leak to the next request that
    reuses the pooled connection. The values live in `session.info` and are re-applied on every new transaction.
    The identity dependency (`require`) calls this once per request, on the same session the route uses.
    """
    session.info["aahar_org_id"] = organization_id
    if user_id is not None:
        session.info["aahar_user_id"] = user_id
    already_open = session.in_transaction()
    connection = session.connection()  # starts a transaction if needed; the after_begin hook applies the scope
    if already_open:
        _apply_scope(session, connection)


def scoped_org(session: Session) -> uuid.UUID | None:
    value = session.info.get("aahar_org_id")
    return value if isinstance(value, uuid.UUID) else None
