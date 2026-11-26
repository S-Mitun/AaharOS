"""Alerts raised by variance, stock and collection checks."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, OrgScoped, Qty, in_list, same_org_fk, uuid_pk

ALERT_KINDS = ("VARIANCE", "LOW_STOCK", "SHORTAGE", "OVERDUE", "EXPIRY")
SEVERITIES = ("INFO", "WARN", "CRITICAL")


class Alert(OrgScoped, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(in_list("kind", ALERT_KINDS), name="kind"),
        CheckConstraint(in_list("severity", SEVERITIES), name="severity"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default="WARN")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[Any | None] = mapped_column(JSONB)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


DRAFT_STATUSES = ("DRAFT", "CANCELLED")


class ItemPlanning(OrgScoped, Base):
    """MP12 (L3): reorder level, safety stock and minimum order in base units, and the lead time, per item."""

    __tablename__ = "item_planning"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "item_id"),
        same_org_fk("item_id", "items"),
        CheckConstraint(
            "reorder_level_base >= 0 AND safety_stock_base >= 0 AND min_order_base >= 0", name="not_negative"
        ),
        CheckConstraint("lead_time_days >= 0 AND lead_time_days <= 365", name="lead_time"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reorder_level_base: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    safety_stock_base: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    min_order_base: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class DraftPurchaseOrder(OrgScoped, Base):
    """MP12 (L5): a purchase the planner suggested and a person approved. Intent only: no stock, no money."""

    __tablename__ = "draft_purchase_orders"
    __table_args__ = (
        UniqueConstraint("organization_id", "draft_no"),
        UniqueConstraint("id", "organization_id"),
        CheckConstraint(in_list("status", DRAFT_STATUSES), name="status"),
        CheckConstraint(
            "status <> 'CANCELLED' OR (cancelled_at IS NOT NULL AND length(trim(coalesce(cancel_reason, ''))) > 0)",
            name="cancel_reason",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    draft_no: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="DRAFT")
    note: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class DraftPurchaseOrderLine(OrgScoped, Base):
    __tablename__ = "draft_purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("draft_id", "line_no"),
        same_org_fk("draft_id", "draft_purchase_orders"),
        same_org_fk("item_id", "items"),
        CheckConstraint("qty_base > 0", name="qty_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    needed_by: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
