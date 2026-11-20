"""Units of measure. System units are global; pack-scoped conversions (carton = 20 packets) belong to an org."""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.core.db import Base, OrgScoped, Qty, in_list, uuid_pk

DIMENSIONS = ("MASS", "VOLUME", "COUNT")


class Uom(Base):
    __tablename__ = "uoms"
    __table_args__ = (
        CheckConstraint(in_list("dimension", DIMENSIONS), name="dimension"),
        CheckConstraint("to_base > 0", name="to_base_positive"),
        CheckConstraint("NOT is_base OR to_base = 1", name="base_unit_factor_one"),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    to_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    is_base: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class UomConversion(OrgScoped, Base):
    """Non-system conversions: carton → packets for one pack spec version, or a density for one item."""

    __tablename__ = "uom_conversions"
    __table_args__ = (
        CheckConstraint("factor > 0", name="factor_positive"),
        CheckConstraint("pack_spec_version_id IS NOT NULL OR item_id IS NOT NULL", name="scoped"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    from_uom: Mapped[str] = mapped_column(Text, ForeignKey("uoms.code"), nullable=False)
    to_uom: Mapped[str] = mapped_column(Text, ForeignKey("uoms.code"), nullable=False)
    factor: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    pack_spec_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pack_spec_versions.id")
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"))
