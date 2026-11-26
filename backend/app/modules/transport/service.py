"""Transport use cases (MP14, ADR-0021): vehicles, trip plans from the day's dispatch notes, trips with planned vs
actual km and cost, cost-to-serve per customer with a Deal Desk price floor. Management figures only: nothing here
posts to the stock ledger or to an invoice.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Any, Final

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.calendar import business_date, financial_year
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money
from app.modules.audit import service as audit
from app.modules.billing import service as billing
from app.modules.collections import service as collections
from app.modules.dispatch import service as dispatch
from app.modules.ledger import service as ledger
from app.modules.procurement import service as procurement
from app.modules.recipe import service as recipes
from app.modules.sales import service as sales
from app.modules.transport import domain, planner
from app.modules.transport.domain import CostRates, MockAdapter, Point
from app.modules.transport.models import Trip, TripStop, Vehicle
from app.modules.uom.domain import normalise

SETTINGS: Final = {
    "depot_latitude": "transport.depot_latitude",
    "depot_longitude": "transport.depot_longitude",
    "road_factor": "transport.road_factor",
    "fuel_inr_per_l": "transport.fuel_inr_per_l",
    "co2_kg_per_km": "transport.co2_kg_per_km",
    "credit_cost_pct_pa": "transport.credit_cost_pct_pa",
    "backhaul_detour_km": "transport.backhaul_detour_km",
}
DOC_TYPE: Final = "TRP"
DEFAULT_PER_CARTON: Final = 20  # when a finished good has no ACTIVE pack spec


class TransportError(DomainError):
    pass


def _settings(session: Session, on: date) -> dict[str, Decimal]:
    out = {}
    for name, key in SETTINGS.items():
        value = effective_settings.decimal_on(session, key, on)
        if value is None:
            raise TransportError("setting_missing", f"the setting {key} is not configured", {"key": key})
        out[name] = value
    return out


# ---------- vehicles ----------


def create_vehicle(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    name: str,
    capacity_cartons: int,
    fuel_l_per_100km: Decimal,
    driver_allowance: Decimal,
    fixed_cost: Decimal,
) -> uuid.UUID:
    vehicle_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                insert(Vehicle).values(
                    id=vehicle_id,
                    organization_id=organization_id,
                    name=name.strip(),
                    capacity_cartons=capacity_cartons,
                    fuel_l_per_100km=fuel_l_per_100km,
                    driver_allowance=driver_allowance,
                    fixed_cost=fixed_cost,
                    created_by=actor_id,
                )
            )
    except IntegrityError as exc:
        raise ConflictError("vehicle_exists", f"a vehicle named {name!r} already exists") from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="vehicle.create",
        entity_type="vehicle",
        entity_id=vehicle_id,
        after={"name": name, "capacity_cartons": capacity_cartons, "fuel_l_per_100km": fuel_l_per_100km},
    )
    return vehicle_id


def _vehicles(session: Session) -> list[Vehicle]:
    return list(session.execute(select(Vehicle).order_by(Vehicle.capacity_cartons.desc(), Vehicle.name)).scalars())


def vehicles(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": str(v.id),
            "name": v.name,
            "capacity_cartons": v.capacity_cartons,
            "fuel_l_per_100km": str(normalise(v.fuel_l_per_100km)),
            "driver_allowance": str(v.driver_allowance),
            "fixed_cost": str(v.fixed_cost),
        }
        for v in _vehicles(session)
    ]


def _rates(v: Vehicle, s: dict[str, Decimal]) -> CostRates:
    return CostRates(s["fuel_inr_per_l"], v.fuel_l_per_100km, v.driver_allowance, v.fixed_cost, s["co2_kg_per_km"])


# ---------- the plan ----------


@dataclass(frozen=True)
class _PlanData:
    settings: dict[str, Decimal]
    adapter: MockAdapter
    depot: Point
    briefs: dict[str, dispatch.DispatchBrief]
    places: dict[uuid.UUID, dict[str, Any]]
    plan: planner.Plan
    cartons: dict[str, int]
    reasons: dict[str, str]
    vehicles: dict[str, Vehicle]


def _on_a_trip(session: Session) -> set[uuid.UUID]:
    return set(session.execute(select(TripStop.dispatch_id)).scalars())


def _plan_data(session: Session, on: date) -> _PlanData:
    s = _settings(session, on)
    adapter = MockAdapter(s["road_factor"])
    depot = Point(s["depot_latitude"], s["depot_longitude"])
    taken = _on_a_trip(session)
    briefs = {str(b.dispatch_id): b for b in dispatch.dispatch_briefs(session, on=on) if b.dispatch_id not in taken}
    places = sales.customer_locations(session, list({b.customer_id for b in briefs.values()}))
    per_carton = recipes.units_per_carton(session, list({i for b in briefs.values() for i in b.packets}))
    cartons = {
        k: sum(domain.cartons(n, per_carton.get(i, DEFAULT_PER_CARTON)) for i, n in b.packets.items())
        for k, b in briefs.items()
    }
    fleet = _vehicles(session)
    reasons: dict[str, str] = {}
    stops = []
    for k, b in briefs.items():
        place = places.get(b.customer_id, {})
        if place.get("latitude") is None:
            reasons[k] = "no location recorded for this customer"
            continue
        stops.append(planner.Stop(k, Point(place["latitude"], place["longitude"]), cartons[k]))
    plan = planner.plan_routes(
        depot, stops, [planner.VehicleCap(str(v.id), v.capacity_cartons) for v in fleet], adapter
    )
    for k in plan.unplanned:
        reasons.setdefault(k, "no vehicle has room for it" if fleet else "no vehicle is set up")
    return _PlanData(s, adapter, depot, briefs, places, plan, cartons, reasons, {str(v.id): v for v in fleet})


def _backhaul(session: Session, d: _PlanData, route: planner.Route) -> list[dict[str, Any]]:
    """Suppliers within the detour limit of the route: pick up raw material on the way back."""
    points = [d.depot, *(_stop_point(d, k) for k in route.stops), d.depot]
    out = []
    for sid, sup in procurement.supplier_locations(session).items():
        if sup["latitude"] is None:
            continue
        via = Point(sup["latitude"], sup["longitude"])
        best = min(domain.detour_km(d.adapter, a, b, via) for a, b in pairwise(points))
        if best <= d.settings["backhaul_detour_km"]:
            out.append(
                {
                    "supplier_id": str(sid),
                    "supplier": sup["name"],
                    "detour_km": str(best),
                    "text": f"Pick up from {sup['name']} on the way: only {best} km extra",
                }
            )
    return out


def _stop_point(d: _PlanData, key: str) -> Point:
    place = d.places[d.briefs[key].customer_id]
    return Point(place["latitude"], place["longitude"])


def plan(session: Session, on: date | None = None) -> dict[str, Any]:
    """A preview of the day's trips: vehicles, stop order, km, cost, CO2 and backhaul. Nothing is written."""
    day = on or business_date()
    d = _plan_data(session, day)
    routes = []
    for r in d.plan.routes:
        v = d.vehicles[r.vehicle_key]
        cost = domain.trip_cost(r.km, Decimal(0), _rates(v, d.settings), None, "planned")
        packets = [sum(d.briefs[k].packets.values()) for k in r.stops]
        shares = domain.split_by_packets(cost.value, packets)
        routes.append(
            {
                "vehicle_id": r.vehicle_key,
                "vehicle": v.name,
                "capacity_cartons": v.capacity_cartons,
                "cartons": sum(d.cartons[k] for k in r.stops),
                "km": str(r.km),
                "cost": cost.to_json(),
                "co2": domain.co2_kg(r.km, d.settings["co2_kg_per_km"], None).to_json(),
                "stops": [
                    {
                        "seq": n,
                        "dispatch_id": k,
                        "dispatch_no": d.briefs[k].dispatch_no,
                        "invoice_no": d.briefs[k].invoice_no,
                        "customer": d.places[d.briefs[k].customer_id]["name"],
                        "packets": str(packets[n - 1]),
                        "cartons": str(d.cartons[k]),
                        "leg_km": str(r.legs_km[n - 1]),
                        "cost_share": str(shares[n - 1]),
                    }
                    for n, k in enumerate(r.stops, start=1)
                ],
                "return_km": str(r.legs_km[-1]),
                "backhaul": _backhaul(session, d, r),
            }
        )
    return {
        "date": day.isoformat(),
        "routing": d.adapter.name,
        "road_factor": str(d.settings["road_factor"]),
        "routes": routes,
        "unplanned": [
            {
                "dispatch_id": k,
                "dispatch_no": d.briefs[k].dispatch_no,
                "customer": d.places.get(d.briefs[k].customer_id, {}).get("name"),
                "reason": reason,
            }
            for k, reason in sorted(d.reasons.items(), key=lambda kv: d.briefs[kv[0]].dispatch_no)
        ],
        "note": (
            "Distances are straight-line x the road factor (DEMO setting), not a road map. Costs are management"
            " figures and are not posted. CO2 is an estimate."
        ),
    }


