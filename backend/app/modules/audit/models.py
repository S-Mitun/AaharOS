"""Hash-chained audit log (ADR-0007). Insert-only: a trigger blocks UPDATE and DELETE."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, LargeBinary, PrimaryKeyConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base, OrgScoped


class AuditLog(OrgScoped, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "seq"),
        CheckConstraint("seq >= 1", name="seq_positive"),
        CheckConstraint("octet_length(prev_hash) = 32 AND octet_length(hash) = 32", name="sha256_lengths"),
    )

    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary: Mapped[Any] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class AuditChainHead(OrgScoped, Base):
    """One row per organization, locked FOR UPDATE by `audit.record()` so writers cannot fork the chain."""

    __tablename__ = "audit_chain_heads"
    __table_args__ = (PrimaryKeyConstraint("organization_id"),)

    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
