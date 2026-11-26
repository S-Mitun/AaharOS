"""Transport rules (MP14, ADR-0021). Pure functions, no database.

Distances come from a RoutingAdapter. The default MockAdapter is the great-circle (haversine) distance x a
configurable road factor: deterministic, offline, no map service. Trip cost = fuel (km x L/100 km / 100 x Rs/L) +
driver allowance + tolls + fixed cost; it is split over the stops by packets (the documented default). CO2 is km x a
configurable factor and is always labelled an estimate.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Protocol

from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money

EARTH_RADIUS_KM = Decimal("6371.0088")
KM_PLACES = Decimal("0.001")


@dataclass(frozen=True)
class Point:
    latitude: Decimal
    longitude: Decimal


class RoutingAdapter(Protocol):
    """Road distance between two points, in km. A real router (OSRM) can replace the mock behind this interface."""

    @property
    def name(self) -> str: ...

    def distance_km(self, a: Point, b: Point) -> Decimal: ...


def haversine_km(a: Point, b: Point) -> Decimal:
    """Great-circle distance. The trigonometry runs in binary floating point (there is no Decimal sine); the result
    is rounded to metres at once and only that Decimal is used, never stored as a float."""
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (a.latitude, a.longitude, b.latitude, b.longitude))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    central = Decimal(repr(2 * math.asin(math.sqrt(h))))
    return (EARTH_RADIUS_KM * central).quantize(KM_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class MockAdapter:
    """Straight-line distance x road factor (DEMO setting transport.road_factor). Deterministic."""

    road_factor: Decimal
    name: str = "mock (straight line x road factor)"

    def distance_km(self, a: Point, b: Point) -> Decimal:
        return (haversine_km(a, b) * self.road_factor).quantize(KM_PLACES, rounding=ROUND_HALF_UP)


def cartons(packets: int, per_carton: int) -> int:
    """Whole cartons a delivery fills (a part carton still takes a carton's space)."""
    if per_carton <= 0:
        raise ValueError("units per carton must be positive")
    return int((Decimal(packets) / per_carton).to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class CostRates:
    fuel_inr_per_l: Decimal
    fuel_l_per_100km: Decimal
    driver_allowance: Decimal
    fixed_cost: Decimal
    co2_kg_per_km: Decimal


def trip_cost(km: Decimal, tolls: Decimal, rates: CostRates, source: SourceRef | None, label: str) -> Explained:
    """Fuel + driver allowance + tolls + fixed cost for one trip, in rupees."""
    fuel = round_money(km * rates.fuel_l_per_100km / 100 * rates.fuel_inr_per_l)
    total = fuel + rates.driver_allowance + tolls + rates.fixed_cost
    return Explained(
        total,
        "INR",
        "km x L per 100 km / 100 x fuel price + driver allowance + tolls + fixed cost",
        (
            ExplainedInput(f"{label} km", km, "km", source),
            ExplainedInput("fuel use", rates.fuel_l_per_100km, "L/100 km"),
            ExplainedInput("fuel price", rates.fuel_inr_per_l, "INR/L"),
            ExplainedInput("fuel", fuel, "INR"),
            ExplainedInput("driver allowance", rates.driver_allowance, "INR"),
            ExplainedInput("tolls", tolls, "INR", source),
            ExplainedInput("fixed cost", rates.fixed_cost, "INR"),
        ),
        method="trip cost (management figure, not posted)",
    )


def co2_kg(km: Decimal, factor: Decimal, source: SourceRef | None) -> Explained:
    value = (km * factor).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return Explained(
        value,
        "kg",
        "km x emission factor",
        (ExplainedInput("km", km, "km", source), ExplainedInput("emission factor", factor, "kg/km")),
        method="estimate (DEMO factor)",
    )


def split_by_packets(total: Decimal, packets: Sequence[int]) -> list[Decimal]:
    """Share a rupee amount by packets, to paise; the rounding remainder goes to the largest stop so the shares
    always add back to the total."""
    whole = sum(packets)
    if whole <= 0:
        return [Decimal(0) for _ in packets]
    shares = [round_money(total * n / whole) for n in packets]
    biggest = max(range(len(packets)), key=lambda i: (packets[i], -i))
    shares[biggest] += total - sum(shares)
    return shares


def detour_km(adapter: RoutingAdapter, before: Point, after: Point, via: Point) -> Decimal:
    """Extra km to call at `via` between two consecutive points of a route."""
    return adapter.distance_km(before, via) + adapter.distance_km(via, after) - adapter.distance_km(before, after)


def credit_cost(outstanding: Decimal, annual_rate_pct: Decimal, days: int) -> Decimal:
    """What carrying a customer's unpaid balance costs over a period, at the factory's annual rate of money."""
    return round_money(outstanding * annual_rate_pct / 100 * days / 365)