def create_trips(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, on: date | None = None
) -> list[str]:
    """Write the planned trips (PLANNED) and their stops for the day. Returns the trip numbers."""
    day = on or business_date()
    d = _plan_data(session, day)
    if not d.plan.routes:
        raise TransportError("nothing_to_plan", "no dispatch note of this day can be put on a trip")
    made = []
    for r in d.plan.routes:
        number = session.execute(
            text("SELECT aahar_next_doc_number(:o, :t, :fy)"),
            {"o": organization_id, "t": DOC_TYPE, "fy": financial_year(day)},
        ).scalar_one()
        trip_no = f"TRP/{financial_year(day)}/{int(number):06d}"
        trip_id = uuid.uuid4()
        try:
            with session.begin_nested():
                session.execute(
                    insert(Trip).values(
                        id=trip_id,
                        organization_id=organization_id,
                        vehicle_id=uuid.UUID(r.vehicle_key),
                        trip_date=day,
                        planned_km=r.km,
                        trip_no=trip_no,
                        created_by=actor_id,
                    )
                )
                session.execute(
                    insert(TripStop),
                    [
                        {
                            "organization_id": organization_id,
                            "trip_id": trip_id,
                            "dispatch_id": uuid.UUID(k),
                            "seq": n,
                            "created_by": actor_id,
                        }
                        for n, k in enumerate(r.stops, start=1)
                    ],
                )
        except IntegrityError as exc:
            raise ConflictError("already_on_a_trip", "a dispatch note is already on a trip; plan again") from exc
        audit.record(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            action="trip.plan",
            entity_type="trip",
            entity_id=trip_id,
            after={"trip_no": trip_no, "vehicle_id": r.vehicle_key, "planned_km": r.km, "stops": list(r.stops)},
        )
        made.append(trip_no)
    return made


