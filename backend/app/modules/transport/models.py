"""Vehicles, trips and transport costs (MP14 stretch; schema only)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Money, OrgScoped, Qty, in_list, uuid_pk

COST_KINDS = ("FUEL", "DRIVER", "TOLL", "FIXED")


class Vehicle(OrgScoped, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("organization_id", "name"),
        CheckConstraint("capacity_cartons > 0", name="capacity_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_cartons: Mapped[int] = mapped_column(Integer, nullable=False)


class Trip(OrgScoped, Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("planned_km IS NULL OR planned_km >= 0", name="planned_not_negative"),
        CheckConstraint("actual_km IS NULL OR actual_km >= 0", name="actual_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    trip_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_km: Mapped[Decimal | None] = mapped_column(Qty)
    actual_km: Mapped[Decimal | None] = mapped_column(Qty)


class TripStop(OrgScoped, Base):
    __tablename__ = "trip_stops"
    __table_args__ = (UniqueConstraint("trip_id", "seq"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False)
    dispatch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dispatches.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)


class TransportCost(OrgScoped, Base):
    __tablename__ = "transport_costs"
    __table_args__ = (
        CheckConstraint(in_list("kind", COST_KINDS), name="kind"),
        CheckConstraint("amount >= 0", name="amount_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
