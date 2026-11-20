"""Items: raw materials, packaging, bulk (unpacked murukku) and finished goods."""

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.core.db import Base, OrgScoped, in_list, uuid_pk

ITEM_KINDS = ("RAW", "PACK", "BULK", "FG")


class Item(OrgScoped, Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        UniqueConstraint("id", "organization_id"),  # target of same-org composite FKs
        CheckConstraint(in_list("kind", ITEM_KINDS), name="kind"),
        CheckConstraint("kind <> 'FG' OR lot_tracked", name="fg_is_lot_tracked"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    base_uom: Mapped[str] = mapped_column(Text, ForeignKey("uoms.code"), nullable=False)
    stock_uom: Mapped[str] = mapped_column(Text, ForeignKey("uoms.code"), nullable=False)
    lot_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hsn: Mapped[str | None] = mapped_column(Text)
