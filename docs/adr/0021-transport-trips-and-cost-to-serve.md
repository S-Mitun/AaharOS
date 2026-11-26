# ADR-0021: Transport (light): trips from dispatch notes, trip cost, cost-to-serve and the Deal Desk floor

- Status: Accepted (MP14, 2026-11-26; built the same day at the user's request, kept light as the master pack asks)
- Builds on: ADR-0017 (dispatch notes, credit notes, collections), ADR-0005 (finished-goods lots at actual cost)

## Context
MP14 is a stretch: trip planning with vehicle capacity, planned vs actual km and cost, cost-to-serve per customer, a
Deal Desk price floor, backhaul and an estimated CO2. No benchmark row belongs to it. The schema had `vehicles`,
`trips`, `trip_stops` and `transport_costs` since MP02, unused.

## Decision
- **M1 Locations (migration 0013).** Customers and suppliers get an optional latitude / longitude (both or neither,
  in range). The depot and every rate are effective-dated settings: `transport.depot_latitude / depot_longitude`,
  `road_factor` (1.3), `fuel_inr_per_l` (94.00), `co2_kg_per_km` (0.20), `credit_cost_pct_pa` (12),
  `backhaul_detour_km` (15). DEMO values; DEMO locations are town centres around Tiruchirappalli (no addresses).
- **M2 Routing.** A `RoutingAdapter` interface; the default `MockAdapter` is the great-circle distance x the road
  factor: deterministic, offline, no map service and no map shown (so no tiles to attribute). The trigonometry runs in
  binary floating point because Decimal has no sine; the result is rounded to metres at once and only that Decimal is
  used. An OSRM adapter can be added behind the same interface; it is not built.
- **M3 Trip planning.** From the day's dispatch notes not yet on a trip (a stop names a dispatch once: unique
  `trip_stops.dispatch_id`): cartons = packets / the pack spec's units per carton, rounded up; OR-Tools routing (CVRP)
  with each vehicle's carton capacity, a fixed charge per vehicle used (100 km) and greedy descent with no time limit,
  so the same day always gives the same plan. A stop with no location or no room is reported with its reason, never
  dropped. Planning is a read; "Create these trips" writes PLANNED trips (`TRP/{fy}/{n}`, gapless) with their stops
  (`dispatch.post`); recording actual km and tolls makes a trip DONE, once.
- **M4 Trip cost.** km x L per 100 km / 100 x fuel price + driver allowance + tolls + fixed cost (vehicle running
  costs are master data on `vehicles`), shared over the stops by packets (the documented default; the rounding
  remainder goes to the largest stop so shares add up). Planned cost uses planned km; actual uses actual km and tolls.
  Computed on read from the trip's km and the settings and vehicle in force; management figures, never posted to the
  ledger. CO2 = km x factor, always labelled an estimate.
- **M5 Cost-to-serve and the Deal Desk.** Per customer over 30 days: delivery (their trip-cost shares, actual where
  done) + credit (owed today x the annual rate of money x days / 365) + returns (credit notes, with tax); per packet
  delivered; floor = finished-goods cost per packet (FG store value / packets on hand) + cost-to-serve per packet,
  ex tax. Every figure is Explained.
- **M6 Backhaul.** A supplier within `backhaul_detour_km` of extra driving between two consecutive points of a route
  is suggested as a pick-up on the way.
- **M7 Not built (kept light):** the salesman visit check-in (opt-in, one-time) and an OSRM adapter; there is no
  continuous GPS tracking, ever (CLAUDE.md).

## Consequences
- 26/26 unchanged. The DEMO seed adds two DEMO vehicles, locations and the four trips of the DEMO history (actual =
  planned + 4%), so cost-to-serve has data: small drops cost Rs 14-19 a packet to serve, which the floor makes visible.
- Straight-line x factor understates winding roads and ignores traffic; trips record actual km for that reason.
- Costs are recomputed from current settings when a rate changes later (settings are effective-dated by trip date).
