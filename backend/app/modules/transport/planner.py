"""Trip planning as a capacitated vehicle routing problem (MP14, ADR-0021). Pure: no database.

OR-Tools routing: one trip per vehicle from and back to the depot, cartons <= capacity, shortest total distance, a
fixed charge per vehicle used (so it does not split a load that one vehicle can carry). The search is the cheapest-arc
start plus greedy descent to a local optimum with no time limit, so the same input always gives the same plan. A stop
no vehicle can take (too big, or not enough room left) is returned as unplanned, never silently dropped.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise

from ortools.constraint_solver import pywrapcp, routing_enums_pb2  # type: ignore[import-untyped]

from app.modules.transport.domain import Point, RoutingAdapter

VEHICLE_FIXED_M = 100_000  # a second vehicle must save more than 100 km to be worth sending
DROP_PENALTY_M = 10_000_000  # leaving a stop unplanned costs more than any route


@dataclass(frozen=True)
class Stop:
    key: str
    point: Point
    cartons: int


@dataclass(frozen=True)
class VehicleCap:
    key: str
    capacity: int


@dataclass(frozen=True)
class Route:
    vehicle_key: str
    stops: tuple[str, ...]  # in driving order
    legs_km: tuple[Decimal, ...]  # depot -> first, ..., last -> depot

    @property
    def km(self) -> Decimal:
        return sum(self.legs_km, Decimal(0))


@dataclass(frozen=True)
class Plan:
    routes: tuple[Route, ...]
    unplanned: tuple[str, ...]


def plan_routes(depot: Point, stops: Sequence[Stop], vehicles: Sequence[VehicleCap], adapter: RoutingAdapter) -> Plan:
    if not stops:
        return Plan((), ())
    if not vehicles:
        return Plan((), tuple(s.key for s in stops))
    points = [depot, *(s.point for s in stops)]
    km = [[adapter.distance_km(a, b) for b in points] for a in points]
    metres = [[int(d * 1000) for d in row] for row in km]
    manager = pywrapcp.RoutingIndexManager(len(points), len(vehicles), 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance(i: int, j: int) -> int:
        return int(metres[manager.IndexToNode(i)][manager.IndexToNode(j)])

    arc = routing.RegisterTransitCallback(distance)
    routing.SetArcCostEvaluatorOfAllVehicles(arc)
    demand = [0, *(s.cartons for s in stops)]

    def load(i: int) -> int:
        return int(demand[manager.IndexToNode(i)])

    cap = routing.RegisterUnaryTransitCallback(load)
    routing.AddDimensionWithVehicleCapacity(cap, 0, [v.capacity for v in vehicles], True, "cartons")
    for v in range(len(vehicles)):
        routing.SetFixedCostOfVehicle(VEHICLE_FIXED_M, v)
    for node in range(1, len(points)):
        routing.AddDisjunction([manager.NodeToIndex(node)], DROP_PENALTY_M)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GREEDY_DESCENT
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return Plan((), tuple(s.key for s in stops))

    routes = []
    planned: set[int] = set()
    for v, vehicle in enumerate(vehicles):
        index = routing.Start(v)
        nodes = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node:
                nodes.append(node)
            index = solution.Value(routing.NextVar(index))
        if not nodes:
            continue
        planned.update(nodes)
        path = [0, *nodes, 0]
        routes.append(
            Route(
                vehicle.key,
                tuple(stops[n - 1].key for n in nodes),
                tuple(km[a][b] for a, b in pairwise(path)),
            )
        )
    unplanned = tuple(stops[n - 1].key for n in range(1, len(points)) if n not in planned)
    return Plan(tuple(routes), unplanned)