def complete_trip(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    trip_id: uuid.UUID,
    actual_km: Decimal,
    tolls: Decimal,
) -> None:
    if actual_km < 0 or tolls < 0:
        raise TransportError("bad_actuals", "km and tolls cannot be negative")
    trip = session.execute(select(Trip).where(Trip.id == trip_id).with_for_update()).scalar_one_or_none()
    if trip is None:
        raise NotFoundError("trip_not_found", "unknown trip")
    if trip.status == "DONE":
        raise ConflictError("trip_done", f"trip {trip.trip_no} is already completed")
    session.execute(
        update(Trip).where(Trip.id == trip_id).values(status="DONE", actual_km=actual_km, tolls=round_money(tolls))
    )
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="trip.complete",
        entity_type="trip",
        entity_id=trip_id,
        before={"status": "PLANNED"},
        after={"status": "DONE", "actual_km": actual_km, "tolls": tolls},
    )


@dataclass(frozen=True)
class _TripCost:
    trip: Trip
    vehicle: Vehicle
    stops: list[tuple[int, dispatch.DispatchBrief]]
    planned: Explained
    actual: Explained | None
    shares: list[Decimal]  # of the actual cost if done, else the planned


def _trip_costs(session: Session, date_from: date, date_to: date) -> list[_TripCost]:
    trips = list(
        session.execute(
            select(Trip).where(Trip.trip_date >= date_from, Trip.trip_date <= date_to).order_by(Trip.trip_no)
        ).scalars()
    )
    if not trips:
        return []
    fleet = {v.id: v for v in _vehicles(session)}
    stops = list(session.execute(select(TripStop).where(TripStop.trip_id.in_([t.id for t in trips]))).scalars())
    briefs = {b.dispatch_id: b for b in dispatch.dispatch_briefs(session, dispatch_ids=[s.dispatch_id for s in stops])}
    out = []
    for t in trips:
        s = _settings(session, t.trip_date)
        rates = _rates(fleet[t.vehicle_id], s)
        src = SourceRef("trip", str(t.id))
        planned = domain.trip_cost(t.planned_km or Decimal(0), Decimal(0), rates, src, "planned")
        actual = (
            None if t.status != "DONE" else domain.trip_cost(t.actual_km or Decimal(0), t.tolls, rates, src, "actual")
        )
        mine = sorted(((st.seq, briefs[st.dispatch_id]) for st in stops if st.trip_id == t.id), key=lambda x: x[0])
        shares = domain.split_by_packets((actual or planned).value, [sum(b.packets.values()) for _, b in mine])
        out.append(_TripCost(t, fleet[t.vehicle_id], mine, planned, actual, shares))
    return out


