"""Effective-dated GST rules by HSN. Overlapping date ranges for one HSN are rejected by an EXCLUDE constraint."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.core.db import Base, OrgScoped, Pct, uuid_pk


class TaxRule(OrgScoped, Base):
    __tablename__ = "tax_rules"
    __table_args__ = (
        CheckConstraint("rate_pct >= 0 AND rate_pct <= 100", name="rate_range"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_range"),
        ExcludeConstraint(  # type: ignore[no-untyped-call]
            ("organization_id", "="),
            ("hsn", "="),
            (text("daterange(effective_from, effective_to, '[]')"), "&&"),
            name="ex_tax_rules_no_overlap",
            using="gist",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    hsn: Mapped[str] = mapped_column(Text, nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
