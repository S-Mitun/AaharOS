"""Valuation state (ADR-0004): the WAC pool per item, and FIFO layers for the sensitivity panel only."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base, Money, OrgScoped, Qty, UnitCost, same_org_fk, uuid_pk


class ItemCostState(OrgScoped, Base):
    """Pooled (qty, value) over the stores. WAC = value / qty is derived, never stored rounded."""

    __tablename__ = "item_cost_state"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "item_id"),
        same_org_fk("item_id", "items"),
        CheckConstraint("qty_base >= 0 AND value >= 0", name="not_negative"),
        CheckConstraint("qty_base <> 0 OR value = 0", name="empty_pool_has_no_value"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ValuationLayer(OrgScoped, Base):
    """A FIFO layer. Sensitivity only: never posts to the ledger."""

    __tablename__ = "valuation_layers"
    __table_args__ = (
        same_org_fk("item_id", "items"),
        CheckConstraint("qty_remaining >= 0", name="qty_not_negative"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    receipt_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_receipt_lines.id")
    )
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    qty_remaining: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(UnitCost, nullable=False)
