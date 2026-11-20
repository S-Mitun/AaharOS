"""Export jobs (GSTR-shaped exports, evidence packs)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, OrgScoped, in_list, uuid_pk

JOB_STATUSES = ("QUEUED", "RUNNING", "DONE", "FAILED")


class ExportJob(OrgScoped, Base):
    __tablename__ = "export_jobs"
    __table_args__ = (CheckConstraint(in_list("status", JOB_STATUSES), name="status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    report: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[Any] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="QUEUED")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_path: Mapped[str | None] = mapped_column(Text)
