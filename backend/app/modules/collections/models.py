"""Customer payments and their allocation to invoices.

Unallocated (advance) amount is computed as amount - Σ allocations; it is never stored, so a posted payment
row never changes. A DB trigger keeps Σ allocations ≤ payment amount and ≤ invoice total (invariant D5).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base, Money, OrgScoped, in_list, same_org_fk, uuid_pk

MODES = ("CASH", "UPI", "BANK", "CHEQUE")


class Payment(OrgScoped, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("organization_id", "payment_no"),
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("customer_id", "customers"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(in_list("mode", MODES), name="mode"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    payment_no: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PaymentAllocation(OrgScoped, Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        same_org_fk("payment_id", "payments"),
        same_org_fk("invoice_id", "invoices"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
