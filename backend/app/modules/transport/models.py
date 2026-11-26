"""Vehicles, trips, trip stops and transport costs (MP14, ADR-0021; migration 0013 adds running costs and trip
numbers). Transport costs are management figures: they never post to the stock ledger."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Money, OrgScoped, Qty, in_list, uuid_pk

COST_KINDS = ("FUEL", "DRIVER", "TOLL", "FIXED")
TRIP_STATUSES = ("PLANNED", "DONE")


class Vehicle(OrgScoped, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("organization_id", "name"),
        CheckConstraint("capacity_cartons > 0", name="capacity_positive"),
        CheckConstraint(
            "fuel_l_per_100km >= 0 AND driver_allowance >= 0 AND fixed_cost >= 0", name="running_costs_not_negative"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_cartons: Mapped[int] = mapped_column(Integer, nullable=False)
    fuel_l_per_100km: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default="0")
    driver_allowance: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    fixed_cost: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")


class Trip(OrgScoped, Base):
    __tablename__ = "trips"
    __table_args__ = (
        UniqueConstraint("organization_id", "trip_no"),
        CheckConstraint("planned_km IS NULL OR planned_km >= 0", name="planned_not_negative"),
        CheckConstraint("actual_km IS NULL OR actual_km >= 0", name="actual_not_negative"),
        CheckConstraint(in_list("status", TRIP_STATUSES), name="status"),
        CheckConstraint("tolls >= 0", name="tolls_not_negative"),
        CheckConstraint("status <> 'DONE' OR actual_km IS NOT NULL", name="done_has_actual_km"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    trip_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_km: Mapped[Decimal | None] = mapped_column(Qty)
    actual_km: Mapped[Decimal | None] = mapped_column(Qty)
    trip_no: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PLANNED")
    tolls: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")


class TripStop(OrgScoped, Base):
    __tablename__ = "trip_stops"
    __table_args__ = (UniqueConstraint("trip_id", "seq"), UniqueConstraint("dispatch_id"))

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
