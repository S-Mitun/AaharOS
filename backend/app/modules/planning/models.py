"""Alerts raised by variance, stock and collection checks."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, OrgScoped, in_list, uuid_pk

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
