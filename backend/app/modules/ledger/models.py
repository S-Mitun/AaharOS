"""Double-entry stock ledger (ADR-0002, docs/architecture/ledger.md).

Database guards (migration 0003): Σ qty per (journal, item) = 0 and Σ value per journal = 0 (deferred constraint
trigger); journals and lines are insert-only; posting into a locked period is rejected; `inventory_balances` is
maintained by a trigger and is read-only for the application role (ADR-0009).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.core.db import Base, Money, OrgScoped, Qty, in_list, lot_of_item_fk, same_org_fk, uuid_pk

LOCATION_KINDS = ("STORE", "VIRTUAL")
JOURNAL_KINDS = (
    "OPENING",
    "RECEIPT",
    "ISSUE",
    "RETURN",
    "RUN_COMPLETION",
    "COST_TRUE_UP",
    "DISPATCH",
    "SALES_RETURN",
    "ADJUSTMENT",
    "REVERSAL",
)
SOURCE_TYPES = (
    "opening",
    "purchase_receipt",
    "material_issue",
    "production_run",
    "run_cost",
    "dispatch",
    "sales_return",
    "stock_count",
    "stock_journal",
)
LOT_SOURCES = ("opening", "production_run", "purchase_receipt")
# IN: qty > 0, value ≥ 0 · OUT: qty < 0, value ≤ 0 · SCRAP_IN: qty > 0 at no value (normal loss, ADR-0002)
# VALUE_ONLY: qty = 0, value ≠ 0 (cost true-ups and their reversals only)
LINE_ROLES = ("IN", "OUT", "SCRAP_IN", "VALUE_ONLY")
RESERVATION_STATUSES = ("ACTIVE", "CONSUMED", "RELEASED")


class Location(OrgScoped, Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        UniqueConstraint("id", "organization_id"),
        CheckConstraint(in_list("kind", LOCATION_KINDS), name="kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)


class Lot(OrgScoped, Base):
    __tablename__ = "lots"
    __table_args__ = (
        UniqueConstraint("organization_id", "item_id", "lot_no"),
        UniqueConstraint("id", "organization_id"),
        UniqueConstraint("id", "item_id", "organization_id"),  # target of lot_of_item_fk
        same_org_fk("item_id", "items"),
        CheckConstraint(in_list("source_type", LOT_SOURCES), name="source_type"),
        CheckConstraint("best_before IS NULL OR mfg_date IS NULL OR best_before >= mfg_date", name="dates_ordered"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot_no: Mapped[str] = mapped_column(Text, nullable=False)
    mfg_date: Mapped[date | None] = mapped_column(Date)
    best_before: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PeriodLock(OrgScoped, Base):
    """A closed month. `period` is the first day of the month (business date, IST). MP11: a lock is reopened with a
    reason (never deleted); at most one active lock per month (migration 0011)."""

    __tablename__ = "period_locks"
    __table_args__ = (
        CheckConstraint("extract(day FROM period) = 1", name="period_is_month_start"),
        CheckConstraint("length(trim(reason)) > 0", name="reason_required"),
        CheckConstraint(
            "reopened_at IS NULL OR length(trim(coalesce(reopen_reason, ''))) > 0", name="reopen_needs_reason"
        ),
        Index(
            "uq_period_locks_active",
            "organization_id",
            "period",
            unique=True,
            postgresql_where=text("reopened_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    period: Mapped[date] = mapped_column(Date, nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reopen_reason: Mapped[str | None] = mapped_column(Text)


class StockJournal(OrgScoped, Base):
    __tablename__ = "stock_journals"
    __table_args__ = (
        UniqueConstraint("id", "organization_id"),
        UniqueConstraint("reverses_journal_id"),  # a journal is reversed at most once
        UniqueConstraint("organization_id", "idempotency_key"),
        same_org_fk("reverses_journal_id", "stock_journals"),
        CheckConstraint(in_list("kind", JOURNAL_KINDS), name="kind"),
        CheckConstraint(in_list("source_type", SOURCE_TYPES), name="source_type"),
        CheckConstraint("(kind = 'REVERSAL') = (reverses_journal_id IS NOT NULL)", name="reversal_link"),
        CheckConstraint(
            "kind NOT IN ('ADJUSTMENT', 'REVERSAL') OR length(trim(coalesce(reason, ''))) > 0",
            name="reason_required",
        ),
        CheckConstraint("kind <> 'ADJUSTMENT' OR approved_by IS NOT NULL", name="adjustment_approved"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reverses_journal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class StockLine(OrgScoped, Base):
    __tablename__ = "stock_lines"
    __table_args__ = (
        UniqueConstraint("journal_id", "line_no"),
        same_org_fk("journal_id", "stock_journals"),
        same_org_fk("item_id", "items"),
        same_org_fk("location_id", "locations"),
        lot_of_item_fk(),
        CheckConstraint(in_list("line_role", LINE_ROLES), name="line_role"),
        CheckConstraint(
            "(line_role = 'IN' AND qty_base > 0 AND value >= 0)"
            " OR (line_role = 'OUT' AND qty_base < 0 AND value <= 0)"
            " OR (line_role = 'SCRAP_IN' AND qty_base > 0 AND value = 0)"
            " OR (line_role = 'VALUE_ONLY' AND qty_base = 0 AND value <> 0)",
            name="sign_matches_role",
        ),
        Index(None, "organization_id", "item_id", "location_id", "posted_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    journal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    line_role: Mapped[str] = mapped_column(Text, nullable=False)
    # Copied from the journal by a BEFORE INSERT trigger, so the (org, item, location, posted_at) index needs no join.
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InventoryBalance(OrgScoped, Base):
    """Projection of `stock_lines`, maintained only by the `aahar_project_balance` trigger (ADR-0009).

    One row per (organization, item, location, lot); a missing lot counts as one value (NULLS NOT DISTINCT).
    """

    __tablename__ = "inventory_balances"
    __table_args__ = (
        same_org_fk("item_id", "items"),
        same_org_fk("location_id", "locations"),
        lot_of_item_fk(),
        Index(
            "uq_inventory_balances_position",
            "organization_id",
            "item_id",
            "location_id",
            "lot_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(in_list("location_kind", LOCATION_KINDS), name="location_kind"),
        CheckConstraint("location_kind <> 'STORE' OR (qty_base >= 0 AND value >= 0)", name="store_not_negative"),
        CheckConstraint("location_kind <> 'STORE' OR qty_base <> 0 OR value = 0", name="empty_store_has_no_value"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    location_kind: Mapped[str] = mapped_column(Text, nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Reservation(OrgScoped, Base):
    """Finished goods held for an approved order line (item level at FG_STORE; the lot is picked at dispatch)."""

    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("id", "organization_id"),
        same_org_fk("item_id", "items"),
        same_org_fk("location_id", "locations"),
        CheckConstraint("qty_base > 0", name="qty_positive"),
        CheckConstraint(in_list("status", RESERVATION_STATUSES), name="status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("order_lines.id"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ACTIVE")
