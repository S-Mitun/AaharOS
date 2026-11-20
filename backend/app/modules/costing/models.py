"""Standard cost cards and variance results. Books are at actual cost; variances are explicit rows (ledger.md §4)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base, Money, OrgScoped, Pct, Qty, UnitCost, in_list, same_org_fk, uuid_pk

VARIANCE_KINDS = ("YIELD", "USAGE_BATCH", "USAGE_FLEX", "PRICE", "DAMAGE")
DIRECTIONS = ("FAVOURABLE", "UNFAVOURABLE", "NONE")
COST_LINE_KINDS = ("MATERIAL", "PACKAGING", "CONVERSION")


class StandardCostCard(OrgScoped, Base):
    __tablename__ = "standard_cost_cards"
    __table_args__ = (
        UniqueConstraint("pack_spec_version_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("per_unit >= 0", name="per_unit_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    pack_spec_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pack_spec_versions.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    per_unit: Mapped[Decimal] = mapped_column(UnitCost, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class StandardCostLine(OrgScoped, Base):
    __tablename__ = "standard_cost_lines"
    __table_args__ = (
        CheckConstraint(in_list("cost_kind", COST_LINE_KINDS), name="cost_kind"),
        CheckConstraint("cost_kind = 'CONVERSION' OR item_id IS NOT NULL", name="item_for_materials"),
        CheckConstraint("std_qty_base >= 0 AND std_rate >= 0", name="not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    card_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("standard_cost_cards.id"), nullable=False)
    cost_kind: Mapped[str] = mapped_column(Text, nullable=False)
    item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"))
    label: Mapped[str] = mapped_column(Text, nullable=False)
    std_qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    std_rate: Mapped[Decimal] = mapped_column(UnitCost, nullable=False)


class VarianceResult(OrgScoped, Base):
    __tablename__ = "variance_results"
    __table_args__ = (
        same_org_fk("run_id", "production_runs"),
        CheckConstraint(in_list("kind", VARIANCE_KINDS), name="kind"),
        CheckConstraint(in_list("direction", DIRECTIONS), name="direction"),
        CheckConstraint("kind = 'YIELD' OR item_id IS NOT NULL", name="item_unless_yield"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    standard: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    actual: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    pct: Mapped[Decimal | None] = mapped_column(Pct)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    inr_impact: Mapped[Decimal] = mapped_column(Money, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