def trips(session: Session, date_from: date | None = None, date_to: date | None = None) -> list[dict[str, Any]]:
    to = date_to or business_date()
    frm = date_from or to - timedelta(days=30)
    places = sales.customer_locations(session)
    out = []
    for c in _trip_costs(session, frm, to):
        t = c.trip
        s = _settings(session, t.trip_date)
        km = t.actual_km if t.actual_km is not None else (t.planned_km or Decimal(0))
        out.append(
            {
                "id": str(t.id),
                "trip_no": t.trip_no,
                "trip_date": t.trip_date.isoformat(),
                "status": t.status,
                "vehicle": c.vehicle.name,
                "planned_km": None if t.planned_km is None else str(normalise(t.planned_km)),
                "actual_km": None if t.actual_km is None else str(normalise(t.actual_km)),
                "tolls": str(t.tolls),
                "planned_cost": c.planned.to_json(),
                "actual_cost": None if c.actual is None else c.actual.to_json(),
                "co2": domain.co2_kg(km, s["co2_kg_per_km"], SourceRef("trip", str(t.id))).to_json(),
                "stops": [
                    {
                        "seq": seq,
                        "dispatch_no": b.dispatch_no,
                        "invoice_no": b.invoice_no,
                        "customer": places.get(b.customer_id, {}).get("name"),
                        "packets": str(sum(b.packets.values())),
                        "cost_share": str(share),
                    }
                    for (seq, b), share in zip(c.stops, c.shares, strict=True)
                ],
            }
        )
    return out


# ---------- cost-to-serve and the Deal Desk ----------


