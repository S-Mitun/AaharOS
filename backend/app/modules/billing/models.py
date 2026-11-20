"""GST invoices, credit notes and their tax lines (conservation law 4 reads only the tax-line tables).

Invoices are posted on insert. The only allowed change is POSTED → CANCELLED with a reason (DB trigger);
lines and tax lines are insert-only. Corrections are credit notes.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base, Money, OrgScoped, Pct, in_list, same_org_fk, uuid_pk

REGIMES = ("INTRA", "INTER")
INVOICE_STATUSES = ("POSTED", "CANCELLED")
TAXES = ("CGST", "SGST", "IGST")


class Invoice(OrgScoped, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_no"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("customer_id", "customers"),
        same_org_fk("sales_order_id", "sales_orders"),
        CheckConstraint("char_length(invoice_no) <= 16", name="invoice_no_max_16"),
        CheckConstraint(in_list("regime", REGIMES), name="regime"),
        CheckConstraint(in_list("status", INVOICE_STATUSES), name="status"),
        CheckConstraint("(regime = 'INTRA') = (supplier_state = place_of_supply)", name="regime_follows_pos"),
        CheckConstraint("taxable >= 0 AND tax_total >= 0", name="amounts_not_negative"),
        CheckConstraint("total = taxable + tax_total + round_off", name="total_adds_up"),
        CheckConstraint(
            "status <> 'CANCELLED' OR (cancelled_at IS NOT NULL AND length(trim(coalesce(cancel_reason, ''))) > 0)",
            name="cancel_reason_required",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_no: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_state: Mapped[str] = mapped_column(Text, nullable=False)
    place_of_supply: Mapped[str] = mapped_column(Text, nullable=False)
    customer_gstin: Mapped[str | None] = mapped_column(Text)
    regime: Mapped[str] = mapped_column(Text, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    round_off: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="POSTED")
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class InvoiceLine(OrgScoped, Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_no"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("invoice_id", "invoices"),
        same_org_fk("item_id", "items"),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("rate >= 0 AND taxable >= 0", name="amounts_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    hsn: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Money, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)


class InvoiceTaxLine(OrgScoped, Base):
    __tablename__ = "invoice_tax_lines"
    __table_args__ = (
        UniqueConstraint("invoice_line_id", "tax"),
        same_org_fk("invoice_line_id", "invoice_lines"),
        CheckConstraint(in_list("tax", TAXES), name="tax"),
        CheckConstraint("rate_pct >= 0 AND amount >= 0", name="not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tax: Mapped[str] = mapped_column(Text, nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tax_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_rules.id"))


class CreditNote(OrgScoped, Base):
    __tablename__ = "credit_notes"
    __table_args__ = (
        UniqueConstraint("organization_id", "credit_note_no"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("invoice_id", "invoices"),
        CheckConstraint("char_length(credit_note_no) <= 16", name="credit_note_no_max_16"),
        CheckConstraint("length(trim(reason)) > 0", name="reason_required"),
        CheckConstraint("taxable >= 0 AND tax_total >= 0", name="amounts_not_negative"),
        CheckConstraint("total = taxable + tax_total + round_off", name="total_adds_up"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    credit_note_no: Mapped[str] = mapped_column(Text, nullable=False)
    note_date: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    round_off: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CreditNoteLine(OrgScoped, Base):
    __tablename__ = "credit_note_lines"
    __table_args__ = (
        UniqueConstraint("credit_note_id", "line_no"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("credit_note_id", "credit_notes"),
        same_org_fk("invoice_line_id", "invoice_lines"),
        CheckConstraint("qty >= 0", name="qty_not_negative"),
        CheckConstraint("rate >= 0 AND taxable >= 0", name="amounts_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    credit_note_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Money, nullable=False)
    taxable: Mapped[Decimal] = mapped_column(Money, nullable=False)


class CreditNoteTaxLine(OrgScoped, Base):
    __tablename__ = "credit_note_tax_lines"
    __table_args__ = (
        UniqueConstraint("credit_note_line_id", "tax"),
        same_org_fk("credit_note_line_id", "credit_note_lines"),
        CheckConstraint(in_list("tax", TAXES), name="tax"),
        CheckConstraint("rate_pct >= 0 AND amount >= 0", name="not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    credit_note_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tax: Mapped[str] = mapped_column(Text, nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
