"""Two-level BOM (ADR-0003): recipes make bulk per batch; pack specs pack bulk per good unit.

Versions are DRAFT → ACTIVE → RETIRED. Once a version leaves DRAFT, its lines are frozen (DB trigger).
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, OrgScoped, Pct, Qty, in_list, uuid_pk

VERSION_STATUSES = ("DRAFT", "ACTIVE", "RETIRED")


class Recipe(OrgScoped, Base):
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    bulk_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)


class RecipeVersion(OrgScoped, Base):
    __tablename__ = "recipe_versions"
    __table_args__ = (
        UniqueConstraint("recipe_id", "version"),
        CheckConstraint(in_list("status", VERSION_STATUSES), name="status"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("bulk_yield_g > 0", name="bulk_yield_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recipes.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="DRAFT")
    bulk_yield_g: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class RecipeLine(OrgScoped, Base):
    __tablename__ = "recipe_lines"
    __table_args__ = (
        UniqueConstraint("recipe_version_id", "item_id"),
        CheckConstraint("qty_base > 0", name="qty_positive"),
        CheckConstraint("driver = 'PER_BATCH'", name="driver"),
        CheckConstraint("tolerance_pct IS NULL OR tolerance_pct >= 0", name="tolerance_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipe_versions.id"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    driver: Mapped[str] = mapped_column(Text, nullable=False, server_default="PER_BATCH")
    tolerance_pct: Mapped[Decimal | None] = mapped_column(Pct)


class PackSpec(OrgScoped, Base):
    __tablename__ = "pack_specs"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recipes.id"), nullable=False)
    fg_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)


class PackSpecVersion(OrgScoped, Base):
    __tablename__ = "pack_spec_versions"
    __table_args__ = (
        UniqueConstraint("pack_spec_id", "version"),
        CheckConstraint(in_list("status", VERSION_STATUSES), name="status"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("net_g > 0", name="net_positive"),
        CheckConstraint("shelf_life_days > 0", name="shelf_life_positive"),
        CheckConstraint("units_per_carton > 0", name="units_per_carton_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    pack_spec_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pack_specs.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="DRAFT")
    net_g: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    shelf_life_days: Mapped[int] = mapped_column(Integer, nullable=False)
    units_per_carton: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class PackSpecLine(OrgScoped, Base):
    __tablename__ = "pack_spec_lines"
    __table_args__ = (
        UniqueConstraint("pack_spec_version_id", "item_id"),
        CheckConstraint("qty_per_good_unit > 0", name="qty_positive"),
        CheckConstraint("driver = 'PER_GOOD_UNIT'", name="driver"),
        CheckConstraint("tolerance_pct IS NULL OR tolerance_pct >= 0", name="tolerance_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    pack_spec_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pack_spec_versions.id"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)
    qty_per_good_unit: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    driver: Mapped[str] = mapped_column(Text, nullable=False, server_default="PER_GOOD_UNIT")
    tolerance_pct: Mapped[Decimal | None] = mapped_column(Pct)
