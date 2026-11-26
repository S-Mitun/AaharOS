"""Transport routes (MP14, ADR-0021): vehicles, the day's trip plan, trips and their actuals, cost-to-serve."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.procurement import service as procurement
from app.modules.sales import service as sales
from app.modules.transport import service

router = APIRouter(prefix="/api/transport", tags=["transport"])
DbSession = Annotated[Session, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("report.read"))]
Dispatcher = Annotated[Principal, Depends(require("dispatch.post"))]
Amount = Annotated[str, StringConstraints(pattern=r"^\d{1,9}(\.\d{1,3})?$")]
Degrees = Annotated[str, StringConstraints(pattern=r"^-?\d{1,3}(\.\d{1,6})?$")]


@router.get("/vehicles")
def vehicles(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return {"vehicles": service.vehicles(session)}


class VehicleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    capacity_cartons: Annotated[int, Field(ge=1, le=10000)]
    fuel_l_per_100km: Amount
    driver_allowance: Amount
    fixed_cost: Amount


@router.post("/vehicles", status_code=status.HTTP_201_CREATED)
def create_vehicle(
    body: VehicleBody, principal: Annotated[Principal, Depends(require("settings.manage"))], session: DbSession
) -> dict[str, Any]:
    vehicle_id = service.create_vehicle(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        name=body.name,
        capacity_cartons=body.capacity_cartons,
        fuel_l_per_100km=Decimal(body.fuel_l_per_100km),
        driver_allowance=Decimal(body.driver_allowance),
        fixed_cost=Decimal(body.fixed_cost),
    )
    session.commit()
    return {"id": str(vehicle_id)}


@router.get("/plan")
def plan(_principal: Reader, session: DbSession, on: date | None = None) -> dict[str, Any]:
    """A preview of the day's trips from its dispatch notes. Nothing is written."""
    return service.plan(session, on)


class TripsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: date | None = None


@router.post("/trips", status_code=status.HTTP_201_CREATED)
def create_trips(body: TripsBody, principal: Dispatcher, session: DbSession) -> dict[str, Any]:
    made = service.create_trips(
        session, organization_id=principal.organization_id, actor_id=principal.user_id, on=body.on
    )
    session.commit()
    return {"trips": made}


@router.get("/trips")
def trips(
    _principal: Reader, session: DbSession, date_from: date | None = None, date_to: date | None = None
) -> dict[str, Any]:
    return {"trips": service.trips(session, date_from, date_to)}


class ActualBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual_km: Amount
    tolls: Amount = "0"


@router.post("/trips/{trip_id}/complete")
def complete_trip(trip_id: uuid.UUID, body: ActualBody, principal: Dispatcher, session: DbSession) -> dict[str, Any]:
    service.complete_trip(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        trip_id=trip_id,
        actual_km=Decimal(body.actual_km),
        tolls=Decimal(body.tolls),
    )
    session.commit()
    return {"id": str(trip_id), "status": "DONE"}


@router.get("/cost-to-serve")
def cost_to_serve(
    _principal: Reader, session: DbSession, days: Annotated[int, Query(ge=1, le=366)] = 30
) -> dict[str, Any]:
    return service.cost_to_serve(session, days)


class LocationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: Degrees
    longitude: Degrees


@router.put("/customers/{customer_id}/location")
def customer_location(
    customer_id: uuid.UUID,
    body: LocationBody,
    principal: Annotated[Principal, Depends(require("customer.manage"))],
    session: DbSession,
) -> dict[str, Any]:
    sales.set_customer_location(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        customer_id=customer_id,
        latitude=Decimal(body.latitude),
        longitude=Decimal(body.longitude),
    )
    session.commit()
    return {"customer_id": str(customer_id), "saved": True}


@router.put("/suppliers/{supplier_id}/location")
def supplier_location(
    supplier_id: uuid.UUID,
    body: LocationBody,
    principal: Annotated[Principal, Depends(require("settings.manage"))],
    session: DbSession,
) -> dict[str, Any]:
    procurement.set_supplier_location(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        supplier_id=supplier_id,
        latitude=Decimal(body.latitude),
        longitude=Decimal(body.longitude),
    )
    session.commit()
    return {"supplier_id": str(supplier_id), "saved": True}
