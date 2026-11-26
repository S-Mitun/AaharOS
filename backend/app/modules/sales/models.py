"""Customers, versioned price lists, sales orders and their status history."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base, Money, OrgScoped, in_list, same_org_fk, uuid_pk

CUSTOMER_KINDS = ("RETAILER", "DISTRIBUTOR")
ORDER_STATUSES = (
    "SUBMITTED",
    "APPROVED",
    "PART_APPROVED",
    "REJECTED",
    "INVOICED",
    "DISPATCHED",
    "CANCELLED",
)


class Customer(OrgScoped, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        UniqueConstraint("id", "organization_id"),
        CheckConstraint(in_list("kind", CUSTOMER_KINDS), name="kind"),
        CheckConstraint("state_code ~ '^[0-9]{2}$'", name="state_code_format"),
        CheckConstraint("credit_limit >= 0", name="credit_limit_not_negative"),
        CheckConstraint("payment_terms_days >= 0", name="terms_not_negative"),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)"
            " AND (latitude IS NULL OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))",
            name="location_valid",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    gstin: Mapped[str | None] = mapped_column(Text)
    credit_limit: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    msme_terms: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    # MP14 (ADR-0021): an optional location in degrees, for trip planning
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))


class PriceList(OrgScoped, Base):
    __tablename__ = "price_lists"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)


class PriceListItem(OrgScoped, Base):
    __tablename__ = "price_list_items"
    __table_args__ = (
        PrimaryKeyConstraint("price_list_id", "item_id"),
        CheckConstraint("price_ex_tax >= 0", name="price_not_negative"),
    )

    price_list_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("price_lists.id"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)
    price_ex_tax: Mapped[Decimal] = mapped_column(Money, nullable=False)


class SalesOrder(OrgScoped, Base):
    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("organization_id", "order_no"),
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("customer_id", "customers"),
        CheckConstraint(in_list("status", ORDER_STATUSES), name="status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_no: Mapped[str] = mapped_column(Text, nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    salesman_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("price_lists.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="SUBMITTED")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class OrderLine(OrgScoped, Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "line_no"),
        same_org_fk("order_id", "sales_orders"),
        same_org_fk("item_id", "items"),
        CheckConstraint("qty_requested > 0", name="qty_positive"),
        CheckConstraint("qty_approved >= 0 AND qty_backordered >= 0", name="qty_not_negative"),
        CheckConstraint("qty_approved + qty_backordered <= qty_requested", name="split_within_request"),
        CheckConstraint("price_captured >= 0 AND (price_final IS NULL OR price_final >= 0)", name="price_not_negative"),
        CheckConstraint(
            "price_final IS NULL OR price_final = price_captured OR length(trim(coalesce(amend_reason, ''))) > 0",
            name="amend_reason_required",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_approved: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    qty_backordered: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    price_captured: Mapped[Decimal] = mapped_column(Money, nullable=False)
    price_final: Mapped[Decimal | None] = mapped_column(Money)
    amend_reason: Mapped[str | None] = mapped_column(Text)


class OrderStatusHistory(OrgScoped, Base):
    """Insert-only trail of order status changes."""

    __tablename__ = "order_status_history"
    __table_args__ = (
        same_org_fk("order_id", "sales_orders"),
        CheckConstraint("from_status IS NULL OR " + in_list("from_status", ORDER_STATUSES), name="from_status"),
        CheckConstraint(in_list("to_status", ORDER_STATUSES), name="to_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