def cost_to_serve(session: Session, days: int = 30, on: date | None = None) -> dict[str, Any]:
    """Per customer over the last `days`: delivery (their share of trip costs, actual where done, by packets) +
    credit cost (what is owed today x the annual rate of money x days / 365) + returns (credit notes). Per packet
    delivered, and the Deal Desk price floor = finished-goods cost per packet + cost-to-serve per packet."""
    if days < 1 or days > 366:
        raise TransportError("bad_days", "days must be between 1 and 366")
    to = on or business_date()
    frm = to - timedelta(days=days - 1)
    s = _settings(session, to)
    places = sales.customer_locations(session)
    delivery: dict[uuid.UUID, list[ExplainedInput]] = {}
    packets: dict[uuid.UUID, int] = {}
    fg_items: set[uuid.UUID] = set()
    for c in _trip_costs(session, frm, to):
        for (_, b), share in zip(c.stops, c.shares, strict=True):
            delivery.setdefault(b.customer_id, []).append(
                ExplainedInput(f"{c.trip.trip_no} / {b.dispatch_no}", share, "INR", SourceRef("trip", str(c.trip.id)))
            )
            packets[b.customer_id] = packets.get(b.customer_id, 0) + sum(b.packets.values())
            fg_items |= set(b.packets)
    returns = billing.credit_note_totals(session, frm, to)
    unit_cost = _fg_cost_per_packet(session, fg_items)
    rows = []
    for cid in sorted(set(delivery) | set(returns), key=lambda c: places.get(c, {}).get("code", "")):
        owed = collections.outstanding_explained(session, cid)
        credit = domain.credit_cost(owed.value, s["credit_cost_pct_pa"], days)
        deliv = sum((i.value for i in delivery.get(cid, [])), Decimal(0))
        ret = returns.get(cid, Decimal(0))
        total = deliv + credit + ret
        n = packets.get(cid, 0)
        per_packet = None if n == 0 else round_money(total / n)
        rows.append(
            {
                "customer_id": str(cid),
                "customer_code": places.get(cid, {}).get("code"),
                "customer_name": places.get(cid, {}).get("name"),
                "packets": str(n),
                "delivery": Explained(
                    deliv, "INR", "share of each trip's cost, by packets", tuple(delivery.get(cid, []))
                ).to_json(),
                "credit": Explained(
                    credit,
                    "INR",
                    "owed today x annual rate of money / 100 x days / 365",
                    (
                        ExplainedInput("owed today", owed.value, "INR", SourceRef("customer", str(cid))),
                        ExplainedInput("rate of money", s["credit_cost_pct_pa"], "% a year"),
                        ExplainedInput("days", Decimal(days), "days"),
                    ),
                ).to_json(),
                "returns": Explained(ret, "INR", "credit notes in the period (with tax)").to_json(),
                "total": Explained(
                    total,
                    "INR",
                    "delivery + credit + returns",
                    (
                        ExplainedInput("delivery", deliv, "INR"),
                        ExplainedInput("credit", credit, "INR"),
                        ExplainedInput("returns", ret, "INR"),
                    ),
                    method="cost-to-serve",
                ).to_json(),
                "per_packet": None
                if per_packet is None
                else Explained(
                    per_packet,
                    "INR/packet",
                    "cost-to-serve / packets delivered",
                    (ExplainedInput("cost-to-serve", total, "INR"), ExplainedInput("packets", Decimal(n), "packets")),
                ).to_json(),
                "price_floor": None
                if per_packet is None or unit_cost is None
                else Explained(
                    round_money(unit_cost.value + per_packet),
                    "INR/packet",
                    "finished-goods cost per packet + cost-to-serve per packet (never quote below this)",
                    (
                        ExplainedInput("finished-goods cost per packet", unit_cost.value, "INR/packet"),
                        ExplainedInput("cost-to-serve per packet", per_packet, "INR/packet"),
                    ),
                    method="Deal Desk floor, ex tax",
                ).to_json(),
            }
        )
    return {
        "date_from": frm.isoformat(),
        "date_to": to.isoformat(),
        "rows": rows,
        "note": "Management figures: delivery from trips (actual where completed), credit at the DEMO rate of money.",
    }


def _fg_cost_per_packet(session: Session, items: set[uuid.UUID]) -> Explained | None:
    """Finished-goods cost per packet: the FG store's value / packets on hand (lots at actual cost, ADR-0005).
    One finished good in the DEMO; the first with stock if several."""
    for item in sorted(items, key=str):
        qty, value = ledger.balance(session, item, "FG_STORE")
        if qty > 0:
            per = (value / qty).quantize(Decimal("0.000001"))
            return Explained(
                per,
                "INR/packet",
                "finished-goods store value / packets on hand",
                (
                    ExplainedInput("FG store value", value, "INR", SourceRef("inventory_balances", str(item))),
                    ExplainedInput("packets on hand", qty, "packets", SourceRef("inventory_balances", str(item))),
                ),
            )
    return None


def trip_count(session: Session) -> int:
    return int(session.execute(select(func.count()).select_from(Trip)).scalar_one())
