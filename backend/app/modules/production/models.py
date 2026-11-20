"""Production runs, material issues, pack lines and run costs.

A run freezes `recipe_snapshot` and `pack_snapshot` when it starts (invariant D2); a DB trigger blocks any later
change to them and limits what may change after completion.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Money, OrgScoped, Pct, Qty, in_list, same_org_fk, uuid_pk

RUN_STATUSES = ("DRAFT", "IN_PROGRESS", "COMPLETED", "REVERSED", "CANCELLED")
COST_STATUSES = ("PROVISIONAL", "FINAL")
ISSUE_DIRECTIONS = ("ISSUE", "RETURN")
RUN_COST_KINDS = ("LABOUR", "GAS_POWER", "OTHER")


class ProductionRun(OrgScoped, Base):
    __tablename__ = "production_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "run_no"),
        UniqueConstraint("id", "organization_id"),
        CheckConstraint(in_list("status", RUN_STATUSES), name="status"),
        CheckConstraint(in_list("cost_status", COST_STATUSES), name="cost_status"),
        CheckConstraint("batch_multiplier > 0", name="batch_multiplier_positive"),
        CheckConstraint("scrap_g >= 0 AND loss_g >= 0", name="scrap_not_negative"),
        CheckConstraint(
            "status IN ('DRAFT', 'CANCELLED') OR (recipe_snapshot IS NOT NULL AND pack_snapshot IS NOT NULL)",
            name="started_run_has_snapshots",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_no: Mapped[str] = mapped_column(Text, nullable=False)
    recipe_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipe_versions.id"), nullable=False
    )
    batch_multiplier: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    recipe_snapshot: Mapped[Any | None] = mapped_column(JSONB)
    pack_snapshot: Mapped[Any | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="DRAFT")
    cost_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PROVISIONAL")
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scrap_g: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    loss_g: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    scrap_reason: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class RunPackLine(OrgScoped, Base):
    __tablename__ = "run_pack_lines"
    __table_args__ = (
        UniqueConstraint("lot_id"),
        same_org_fk("run_id", "production_runs"),
        same_org_fk("lot_id", "lots"),
        CheckConstraint("bulk_allocated_g > 0", name="bulk_positive"),
        CheckConstraint("expected_units > 0", name="expected_positive"),
        CheckConstraint("good_units IS NULL OR good_units >= 0", name="good_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    pack_spec_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pack_spec_versions.id"), nullable=False
    )
    bulk_allocated_g: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    expected_units: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    good_units: Mapped[int | None] = mapped_column(Integer)
    packaging_actual: Mapped[Any | None] = mapped_column(JSONB)
    damage: Mapped[Any | None] = mapped_column(JSONB)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class MaterialIssue(OrgScoped, Base):
    """An issue (or return) of raw material for a run. Posted on insert; insert-only."""

    __tablename__ = "material_issues"
    __table_args__ = (
        UniqueConstraint("organization_id", "issue_no"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("run_id", "production_runs"),
        same_org_fk("journal_id", "stock_journals"),
        CheckConstraint(in_list("direction", ISSUE_DIRECTIONS), name="direction"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    issue_no: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    journal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class MaterialIssueLine(OrgScoped, Base):
    __tablename__ = "material_issue_lines"
    __table_args__ = (
        UniqueConstraint("issue_id", "item_id"),
        same_org_fk("issue_id", "material_issues"),
        same_org_fk("item_id", "items"),
        CheckConstraint("qty_base > 0", name="qty_positive"),
        CheckConstraint("value >= 0", name="value_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)


class RunCost(OrgScoped, Base):
    """Direct conversion cost of a run (labour, gas/power). Late costs reach the lot via a COST_TRUE_UP journal."""

    __tablename__ = "run_costs"
    __table_args__ = (
        same_org_fk("run_id", "production_runs"),
        same_org_fk("journal_id", "stock_journals"),
        CheckConstraint(in_list("kind", RUN_COST_KINDS), name="kind"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False, server_default="DIRECT")
    incurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class FillWeightSample(OrgScoped, Base):
    __tablename__ = "fill_weight_samples"
    __table_args__ = (
        same_org_fk("run_id", "production_runs"),
        CheckConstraint("gross_g > 0 AND net_g > 0 AND net_g <= gross_g", name="weights_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    gross_g: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    net_g: Mapped[Decimal] = mapped_column(Qty, nullable=False)


class OilSession(OrgScoped, Base):
    __tablename__ = "oil_sessions"
    __table_args__ = (
        same_org_fk("run_id", "production_runs"),
        CheckConstraint("fresh_ml >= 0 AND topup_ml >= 0 AND discard_ml >= 0", name="volumes_not_negative"),
        CheckConstraint("tpc_pct IS NULL OR (tpc_pct >= 0 AND tpc_pct <= 100)", name="tpc_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fresh_ml: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    topup_ml: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    discard_ml: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    tpc_pct: Mapped[Decimal | None] = mapped_column(Pct)
