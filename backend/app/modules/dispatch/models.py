"""Dispatch notes and their lot picks (FEFO, ADR-0005). Dispatch lines are insert-only."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.core.db import Base, OrgScoped, lot_of_item_fk, same_org_fk, uuid_pk


class Dispatch(OrgScoped, Base):
    __tablename__ = "dispatches"
    __table_args__ = (
        UniqueConstraint("organization_id", "dispatch_no"),
        UniqueConstraint("id", "organization_id"),
        same_org_fk("invoice_id", "invoices"),
        same_org_fk("journal_id", "stock_journals"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dispatch_no: Mapped[str] = mapped_column(Text, nullable=False)
    dispatch_date: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    eway_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    eway_reason: Mapped[str | None] = mapped_column(Text)
    eway_payload: Mapped[Any | None] = mapped_column(JSONB)  # MP10: a MOCK payload, never sent to the portal


class DispatchLine(OrgScoped, Base):
    __tablename__ = "dispatch_lines"
    __table_args__ = (
        same_org_fk("dispatch_id", "dispatches"),
        same_org_fk("reservation_id", "reservations"),
        same_org_fk("item_id", "items"),
        lot_of_item_fk(),
        CheckConstraint("qty > 0", name="qty_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dispatch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
