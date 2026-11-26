"""MP13 (T7): a short DEMO history for the LIVE DEMO factory, posted once through the real services.

From the factory's opening day (2026-11-21, when its opening stock is dated) to today: supplier receipts with lots,
three completed batches with oil sessions and fill-weight samples, and orders from three retailers at different
rhythms, each approved, invoiced and dispatched FEFO. Everything is fictional and labelled DEMO. It never runs on a
BENCHMARK tenant and never touches the oracle.

Deviation from the approved plan (T7 said "over the past 3 weeks"): the DEMO opening stock is dated on the opening
day, so a history before it would issue and dispatch stock the ledger shows arriving later. The history therefore
starts on the opening day; any day after today is clamped to today.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Final

from sqlalchemy.orm import Session

from app.core.calendar import business_date
from app.modules.billing import service as billing
from app.modules.catalog import service as catalog
from app.modules.dispatch import service as dispatch
from app.modules.identity import service as identity
from app.modules.judge.replay import PACK_200G, POSTING_DATE, PRICE_LIST_CODE, RECIPE
from app.modules.ledger import service as ledger
from app.modules.procurement import service as procurement
from app.modules.procurement.domain import ReceiptLineIn
from app.modules.production import service as production
from app.modules.recipe import service as recipes
from app.modules.sales import service as sales
from app.modules.sales.domain import OrderLineIn
from app.modules.transport import service as transport

D = Decimal
MARKER_LOT: Final = "DEMO-FL-01"  # the history is there once the first flour lot exists
POUCH_G: Final = D("4.5")  # DEMO tare of one 200 g pouch (gross - net)

# customer code, name, salesman, route order. `users` maps PRODUCTION, ADMIN, SALESMAN_A, SALESMAN_B to user ids.
NEW_RETAILERS: Final = (("RET-C", "DEMO Retailer C", "SALESMAN_A", 2), ("RET-D", "DEMO Retailer D", "SALESMAN_B", 2))
SALESMAN_OF: Final = {"RET-A": "SALESMAN_A", "RET-C": "SALESMAN_A", "RET-D": "SALESMAN_B"}
USER_EMAILS: Final = {
    "PRODUCTION": "production@aaharos-demo.invalid",
    "ADMIN": "admin@aaharos-demo.invalid",
    "SALESMAN_A": "salesman.a@aaharos-demo.invalid",
    "SALESMAN_B": "salesman.b@aaharos-demo.invalid",
}

# day offset, [(item, qty, unit, rate, supplier lot or None)]
RECEIPTS: Final = (
    (0, [("flour", "50", "kg", "45.00", "DEMO-FL-01"), ("pouch_200g", "400", "piece", "2.50", "DEMO-PCH-01")]),
    (1, [("spice_mix", "3", "kg", "205.00", "DEMO-SP-01")]),
    (2, [("flour", "50", "kg", "46.00", "DEMO-FL-02"), ("cooking_oil", "15", "L", "142.00", "DEMO-OIL-01")]),
)


@dataclass(frozen=True)
class Batch:
    day: int
    flour_kg: str
    oil_l: str
    good: int
    damaged: int
    fresh_ml: str
    topup_ml: str
    discard_ml: str
    tpc_pct: str
    nets_g: tuple[str, ...]


BATCHES: Final = (
    Batch(0, "40", "10.5", 190, 4, "10000", "500", "0", "12.0", ("203", "205", "201", "204", "206")),
    Batch(2, "40", "10.3", 186, 5, "10000", "300", "0", "18.5", ("208", "210", "207", "209", "211")),
    Batch(4, "40", "10.2", 192, 3, "10000", "200", "1500", "26.0", ("199", "202", "190", "201", "203")),
)
# day offset, customer, packets: Retailer A small and often, C larger and less often, D once so far
ORDERS: Final = (
    (1, "RET-A", 30),
    (1, "RET-C", 60),
    (2, "RET-A", 30),
    (2, "RET-D", 80),
    (4, "RET-C", 60),
    (5, "RET-A", 30),
)


def history_present(session: Session) -> bool:
    try:
        flour = catalog.id_by_code(session, "flour")
    except Exception:
        return False
    return ledger.lot_id_by_no(session, flour, MARKER_LOT) is not None


def seed_history(
    session: Session, org_id: uuid.UUID, users: dict[str, uuid.UUID], start: date = POSTING_DATE
) -> list[str]:
    """Post the DEMO history once (the caller commits). Returns what was added, or [] when it is already there."""
    if history_present(session):
        return []
    today = business_date()

    def day(n: int) -> date:
        return min(start + timedelta(days=n), today)

    ids = {code: catalog.id_by_code(session, code) for code in ("flour", "cooking_oil", "spice_mix")}
    ids |= {code: catalog.id_by_code(session, code) for code in ("pouch_200g", "carton_20", "murukku_200g")}
    supplier = uuid.UUID(procurement.list_suppliers(session)[0]["id"])
    production_user = users["PRODUCTION"]
    admin = users["ADMIN"]

    customers = {code: sales.customer_id_by_code(session, code) for code in ("RET-A",)}
    for code, name, salesman, route in NEW_RETAILERS:
        cid = sales.customer_id_by_code(session, code)
        if cid is None:
            cid = sales.create_customer(
                session,
                organization_id=org_id,
                actor_id=None,
                code=code,
                name=name,
                kind="RETAILER",
                state_code="33",
                gstin=None,
                credit_limit=D("25000.00"),
                payment_terms_days=30,
                msme_terms=True,
            )
            identity.assign_customer(
                session,
                organization_id=org_id,
                actor_id=None,
                salesman_id=users[salesman],
                customer_id=cid,
                route_order=route,
            )
        customers[code] = cid

    recipe_version = recipes.active_recipe_version(session, RECIPE[0])
    pack_version = recipes.active_pack_spec_version(session, PACK_200G[0])
    price_list = next(
        p["id"] for p in sales.list_price_lists(session) if p["code"] == PRICE_LIST_CODE and p["in_force_today"]
    )

    def receive(n: int) -> None:
        on, lines = next((day(d), ls) for d, ls in RECEIPTS if d == n)
        procurement.post_receipt(
            session,
            organization_id=org_id,
            actor_id=production_user,
            supplier_id=supplier,
            supplier_invoice_ref=f"DEMO-SUP-{on:%m%d}-{n}",
            received_on=on,
            lines=[ReceiptLineIn(ids[i], D(q), u, D(r), lot_no=lot) for i, q, u, r, lot in lines],
        )

    def make(b: Batch) -> str:
        on = day(b.day)
        run = production.create_run(
            session,
            organization_id=org_id,
            actor_id=production_user,
            recipe_version_id=recipe_version,
            batch_multiplier=D(1),
            run_date=on,
            pack_lines=[production.PackLineRequest(pack_version)],
        )
        production.start_run(session, organization_id=org_id, actor_id=production_user, run_id=run)
        production.issue_materials(
            session,
            organization_id=org_id,
            actor_id=production_user,
            run_id=run,
            posting_date=on,
            lines=[
                production.MaterialLineIn(ids["flour"], D(b.flour_kg), "kg"),
                production.MaterialLineIn(ids["cooking_oil"], D(b.oil_l), "L"),
                production.MaterialLineIn(ids["spice_mix"], D("1.2"), "kg"),
            ],
        )
        pack_line = production.run_analysis(session, run).pack_lines[0].pack_line_id
        sampled = datetime.combine(on, time(10, 0), tzinfo=UTC)
        production.complete_run(
            session,
            organization_id=org_id,
            actor_id=production_user,
            run_id=run,
            posting_date=on,
            results=[
                production.PackResultIn(
                    pack_line_id=pack_line,
                    good_units=b.good,
                    packaging=[
                        production.PackagingIn(ids["pouch_200g"], D(b.good + b.damaged), D(b.damaged), "piece"),
                        production.PackagingIn(ids["carton_20"], D(b.good // 20), D(0), "piece"),
                    ],
                )
            ],
            samples=[
                production.SampleIn(D(n) + POUCH_G, D(n), sampled + timedelta(minutes=10 * k))
                for k, n in enumerate(b.nets_g)
            ],
            oil=production.OilIn(D(b.fresh_ml), D(b.topup_ml), D(b.discard_ml), D(b.tpc_pct)),
        )
        return str(production.trace_runs(session, [run])[run]["run_no"])

    def sell(on: date, code: str, packets: int) -> str:
        placed = sales.receive_order(
            session,
            organization_id=org_id,
            actor_id=users[SALESMAN_OF[code]],
            customer_id=customers[code],  # type: ignore[arg-type]
            price_list_id=uuid.UUID(price_list),
            lines=[OrderLineIn(ids["murukku_200g"], packets, D("50.00"))],
            salesman_id=users[SALESMAN_OF[code]],
            order_date=on,
        )
        sales.approve_order(session, organization_id=org_id, actor_id=admin, order_id=placed.order_id)
        invoice = billing.create_invoice(
            session, organization_id=org_id, actor_id=admin, order_id=placed.order_id, invoice_date=on
        )
        dispatch.dispatch_invoice(
            session, organization_id=org_id, actor_id=admin, invoice_id=invoice.invoice_id, dispatch_date=on
        )
        return placed.order_no

    made: list[str] = []
    orders: list[str] = []
    for n in range(6):
        if any(d == n for d, _ in RECEIPTS):
            receive(n)
        made += [make(b) for b in BATCHES if b.day == n]
        orders += [sell(day(n), code, qty) for d, code, qty in ORDERS if d == n]
    return [
        f"{len(RECEIPTS)} receipts with supplier lots",
        f"batches {', '.join(made)} with oil sessions and fill samples",
        f"{len(orders)} orders from RET-A, RET-C and RET-D, invoiced and dispatched FEFO",
    ]


def seed_trips(session: Session, org_id: uuid.UUID, users: dict[str, uuid.UUID]) -> list[str]:
    """MP14: put the DEMO history's dispatches on planned trips and record their actual km (planned + 4%, rounded
    up to a whole km), once. Returns the trip numbers, or [] when trips already exist."""
    if transport.trip_count(session) > 0:
        return []
    days = sorted({b.dispatch_date for b in dispatch.dispatch_briefs(session)})
    made: list[str] = []
    for on in days:
        try:
            made += transport.create_trips(session, organization_id=org_id, actor_id=users["ADMIN"], on=on)
        except transport.TransportError:
            continue
    for trip in transport.trips(session, date_from=min(days, default=business_date()), date_to=business_date()):
        planned = D(trip["planned_km"] or "0")
        transport.complete_trip(
            session,
            organization_id=org_id,
            actor_id=users["ADMIN"],
            trip_id=uuid.UUID(trip["id"]),
            actual_km=(planned * D("1.04")).to_integral_value(rounding=ROUND_CEILING),
            tolls=D("0"),
        )
    return made
