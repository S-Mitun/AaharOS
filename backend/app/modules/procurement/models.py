"""Suppliers and purchase receipts. A receipt is editable while DRAFT; once POSTED only a reversal changes it."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Money, OrgScoped, Qty, UnitCost, in_list, same_org_fk, uuid_pk

RECEIPT_STATUSES = ("DRAFT", "POSTED", "REVERSED")


class Supplier(OrgScoped, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        CheckConstraint("state_code ~ '^[0-9]{2}$'", name="state_code_format"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    gstin: Mapped[str | None] = mapped_column(Text)


class PurchaseReceipt(OrgScoped, Base):
    __tablename__ = "purchase_receipts"
    __table_args__ = (
        UniqueConstraint("organization_id", "receipt_no"),
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("journal_id", "stock_journals"),
        CheckConstraint(in_list("status", RECEIPT_STATUSES), name="status"),
        CheckConstraint("status = 'DRAFT' OR (journal_id IS NOT NULL AND posted_at IS NOT NULL)", name="posted_link"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    receipt_no: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)
    supplier_invoice_ref: Mapped[str | None] = mapped_column(Text)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="DRAFT")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    journal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PurchaseReceiptLine(OrgScoped, Base):
    __tablename__ = "purchase_receipt_lines"
    __table_args__ = (
        UniqueConstraint("receipt_id", "line_no"),
        same_org_fk("receipt_id", "purchase_receipts"),
        same_org_fk("item_id", "items"),
        CheckConstraint("qty_entered > 0 AND qty_base > 0", name="qty_positive"),
        CheckConstraint("rate >= 0 AND value >= 0 AND freight >= 0", name="money_not_negative"),
        CheckConstraint("accepted_base >= 0 AND rejected_base >= 0", name="split_not_negative"),
        CheckConstraint("accepted_base + rejected_base = qty_base", name="split_adds_up"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_entered: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    uom_entered: Mapped[str] = mapped_column(Text, ForeignKey("uoms.code"), nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    rate: Mapped[Decimal] = mapped_column(UnitCost, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    freight: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    accepted_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    rejected_base: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    lot_no: Mapped[str | None] = mapped_column(Text)
