"""Sales use cases: customers, versioned price lists and order taking (MP08, ADR-0015).

Other modules call only this file. Functions run in the caller's transaction and do not commit (the API route
commits). An order is placed in one savepoint:
  assignment check -> price check against the version the phone showed (G1) -> claim the Idempotency-Key (G4) ->
  gapless SO number (G3) -> order + lines -> SUBMITTED status-history row -> audit row -> store the response.
A refusal anywhere rolls the whole savepoint back, the SO number included, so numbers stay gapless.
Approval, reservations and the inbox arrive in MP09.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import idempotency
from app.core.calendar import business_date, financial_year
from app.core.errors import DomainError, NotFoundError, PermissionDeniedError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.identity import service as identity
from app.modules.identity.service import Principal
from app.modules.ledger import service as ledger
from app.modules.recipe import service as recipes
from app.modules.sales import domain
from app.modules.sales.domain import OrderError, OrderLineIn, PriceListVersion
from app.modules.sales.models import (
    CUSTOMER_KINDS,
    Customer,
    OrderLine,
    OrderStatusHistory,
    PriceList,
    PriceListItem,
    SalesOrder,
)

ORDERED_NOT_INVOICED = "Ordered, not invoiced: values are ex-tax order values, not sales."
COUNTED_STATUSES = ("SUBMITTED", "APPROVED", "PART_APPROVED", "INVOICED", "DISPATCHED")


def _db_error(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


# ---------- customers ----------


def _visible_customer(session: Session, principal: Principal, customer_id: uuid.UUID) -> Customer:
    """The customer, if this caller may order for it: a salesman only for assigned customers."""
    customer = session.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if customer is None:
        raise NotFoundError("customer_not_found", "unknown customer", {"customer_id": str(customer_id)})
    if principal.sees_only_own_rows and not identity.is_assigned(session, principal.user_id, customer_id):
        raise PermissionDeniedError(
            "customer_not_assigned", "this customer is not on your route", {"customer_id": str(customer_id)}
        )
    return customer


def list_customers(session: Session, principal: Principal) -> list[dict[str, Any]]:
    query = select(Customer).order_by(Customer.code)
    route: dict[uuid.UUID, int | None] = {}
    if principal.sees_only_own_rows:
        query = query.where(Customer.id.in_(identity.assigned_customer_ids(principal.user_id)))
        route = identity.route_order(session, principal.user_id)
    rows = [
        {
            "id": str(c.id),
            "code": c.code,
            "name": c.name,
            "kind": c.kind,
            "state_code": c.state_code,
            "gstin": c.gstin,
            "route_order": route.get(c.id),
        }
        for c in session.execute(query).scalars()
    ]
    if route:
        rows.sort(key=lambda r: (r["route_order"] is None, r["route_order"] or 0, r["code"]))
    return rows


def create_customer(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    code: str,
    name: str,
    kind: str,
    state_code: str,
    gstin: str | None = None,
) -> uuid.UUID:
    """Master data (MP05 seeds). Customer management screens arrive with MP09."""
    if kind not in CUSTOMER_KINDS:
        raise DomainError("unknown_customer_kind", f"customer kind must be one of {', '.join(CUSTOMER_KINDS)}")
    customer_id = uuid.uuid4()
    session.execute(
        insert(Customer).values(
            id=customer_id,
            organization_id=organization_id,
            code=code,
            name=name,
            kind=kind,
            state_code=state_code,
            gstin=gstin,
            created_by=actor_id,
        )
    )
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="customer.create",
        entity_type="customer",
        entity_id=customer_id,
        after={"code": code, "name": name, "kind": kind, "state_code": state_code, "gstin": gstin},
    )
    return customer_id


def customer_id_by_code(session: Session, code: str) -> uuid.UUID | None:
    return session.execute(select(Customer.id).where(Customer.code == code)).scalar_one_or_none()


# ---------- price lists (G1: append-only versions) ----------


def _versions(session: Session) -> list[PriceListVersion]:
    return [
        PriceListVersion(p.id, p.code, p.version, p.customer_id, p.effective_from, p.effective_to, p.created_at)
        for p in session.execute(select(PriceList)).scalars()
    ]


def _list_prices(session: Session, price_list_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    rows = session.execute(
        select(PriceListItem.item_id, PriceListItem.price_ex_tax).where(PriceListItem.price_list_id == price_list_id)
    ).tuples()
    return dict(rows.all())


def create_price_list(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    code: str,
    effective_from: date,
    items: Mapping[uuid.UUID, Decimal],
    customer_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Publish the next version of a price list. Versions are append-only (migration 0009): prices change only by
    publishing a new version, so every captured price can be traced to the list it came from."""
    code = code.strip().upper()
    if not code:
        raise OrderError("code_required", "a price list needs a code")
    kinds = catalog.kinds_for(session, items.keys())
    domain.check_new_price_list(items, {i for i, k in kinds.items() if k == "FG"})
    existing = [v for v in _versions(session) if v.code == code]
    if existing and {v.customer_id for v in existing} != {customer_id}:
        raise OrderError("price_list_customer_mismatch", f"price list {code} belongs to a different customer scope")
    if customer_id is not None and not customer_id_exists(session, customer_id):
        raise NotFoundError("customer_not_found", "unknown customer", {"customer_id": str(customer_id)})
    version = 1 + max((v.version for v in existing), default=0)
    price_list_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                insert(PriceList).values(
                    id=price_list_id,
                    organization_id=organization_id,
                    code=code,
                    version=version,
                    customer_id=customer_id,
                    effective_from=effective_from,
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(PriceListItem),
                [
                    {
                        "organization_id": organization_id,
                        "price_list_id": price_list_id,
                        "item_id": item_id,
                        "price_ex_tax": price,
                        "created_by": actor_id,
                    }
                    for item_id, price in items.items()
                ],
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="price_list.publish",
                entity_type="price_list",
                entity_id=price_list_id,
                after={
                    "code": code,
                    "version": version,
                    "customer_id": customer_id,
                    "effective_from": effective_from,
                    "items": {str(i): p for i, p in items.items()},
                },
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return price_list_id


def customer_id_exists(session: Session, customer_id: uuid.UUID) -> bool:
    return session.execute(select(Customer.id).where(Customer.id == customer_id)).first() is not None


def list_price_lists(session: Session) -> list[dict[str, Any]]:
    versions = sorted(_versions(session), key=lambda v: (v.code, v.version))
    items = session.execute(select(PriceListItem)).scalars().all()
    names = catalog.names_for(session, {i.item_id for i in items})
    today = business_date()
    return [
        {
            "id": str(v.id),
            "code": v.code,
            "version": v.version,
            "customer_id": None if v.customer_id is None else str(v.customer_id),
            "effective_from": v.effective_from.isoformat(),
            "effective_to": None if v.effective_to is None else v.effective_to.isoformat(),
            "in_force_today": v.in_force_on(today),
            "items": [
                {
                    "item_id": str(i.item_id),
                    "item_code": names[i.item_id][0],
                    "price_ex_tax": str(i.price_ex_tax),
                }
                for i in sorted(items, key=lambda x: names[x.item_id][0])
                if i.price_list_id == v.id
            ],
        }
        for v in versions
    ]


def price_list_in_force(
    session: Session, customer_id: uuid.UUID, on: date, known_at: datetime | None = None
) -> PriceListVersion | None:
    return domain.price_list_in_force(_versions(session), customer_id, on, known_at)


# ---------- the salesman's catalog (G2, G7) ----------


def catalog_for(session: Session, principal: Principal, customer_id: uuid.UUID) -> dict[str, Any]:
    """Finished goods priced for this customer today, packets per carton from the ACTIVE pack spec, and the
    'available today' hint as quantities only (never values), for callers holding `stock.read`."""
    _visible_customer(session, principal, customer_id)
    today = business_date()
    version = price_list_in_force(session, customer_id, today)
    if version is None:
        return {
            "customer_id": str(customer_id),
            "price_list": None,
            "products": [],
            "note": "No price list is in force for this customer today. Ask the factory admin to publish one.",
        }
    prices = _list_prices(session, version.id)
    names = catalog.names_for(session, prices.keys())
    per_carton = recipes.units_per_carton(session, list(prices))
    show_stock = "stock.read" in principal.permissions
    products = []
    for item_id, price in sorted(prices.items(), key=lambda kv: names[kv[0]][0]):
        available: str | None = None
        if show_stock:
            atp = ledger.available_to_promise(session, item_id, as_of=today)["available"]
            available = str(max(int(atp), 0))
        code, name = names[item_id]
        products.append(
            {
                "item_id": str(item_id),
                "code": code,
                "name": name,
                "price_ex_tax": str(price),
                "units_per_carton": per_carton.get(item_id),
                "available_today": available,
            }
        )
    return {
        "customer_id": str(customer_id),
        "price_list": {
            "id": str(version.id),
            "code": version.code,
            "version": version.version,
            "effective_from": version.effective_from.isoformat(),
        },
        "products": products,
        "note": "Prices are ex-tax. GST is added on the invoice. Stock shown is a hint, not a promise.",
    }


# ---------- placing an order (G1, G3, G4) ----------


@dataclass(frozen=True)
class OrderResult:
    order_id: uuid.UUID
    order_no: str
    replayed: bool  # True when an Idempotency-Key replay returned the original order
    stale: bool


def place_order(
    session: Session,
    principal: Principal,
    *,
    customer_id: uuid.UUID,
    price_list_id: uuid.UUID,
    lines: Sequence[OrderLineIn],
    captured_at: datetime | None = None,
    idempotency_key: uuid.UUID | None = None,
    salesman_id: uuid.UUID | None = None,
    order_date: date | None = None,
) -> OrderResult:
    """Receive an order. The price of every line is taken from the version the phone showed and must equal it.
    A salesman orders for assigned customers only and is always the order's salesman."""
    _visible_customer(session, principal, customer_id)
    if principal.sees_only_own_rows:
        salesman_id = principal.user_id
    return receive_order(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        customer_id=customer_id,
        price_list_id=price_list_id,
        lines=lines,
        captured_at=captured_at,
        idempotency_key=idempotency_key,
        salesman_id=salesman_id,
        order_date=order_date,
    )


def receive_order(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    customer_id: uuid.UUID,
    price_list_id: uuid.UUID,
    lines: Sequence[OrderLineIn],
    captured_at: datetime | None = None,
    idempotency_key: uuid.UUID | None = None,
    salesman_id: uuid.UUID | None = None,
    order_date: date | None = None,
) -> OrderResult:
    """The order itself, once the caller's access is checked (`place_order`), or for the benchmark replay."""
    if not customer_id_exists(session, customer_id):
        raise NotFoundError("customer_not_found", "unknown customer", {"customer_id": str(customer_id)})
    versions = {v.id: v for v in _versions(session)}
    shown = versions.get(price_list_id)
    if shown is None:
        raise NotFoundError("price_list_not_found", "unknown price list", {"price_list_id": str(price_list_id)})
    if shown.customer_id is not None and shown.customer_id != customer_id:
        raise OrderError("price_list_not_for_customer", "this price list belongs to another customer")
    plan = domain.plan_order(lines, _list_prices(session, price_list_id))
    received_on = order_date or business_date()
    if captured_at is not None and captured_at.tzinfo is None:
        raise OrderError("captured_at_needs_timezone", "captured_at must carry a time zone")
    digest = idempotency.request_hash(domain.request_doc(customer_id, price_list_id, plan, captured_at))
    org = organization_id
    actor = actor_id

    try:
        with session.begin_nested():
            if idempotency_key is not None:
                stored = idempotency.claim(session, org, idempotency_key, digest)
                if stored is not None:
                    if "order_id" not in stored.body:
                        raise DomainError(
                            "idempotency_key_reused", "this Idempotency-Key belongs to a different kind of request"
                        )
                    return OrderResult(
                        uuid.UUID(stored.body["order_id"]),
                        stored.body["order_no"],
                        replayed=True,
                        stale=bool(stored.body.get("stale")),
                    )
            in_force = domain.price_list_in_force(list(versions.values()), customer_id, received_on)
            stale = domain.is_stale(price_list_id, in_force)
            fy = financial_year(received_on)
            number = session.execute(
                text("SELECT aahar_next_doc_number(:o, :t, :fy)"), {"o": org, "t": domain.DOC_TYPE, "fy": fy}
            ).scalar_one()
            order_no = domain.order_no(fy, int(number))
            order_id = uuid.uuid4()
            session.execute(
                insert(SalesOrder).values(
                    id=order_id,
                    organization_id=org,
                    order_no=order_no,
                    order_date=received_on,
                    customer_id=customer_id,
                    salesman_id=salesman_id,
                    price_list_id=price_list_id,
                    status="SUBMITTED",
                    captured_at=captured_at,
                    idempotency_key=idempotency_key,
                    created_by=actor,
                )
            )
            session.execute(
                insert(OrderLine),
                [
                    {
                        "organization_id": org,
                        "order_id": order_id,
                        "line_no": p.line_no,
                        "item_id": p.item_id,
                        "qty_requested": p.qty,
                        "price_captured": p.price,
                        "created_by": actor,
                    }
                    for p in plan
                ],
            )
            stale_note = None
            if stale:
                stale_note = f"stale price list: shown {shown.code} v{shown.version}, in force " + (
                    "none" if in_force is None else f"{in_force.code} v{in_force.version}"
                )
            session.execute(
                insert(OrderStatusHistory).values(
                    organization_id=org,
                    order_id=order_id,
                    from_status=None,
                    to_status="SUBMITTED",
                    actor_id=actor,
                    reason=stale_note,
                    created_by=actor,
                )
            )
            audit.record(
                session,
                organization_id=org,
                actor_id=actor,
                action="order.create",
                entity_type="sales_order",
                entity_id=order_id,
                after={
                    "order_no": order_no,
                    "order_date": received_on,
                    "customer_id": customer_id,
                    "salesman_id": salesman_id,
                    "price_list_id": price_list_id,
                    "captured_at": None if captured_at is None else captured_at.isoformat(),
                    "stale": stale,
                    "lines": [{"item_id": p.item_id, "qty": p.qty, "price": p.price} for p in plan],
                },
                note=stale_note,
            )
            if idempotency_key is not None:
                idempotency.complete(
                    session, org, idempotency_key, 201, {"order_id": order_id, "order_no": order_no, "stale": stale}
                )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return OrderResult(order_id, order_no, replayed=False, stale=stale)


# ---------- reading orders ----------


def _order_or_404(session: Session, principal: Principal, order_id: uuid.UUID) -> SalesOrder:
    query = select(SalesOrder).where(SalesOrder.id == order_id)
    if principal.sees_only_own_rows:
        query = query.where(SalesOrder.salesman_id == principal.user_id)
    order = session.execute(query).scalar_one_or_none()
    if order is None:
        raise NotFoundError("order_not_found", "unknown order")
    return order


def _lines(session: Session, order_ids: set[uuid.UUID]) -> list[OrderLine]:
    if not order_ids:
        return []
    return list(
        session.execute(
            select(OrderLine).where(OrderLine.order_id.in_(order_ids)).order_by(OrderLine.order_id, OrderLine.line_no)
        ).scalars()
    )


def _stale_info(session: Session, order: SalesOrder, versions: list[PriceListVersion]) -> dict[str, Any] | None:
    """The stale flag is recomputed from the versions known when the factory received the order (created_at), so
    a version published later never changes it."""
    if order.price_list_id is None:
        return None
    in_force = domain.price_list_in_force(versions, order.customer_id, order.order_date, order.created_at)
    if not domain.is_stale(order.price_list_id, in_force):
        return None
    return {
        "in_force_price_list": None
        if in_force is None
        else {"id": str(in_force.id), "code": in_force.code, "version": in_force.version},
        "current_prices": {}
        if in_force is None
        else {str(k): str(v) for k, v in _list_prices(session, in_force.id).items()},
        "note": "The phone showed an older price list. The admin decides which price applies when approving (MP09).",
    }


def get_order(session: Session, principal: Principal, order_id: uuid.UUID) -> dict[str, Any]:
    order = _order_or_404(session, principal, order_id)
    lines = _lines(session, {order.id})
    names = catalog.names_for(session, {ln.item_id for ln in lines})
    customer = session.execute(select(Customer).where(Customer.id == order.customer_id)).scalar_one()
    history = session.execute(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(OrderStatusHistory.changed_at)
    ).scalars()
    versions = _versions(session)
    shown = next((v for v in versions if v.id == order.price_list_id), None)
    stale = _stale_info(session, order, versions)
    source = SourceRef("sales_order", str(order.id))
    total = domain.order_total([(names[ln.item_id][1], ln.qty_requested, ln.price_captured) for ln in lines], source)
    salesman = identity.display_names(session, {order.salesman_id} if order.salesman_id else set())
    return {
        "id": str(order.id),
        "order_no": order.order_no,
        "order_date": order.order_date.isoformat(),
        "status": order.status,
        "captured_at": None if order.captured_at is None else order.captured_at.isoformat(),
        "received_at": order.created_at.isoformat(),
        "customer": {"id": str(customer.id), "code": customer.code, "name": customer.name},
        "salesman": None
        if order.salesman_id is None
        else {"id": str(order.salesman_id), "name": salesman.get(order.salesman_id)},
        "price_list": None if shown is None else {"id": str(shown.id), "code": shown.code, "version": shown.version},
        "lines": [
            {
                "line_no": ln.line_no,
                "item_id": str(ln.item_id),
                "item_code": names[ln.item_id][0],
                "item_name": names[ln.item_id][1],
                "qty": str(ln.qty_requested),
                "price_ex_tax": str(ln.price_captured),
                "value_ex_tax": str(
                    domain.OrderLinePlan(ln.line_no, ln.item_id, ln.qty_requested, ln.price_captured).value
                ),
            }
            for ln in lines
        ],
        "total_ex_tax": total.to_json(),
        "stale": stale is not None,
        "stale_detail": stale,
        "timeline": [
            {
                "from_status": h.from_status,
                "to_status": h.to_status,
                "at": h.changed_at.isoformat(),
                "reason": h.reason,
            }
            for h in history
        ],
    }


def list_orders(session: Session, principal: Principal, days: int | None = None) -> list[dict[str, Any]]:
    query = select(SalesOrder).order_by(SalesOrder.order_date.desc(), SalesOrder.order_no.desc())
    if principal.sees_only_own_rows:
        query = query.where(SalesOrder.salesman_id == principal.user_id)
    if days is not None:
        query = query.where(SalesOrder.order_date >= business_date() - timedelta(days=days))
    orders = list(session.execute(query).scalars())
    lines = _lines(session, {o.id for o in orders})
    customers = (
        dict(
            session.execute(select(Customer.id, Customer.name).where(Customer.id.in_({o.customer_id for o in orders})))
            .tuples()
            .all()
        )
        if orders
        else {}
    )
    versions = _versions(session)
    by_order: dict[uuid.UUID, list[OrderLine]] = {}
    for ln in lines:
        by_order.setdefault(ln.order_id, []).append(ln)
    out = []
    for o in orders:
        mine = by_order.get(o.id, [])
        out.append(
            {
                "id": str(o.id),
                "order_no": o.order_no,
                "order_date": o.order_date.isoformat(),
                "customer_id": str(o.customer_id),
                "customer_name": customers.get(o.customer_id),
                "salesman_id": None if o.salesman_id is None else str(o.salesman_id),
                "status": o.status,
                "captured_at": None if o.captured_at is None else o.captured_at.isoformat(),
                "received_at": o.created_at.isoformat(),
                "packets": str(sum(ln.qty_requested for ln in mine)),
                "value_ex_tax": str(sum((ln.qty_requested * ln.price_captured for ln in mine), Decimal(0))),
                "stale": _stale_info(session, o, versions) is not None,
            }
        )
    return out


def last_order(session: Session, principal: Principal, customer_id: uuid.UUID) -> dict[str, Any] | None:
    """The newest order for this customer (a salesman's own), for 'Repeat last order'. None if there is none."""
    _visible_customer(session, principal, customer_id)
    query = (
        select(SalesOrder)
        .where(SalesOrder.customer_id == customer_id)
        .order_by(SalesOrder.created_at.desc(), SalesOrder.order_no.desc())
        .limit(1)
    )
    if principal.sees_only_own_rows:
        query = query.where(SalesOrder.salesman_id == principal.user_id)
    order = session.execute(query).scalar_one_or_none()
    if order is None:
        return None
    return {
        "id": str(order.id),
        "order_no": order.order_no,
        "order_date": order.order_date.isoformat(),
        "lines": [{"item_id": str(ln.item_id), "qty": str(ln.qty_requested)} for ln in _lines(session, {order.id})],
    }


def summary(session: Session, principal: Principal, days: int = 30) -> dict[str, Any]:
    """Per customer: orders, packets and ex-tax order value over the last `days` days. Ordered, not invoiced."""
    since = business_date() - timedelta(days=days)
    query = (
        select(
            Customer.id,
            Customer.name,
            func.count(func.distinct(SalesOrder.id)),
            func.coalesce(func.sum(OrderLine.qty_requested), 0),
            func.coalesce(func.sum(OrderLine.qty_requested * OrderLine.price_captured), 0),
        )
        .join(SalesOrder, SalesOrder.customer_id == Customer.id)
        .join(OrderLine, OrderLine.order_id == SalesOrder.id)
        .where(SalesOrder.order_date >= since, SalesOrder.status.in_(COUNTED_STATUSES))
        .group_by(Customer.id, Customer.name)
        .order_by(Customer.name)
    )
    if principal.sees_only_own_rows:
        query = query.where(SalesOrder.salesman_id == principal.user_id)
    rows = session.execute(query).tuples().all()
    total = Explained(
        value=round_money(sum((Decimal(v) for *_, v in rows), Decimal(0))),
        unit="INR",
        formula="Σ order values ex-tax per customer",
        inputs=tuple(ExplainedInput(f"{name}: order value ex-tax", Decimal(v), "INR") for _, name, _, _, v in rows),
        method="Ordered, not invoiced (ex-tax)",
    )
    return {
        "since": since.isoformat(),
        "days": days,
        "customers": [
            {
                "customer_id": str(cid),
                "customer_name": name,
                "orders": int(n),
                "packets": str(int(packets)),
                "value_ex_tax": str(Decimal(value)),
            }
            for cid, name, n, packets, value in rows
        ],
        "total_ex_tax": total.to_json(),
        "note": ORDERED_NOT_INVOICED,
        "generated_at": datetime.now(UTC).isoformat(),
    }
