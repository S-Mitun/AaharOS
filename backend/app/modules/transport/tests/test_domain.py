"""Transport rules and the trip planner without a database (MP14, ADR-0021)."""

from decimal import Decimal

import pytest

from app.core.explained import SourceRef
from app.modules.transport import domain, planner
from app.modules.transport.domain import CostRates, MockAdapter, Point

D = Decimal
TRICHY = Point(D("10.790500"), D("78.704700"))
SRIRANGAM = Point(D("10.862000"), D("78.690000"))
THANJAVUR = Point(D("10.787000"), D("79.137800"))
KARUR = Point(D("10.960100"), D("78.076600"))
KULITHALAI = Point(D("10.935600"), D("78.420600"))


def test_haversine_and_the_road_factor() -> None:
    straight = domain.haversine_km(TRICHY, THANJAVUR)
    assert D("47") < straight < D("48")  # about 47.4 km as the crow flies
    assert domain.haversine_km(TRICHY, TRICHY) == 0
    road = MockAdapter(D("1.3")).distance_km(TRICHY, THANJAVUR)
    assert road == (straight * D("1.3")).quantize(D("0.001"))
    assert MockAdapter(D("1.3")).distance_km(TRICHY, KARUR) == MockAdapter(D("1.3")).distance_km(KARUR, TRICHY)


def test_cartons_round_up() -> None:
    assert [domain.cartons(n, 20) for n in (1, 20, 21, 60)] == [1, 1, 2, 3]
    with pytest.raises(ValueError):
        domain.cartons(10, 0)


def test_trip_cost_is_fuel_driver_tolls_and_fixed() -> None:
    rates = CostRates(D("94.00"), D("6.5"), D("500.00"), D("300.00"), D("0.20"))
    cost = domain.trip_cost(D("100"), D("120.00"), rates, SourceRef("trip", "t1"), "actual")
    assert cost.value == D("611.00") + D("500.00") + D("120.00") + D("300.00")  # fuel 100 x 6.5 / 100 x 94 = 611
    assert [i.label for i in cost.inputs][:2] == ["actual km", "fuel use"]
    assert domain.co2_kg(D("143"), D("0.20"), None).value == D("28.6")


def test_the_split_by_packets_always_adds_up() -> None:
    assert domain.split_by_packets(D("100.00"), [1, 1, 1]) == [D("33.34"), D("33.33"), D("33.33")]
    assert sum(domain.split_by_packets(D("1673.73"), [30, 60])) == D("1673.73")
    assert domain.split_by_packets(D("10.00"), [0, 0]) == [D(0), D(0)]


def test_backhaul_detour_and_credit_cost() -> None:
    road = MockAdapter(D("1.3"))
    assert domain.detour_km(road, TRICHY, KARUR, KULITHALAI) < D("5")  # on the way
    assert domain.detour_km(road, TRICHY, SRIRANGAM, THANJAVUR) > D("50")  # far off
    assert domain.credit_cost(D("3650.00"), D("12"), 30) == D("36.00")


def test_the_planner_respects_capacity_and_is_repeatable() -> None:
    road = MockAdapter(D("1.3"))
    stops = [
        planner.Stop("A", SRIRANGAM, 3),
        planner.Stop("C", THANJAVUR, 3),
        planner.Stop("D", KARUR, 4),
    ]
    fleet = [planner.VehicleCap("truck", 40), planner.VehicleCap("bike", 4)]
    one = planner.plan_routes(TRICHY, stops, fleet, road)
    assert one == planner.plan_routes(TRICHY, stops, fleet, road)  # deterministic
    assert one.unplanned == () and [r.vehicle_key for r in one.routes] == ["truck"]  # one vehicle is cheaper
    assert sorted(one.routes[0].stops) == ["A", "C", "D"] and len(one.routes[0].legs_km) == 4
    tight = planner.plan_routes(TRICHY, stops, [planner.VehicleCap("bike", 4), planner.VehicleCap("van", 5)], road)
    assert sum(len(r.stops) for r in tight.routes) == 2 and len(tight.unplanned) == 1  # 10 cartons, room for 9
    for r in tight.routes:
        cap = {"bike": 4, "van": 5}[r.vehicle_key]
        assert sum({"A": 3, "C": 3, "D": 4}[s] for s in r.stops) <= cap


def test_a_stop_too_big_for_every_vehicle_is_reported_not_dropped() -> None:
    plan = planner.plan_routes(
        TRICHY, [planner.Stop("big", KARUR, 50)], [planner.VehicleCap("truck", 40)], MockAdapter(D("1.3"))
    )
    assert plan.routes == () and plan.unplanned == ("big",)
    assert planner.plan_routes(TRICHY, [], [], MockAdapter(D("1"))) == planner.Plan((), ())
    no_fleet = planner.plan_routes(TRICHY, [planner.Stop("a", KARUR, 1)], [], MockAdapter(D("1")))
    assert no_fleet.unplanned == ("a",)
