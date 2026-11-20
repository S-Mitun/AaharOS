"""Kernel tables every module may use: effective-dated settings, document numbering, idempotency, outbox."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, Integer, LargeBinary, PrimaryKeyConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.core.db import Base, OrgScoped, uuid_pk


class Setting(OrgScoped, Base):
    """Effective-dated configuration: tolerance %, e-way threshold, FSSAI no., GSTIN, Udyam no. (CLAUDE.md rule)."""

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_range"),
        ExcludeConstraint(  # type: ignore[no-untyped-call]
            ("organization_id", "="),
            ("key", "="),
            (text("daterange(effective_from, effective_to, '[]')"), "&&"),
            name="ex_settings_no_overlap",
            using="gist",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)


class NumberSequence(OrgScoped, Base):
    """Gapless document numbers per (organization, doc type, financial year). Use `aahar_next_doc_number()`."""

    __tablename__ = "number_sequences"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "doc_type", "fy"),
        CheckConstraint("next_value >= 1", name="next_value_positive"),
        CheckConstraint("fy ~ '^[0-9]{2}-[0-9]{2}$'", name="fy_format"),
    )

    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    fy: Mapped[str] = mapped_column(Text, nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False)


class IdempotencyKey(OrgScoped, Base):
    """One client key → one effect (invariant D4)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (PrimaryKeyConstraint("organization_id", "key"),)

    key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSONB)


class OutboxEvent(OrgScoped, Base):
    """Events written in the same transaction as the change, published later."""

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
