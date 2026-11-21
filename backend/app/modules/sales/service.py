"""Sales use cases: customers, versioned price lists and order taking (MP08, ADR-0015).

Other modules call only this file. Functions run in the caller's transaction and do not commit (the API route
commits). An order is placed in one savepoint:
  assignment check -> price check against the version the phone showed (G1) -> claim the Idempotency-Key (G4) ->
  gapless SO number (G3) -> order + lines -> SUBMITTED status-history row -> audit row -> store the response.
A refusal anywhere rolls the whole savepoint back, the SO number included, so numbers stay gapless.
Approval, reservations and the inbox arrive in MP09.
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
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
from app.modules.production import service as production
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
from app.modules.tax import domain as tax_domain
from app.modules.tax import service as tax_service

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
    credit_limit: Decimal = Decimal(0),
    payment_terms_days: int = 0,
    msme_terms: bool = False,
) -> uuid.UUID:
    """Master data (MP05 seeds; the credit limit from MP09). Customer management screens come later."""
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
            credit_limit=credit_limit,
            payment_terms_days=payment_terms_days,
            msme_terms=msme_terms,
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
        after={
            "code": code,
            "name": name,
            "kind": kind,
            "state_code": state_code,
            "gstin": gstin,
            "credit_limit": credit_limit,
        },
    )
    return customer_id


def set_credit_limit(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, customer_id: uuid.UUID, limit: Decimal
) -> None:
    """Master data: a customer's credit limit in rupees (0 = no limit set), audited."""
    if limit < 0 or limit != round_money(limit):
        raise OrderError("bad_credit_limit", "a credit limit is rupees, at least 0, with at most two decimals")
    customer = session.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if customer is None:
        raise NotFoundError("customer_not_found", "unknown customer")
    before = customer.credit_limit
    customer.credit_limit = limit
    session.flush()
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="customer.credit_limit",
        entity_type="customer",
        entity_id=customer_id,
        before={"credit_limit": before},
        after={"credit_limit": limit},
    )


def set_payment_terms(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    customer_id: uuid.UUID,
    days: int,
    msme_terms: bool,
) -> None:
    """Master data (MP10): payment terms in days and whether MSME terms apply (due date at most 45 days), audited."""
    if days < 0 or days > 365:
        raise OrderError("bad_terms", "payment terms are 0 to 365 days")
    customer = session.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if customer is None:
        raise NotFoundError("customer_not_found", "unknown customer")
    before = {"payment_terms_days": customer.payment_terms_days, "msme_terms": customer.msme_terms}
    customer.payment_terms_days, customer.msme_terms = days, msme_terms
    session.flush()
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="customer.terms",
        entity_type="customer",
        entity_id=customer_id,
        before=before,
        after={"payment_terms_days": days, "msme_terms": msme_terms},
    )


def credit_limit_of(session: Session, customer_id: uuid.UUID) -> Decimal:
    limit: Decimal = session.execute(select(Customer.credit_limit).where(Customer.id == customer_id)).scalar_one()
    return limit


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
    return _order_view(session, _order_or_404(session, principal, order_id))


def _order_view(session: Session, order: SalesOrder) -> dict[str, Any]:
    lines = _lines(session, {order.id})
    names = catalog.names_for(session, {ln.item_id for ln in lines})
    customer = session.execute(select(Customer).where(Customer.id == order.customer_id)).scalar_one()
    history = session.execute(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order.id)
        # rows of one transaction share now(): the receipt row (no from_status) always comes first
        .order_by(OrderStatusHistory.changed_at, OrderStatusHistory.from_status.is_not(None))
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
                "approved": str(ln.qty_approved),
                "backordered": str(ln.qty_backordered),
                "price_ex_tax": str(ln.price_captured),
                "price_final": None if ln.price_final is None else str(ln.price_final),
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


# ---------- MP09: the order inbox and decisions (ADR-0016) ----------

OutstandingProvider = Callable[[Session, uuid.UUID], Explained]
_outstanding_provider: OutstandingProvider | None = None
WAITING_PREFIX = "Waiting for the next batch"


def register_outstanding_provider(provider: OutstandingProvider | None) -> None:
    """H7: collections (MP10, a higher layer) supplies what a customer owes; sales cannot import it."""
    global _outstanding_provider
    _outstanding_provider = provider


def _outstanding(session: Session, customer_id: uuid.UUID) -> Explained:
    if _outstanding_provider is not None:
        return _outstanding_provider(session, customer_id)
    return Explained(
        value=Decimal("0.00"),
        unit="INR",
        formula="no invoices exist until MP10",
        method="Outstanding",
    )


def _lock_order(session: Session, order_id: uuid.UUID) -> SalesOrder:
    order = session.execute(select(SalesOrder).where(SalesOrder.id == order_id).with_for_update()).scalar_one_or_none()
    if order is None:
        raise NotFoundError("order_not_found", "unknown order")
    return order


def _states(lines: Sequence[OrderLine]) -> list[domain.LineState]:
    return [
        domain.LineState(ln.line_no, ln.item_id, ln.qty_requested, ln.qty_approved, ln.qty_backordered) for ln in lines
    ]


def _available(session: Session, organization_id: uuid.UUID, item_ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Lock each item's stores (sorted, so two approvals never deadlock), then read available to promise."""
    out = {}
    for item_id in sorted(item_ids, key=str):
        ledger.lock_item_stores(session, organization_id, item_id)
        out[item_id] = int(ledger.available_to_promise(session, item_id)["available"])
    return out


def _price(ln: OrderLine) -> Decimal:
    return ln.price_final if ln.price_final is not None else ln.price_captured


def _history(
    session: Session, org: uuid.UUID, actor: uuid.UUID | None, order_id: uuid.UUID, frm: str, to: str, reason: str
) -> None:
    session.execute(
        insert(OrderStatusHistory).values(
            organization_id=org,
            order_id=order_id,
            from_status=frm,
            to_status=to,
            actor_id=actor,
            reason=reason,
            created_by=actor,
        )
    )


def _release_lines(
    session: Session, org: uuid.UUID, actor: uuid.UUID | None, line_ids: Sequence[uuid.UUID], reason: str
) -> int:
    released = 0
    for reservation_id, _line, qty in ledger.active_reservations(session, line_ids):
        ledger.release(session, organization_id=org, actor_id=actor, reservation_id=reservation_id, reason=reason)
        released += int(qty)
    return released


@dataclass(frozen=True)
class Decision:
    order_id: uuid.UUID
    status: str
    summary: str


def approve_order(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    order_id: uuid.UUID,
    partial: bool = False,
    agreed: Mapping[int, int] | None = None,
    amend_reason: str | None = None,
    stale_price: str | None = None,
    credit_override_reason: str | None = None,
) -> Decision:
    """H1/H2/H4/H7: approve in one savepoint. Full: every agreed packet reserved or nothing. Partial: reserve what is
    available, backorder the rest. A stale order needs a price choice; over the credit limit needs a reason."""
    order = _lock_order(session, order_id)
    domain.require_status("approve", order.status)
    lines = _lines(session, {order.id})
    states = _states(lines)
    agreed_qty = domain.agreed_quantities(states, dict(agreed or {}))
    cut = any(agreed_qty[s.line_no] < s.requested for s in states)
    reason = domain.require_reason(amend_reason, "agreeing to fewer packets than ordered") if cut else None

    versions = _versions(session)
    stale = _stale_info(session, order, versions)
    new_prices: dict[int, Decimal] = {}
    price_note = None
    if stale is not None:
        if stale_price not in ("captured", "current"):
            raise OrderError(
                "stale_price_choice_required",
                "the phone showed an older price list: choose the phone's price or the current price",
                {"in_force_price_list": stale["in_force_price_list"]},
            )
        if stale_price == "current":
            # "current" is the list in force today, the one the card shows as "list today" (review fix: not the
            # version in force at receipt, which a later version may already have replaced)
            today_list = domain.price_list_in_force(versions, order.customer_id, business_date())
            if today_list is None:
                raise OrderError("no_price_list_in_force", "no price list is in force for this customer today")
            current = _list_prices(session, today_list.id)
            price_note = f"price list {today_list.code} v{today_list.version} in force at approval"
            for ln in lines:
                if ln.item_id not in current:
                    raise OrderError("item_not_on_current_list", "a product is not on the current price list")
                if current[ln.item_id] != ln.price_captured:
                    new_prices[ln.line_no] = current[ln.item_id]

    value = round_money(
        sum(
            (Decimal(agreed_qty[ln.line_no]) * new_prices.get(ln.line_no, _price(ln)) for ln in lines),
            Decimal(0),
        )
    )
    customer = session.execute(select(Customer).where(Customer.id == order.customer_id)).scalar_one()
    credit = domain.credit_check(customer.credit_limit, _outstanding(session, customer.id), value)
    override = None
    if credit.over_limit:
        if not (credit_override_reason or "").strip():
            raise OrderError(
                "credit_limit_exceeded",
                "this order takes the customer over the credit limit: give a reason to approve anyway",
                {"limit": str(credit.limit), "exposure": str(credit.exposure.value)},
            )
        override = domain.require_reason(credit_override_reason, "approving over the credit limit")

    available = _available(session, organization_id, {s.item_id for s in states})
    plan = domain.approval_plan(states, agreed_qty, available, partial)
    by_no = {ln.line_no: ln for ln in lines}
    new_status = domain.status_after([(d.reserve, d.backorder) for d in plan])
    reserved = sum(d.reserve for d in plan)
    owed = sum(d.backorder for d in plan)
    summary = f"approved {reserved} packets" + (f", {owed} backordered" if owed else "")
    notes = [n for n in (reason, price_note and f"price: {price_note}", override and f"credit: {override}") if n]
    try:
        with session.begin_nested():
            for d in plan:
                ln = by_no[d.line_no]
                if d.reserve:
                    ledger.reserve(
                        session,
                        organization_id=organization_id,
                        actor_id=actor_id,
                        order_line_id=ln.id,
                        item_id=ln.item_id,
                        qty_base=Decimal(d.reserve),
                    )
                ln.qty_approved = d.reserve
                ln.qty_backordered = d.backorder
                if d.line_no in new_prices:
                    ln.price_final = new_prices[d.line_no]
                    ln.amend_reason = f"stale price: {price_note}"
            order.status = new_status
            session.flush()
            _history(
                session, organization_id, actor_id, order.id, "SUBMITTED", new_status, "; ".join([summary, *notes])
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="order.approve",
                entity_type="sales_order",
                entity_id=order.id,
                before={"status": "SUBMITTED"},
                after={
                    "status": new_status,
                    "partial": partial,
                    "lines": [
                        {
                            "line_no": d.line_no,
                            "agreed": d.target,
                            "reserved": d.reserve,
                            "backordered": d.backorder,
                            "price_final": new_prices.get(d.line_no),
                        }
                        for d in plan
                    ],
                    "credit_exposure": credit.exposure.value,
                    "credit_limit": credit.limit,
                },
                note="; ".join(notes) or None,
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return Decision(order.id, new_status, summary)


def approve_backorder(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, order_id: uuid.UUID
) -> Decision:
    """H2: cover backordered packets from stock that has become available."""
    order = _lock_order(session, order_id)
    domain.require_status("approve_backorder", order.status)
    lines = _lines(session, {order.id})
    states = _states(lines)
    available = _available(session, organization_id, {s.item_id for s in states if s.backordered})
    plan = domain.backorder_plan([s for s in states if s.backordered], available)
    by_no = {ln.line_no: ln for ln in lines}
    try:
        with session.begin_nested():
            for d in plan:
                ln = by_no[d.line_no]
                if d.reserve:
                    ledger.reserve(
                        session,
                        organization_id=organization_id,
                        actor_id=actor_id,
                        order_line_id=ln.id,
                        item_id=ln.item_id,
                        qty_base=Decimal(d.reserve),
                    )
                ln.qty_approved += d.reserve
                ln.qty_backordered = d.backorder
            new_status = domain.status_after([(ln.qty_approved, ln.qty_backordered) for ln in lines])
            order.status = new_status
            session.flush()
            covered = sum(d.reserve for d in plan)
            left = sum(ln.qty_backordered for ln in lines)
            summary = f"backorder: {covered} more packets reserved" + (f", {left} still owed" if left else "")
            _history(session, organization_id, actor_id, order.id, "PART_APPROVED", new_status, summary)
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="order.approve_backorder",
                entity_type="sales_order",
                entity_id=order.id,
                before={"status": "PART_APPROVED"},
                after={"status": new_status, "reserved": covered, "still_backordered": left},
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return Decision(order.id, new_status, summary)


def _close_order(
    session: Session,
    *,
    action: str,
    to_status: str,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    order_id: uuid.UUID,
    reason: str,
) -> Decision:
    order = _lock_order(session, order_id)
    domain.require_status(action, order.status)
    text_reason = domain.require_reason(reason, "rejecting" if action == "reject" else "cancelling")
    lines = _lines(session, {order.id})
    if any(_invoiced(session, order.id).values()):
        raise OrderError(
            "order_has_invoice", "packets of this order are invoiced: cancel the invoice first (or issue a credit note)"
        )
    before = order.status
    try:
        with session.begin_nested():
            released = _release_lines(
                session, organization_id, actor_id, [ln.id for ln in lines], f"order {to_status.lower()}: {text_reason}"
            )
            for ln in lines:
                ln.qty_approved = 0
                ln.qty_backordered = 0
            order.status = to_status
            session.flush()
            summary = f"{to_status.lower()}: {text_reason}" + (f" ({released} packets released)" if released else "")
            _history(session, organization_id, actor_id, order.id, before, to_status, summary)
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action=f"order.{action}",
                entity_type="sales_order",
                entity_id=order.id,
                before={"status": before},
                after={"status": to_status, "released_packets": released},
                note=text_reason,
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return Decision(order.id, to_status, summary)


def reject_order(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, order_id: uuid.UUID, reason: str
) -> Decision:
    """H3: reject (SUBMITTED or PART_APPROVED), releasing any reservation."""
    return _close_order(
        session,
        action="reject",
        to_status="REJECTED",
        organization_id=organization_id,
        actor_id=actor_id,
        order_id=order_id,
        reason=reason,
    )


def cancel_order(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, order_id: uuid.UUID, reason: str
) -> Decision:
    """H3: cancel an approved order before invoicing, releasing its reservations."""
    return _close_order(
        session,
        action="cancel",
        to_status="CANCELLED",
        organization_id=organization_id,
        actor_id=actor_id,
        order_id=order_id,
        reason=reason,
    )


def amend_line(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    order_id: uuid.UUID,
    line_no: int,
    reason: str,
    price: Decimal | None = None,
    qty: int | None = None,
) -> Decision:
    """H5: change a line's price (into price_final) or lower its agreed quantity, with a reason. The salesman's
    quantity and captured price are never overwritten. Lowering an approved line releases the difference."""
    if (price is None) == (qty is None):
        raise OrderError("one_change_at_a_time", "amend either the price or the quantity")
    order = _lock_order(session, order_id)
    domain.require_status("amend_price" if price is not None else "amend_qty", order.status)
    text_reason = domain.require_reason(reason, "an amendment")
    lines = _lines(session, {order.id})
    line = next((ln for ln in lines if ln.line_no == line_no), None)
    if line is None:
        raise OrderError("unknown_line", "no such line on this order", {"line_no": line_no})
    before: dict[str, Any] = {
        "price_final": line.price_final,
        "qty_approved": line.qty_approved,
        "qty_backordered": line.qty_backordered,
    }
    try:
        with session.begin_nested():
            if price is not None:
                if price < 0 or price != round_money(price):
                    raise OrderError("bad_price", "prices are in rupees with at most two decimals")
                line.price_final = price
                line.amend_reason = text_reason
                summary = f"line {line_no}: price {line.price_captured} -> {price} ({text_reason})"
            else:
                assert qty is not None
                invoiced = _invoiced(session, order.id).get(line.item_id, 0)
                if qty < invoiced:
                    raise OrderError(
                        "below_invoiced",
                        f"{invoiced} packets of this line are already invoiced",
                        {"invoiced": invoiced},
                    )
                approved, back = domain.reduce_line(line.qty_approved, line.qty_backordered, qty)
                if approved < line.qty_approved:
                    _release_lines(session, organization_id, actor_id, [line.id], f"amended: {text_reason}")
                    if approved:
                        ledger.reserve(
                            session,
                            organization_id=organization_id,
                            actor_id=actor_id,
                            order_line_id=line.id,
                            item_id=line.item_id,
                            qty_base=Decimal(approved),
                        )
                line.qty_approved, line.qty_backordered = approved, back
                if not any(ln.qty_approved + ln.qty_backordered for ln in lines):
                    raise OrderError("nothing_to_supply", "every line would be at zero: cancel the order instead")
                summary = f"line {line_no}: agreed {qty} packets ({text_reason})"
            new_status = (
                domain.status_after([(ln.qty_approved, ln.qty_backordered) for ln in lines])
                if order.status != "SUBMITTED"
                else "SUBMITTED"
            )
            old_status = order.status
            order.status = new_status
            session.flush()
            _history(session, organization_id, actor_id, order.id, old_status, new_status, summary)
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="order.amend",
                entity_type="sales_order",
                entity_id=order.id,
                before=before,
                after={
                    "line_no": line_no,
                    "price_final": line.price_final,
                    "qty_approved": line.qty_approved,
                    "qty_backordered": line.qty_backordered,
                    "status": new_status,
                },
                note=text_reason,
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return Decision(order.id, new_status, summary)


def wait_for_batch(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, order_id: uuid.UUID
) -> Decision:
    """H6: keep the order open and record which batch it waits for (or that none is planned)."""
    order = _lock_order(session, order_id)
    domain.require_status("wait", order.status)
    lines = _lines(session, {order.id})
    names = catalog.names_for(session, {ln.item_id for ln in lines})
    parts = []
    for ln in lines:
        batch = production.next_batch_for(session, ln.item_id)
        name = names[ln.item_id][1]
        parts.append(
            f"{name}: no batch planned, ETA unknown"
            if batch is None
            else f"{name}: {batch['run_no']} planned for {batch['run_date']}, about {batch['planned_packets']} packets"
        )
    summary = f"{WAITING_PREFIX}. " + "; ".join(parts)
    _history(session, organization_id, actor_id, order.id, "SUBMITTED", "SUBMITTED", summary)
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="order.wait",
        entity_type="sales_order",
        entity_id=order.id,
        after={"status": "SUBMITTED", "note": summary},
    )
    return Decision(order.id, "SUBMITTED", summary)


INBOX_VIEWS = ("to_decide", "short", "stale", "all")


def _open_qty(ln: OrderLine, status: str) -> int:
    if status == "SUBMITTED":
        return ln.qty_requested
    if status == "PART_APPROVED":
        return ln.qty_backordered
    return 0


def inbox(session: Session, view: str = "to_decide") -> dict[str, Any]:
    """Orders for the admin: open ones (SUBMITTED, PART_APPROVED) with their flags, newest receipts first."""
    if view not in INBOX_VIEWS:
        raise OrderError("unknown_view", f"view must be one of {', '.join(INBOX_VIEWS)}")
    query = select(SalesOrder).order_by(SalesOrder.created_at.desc())
    if view != "all":
        query = query.where(SalesOrder.status.in_(domain.OPEN_STATUSES))
    orders = list(session.execute(query.limit(200)).scalars())
    lines = _lines(session, {o.id for o in orders})
    by_order: dict[uuid.UUID, list[OrderLine]] = {}
    for ln in lines:
        by_order.setdefault(ln.order_id, []).append(ln)
    customers = (
        dict(
            session.execute(select(Customer.id, Customer.name).where(Customer.id.in_({o.customer_id for o in orders})))
            .tuples()
            .all()
        )
        if orders
        else {}
    )
    atp = {item: int(ledger.available_to_promise(session, item)["available"]) for item in {ln.item_id for ln in lines}}
    waiting = _waiting_orders(session, [o.id for o in orders])
    versions = _versions(session)
    rows = []
    for o in orders:
        mine = by_order.get(o.id, [])
        short = any(domain.shortage(_open_qty(ln, o.status), atp.get(ln.item_id, 0)) for ln in mine)
        stale = _stale_info(session, o, versions) is not None
        if (view == "short" and not short) or (view == "stale" and not stale):
            continue
        rows.append(
            {
                "id": str(o.id),
                "order_no": o.order_no,
                "order_date": o.order_date.isoformat(),
                "received_at": o.created_at.isoformat(),
                "status": o.status,
                "customer_name": customers.get(o.customer_id),
                "packets": str(sum(ln.qty_requested for ln in mine)),
                "value_ex_tax": str(sum((ln.qty_requested * _price(ln) for ln in mine), Decimal(0))),
                "short": short,
                "stale": stale,
                "waiting": o.id in waiting and o.status == "SUBMITTED",
            }
        )
    return {"view": view, "orders": rows}


def _waiting_orders(session: Session, order_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not order_ids:
        return set()
    return set(
        session.execute(
            select(OrderStatusHistory.order_id).where(
                OrderStatusHistory.order_id.in_(order_ids), OrderStatusHistory.reason.like(f"{WAITING_PREFIX}%")
            )
        ).scalars()
    )


def inbox_card(session: Session, order_id: uuid.UUID) -> dict[str, Any]:
    """Everything the admin needs to decide (H10): lines with captured vs current price, the stock line (on hand,
    reserved, available to promise), the shortage, the credit check, the stale warning and the options."""
    order = session.execute(select(SalesOrder).where(SalesOrder.id == order_id)).scalar_one_or_none()
    if order is None:
        raise NotFoundError("order_not_found", "unknown order")
    lines = _lines(session, {order.id})
    names = catalog.names_for(session, {ln.item_id for ln in lines})
    customer = session.execute(select(Customer).where(Customer.id == order.customer_id)).scalar_one()
    versions = _versions(session)
    stale = _stale_info(session, order, versions)
    current_list = domain.price_list_in_force(versions, order.customer_id, business_date())
    current_prices = _list_prices(session, current_list.id) if current_list else {}
    out_lines = []
    total_short = 0
    for ln in lines:
        atp = ledger.available_to_promise(session, ln.item_id)
        on_hand, reserved = int(atp["on_hand"]), int(atp["reserved"])
        available = on_hand - reserved
        open_qty = _open_qty(ln, order.status)
        short = domain.shortage(open_qty, available)
        total_short += short
        batch = production.next_batch_for(session, ln.item_id) if short else None
        out_lines.append(
            {
                "line_no": ln.line_no,
                "item_id": str(ln.item_id),
                "item_code": names[ln.item_id][0],
                "item_name": names[ln.item_id][1],
                "requested": str(ln.qty_requested),
                "approved": str(ln.qty_approved),
                "backordered": str(ln.qty_backordered),
                "open": str(open_qty),
                "price_captured": str(ln.price_captured),
                "price_final": None if ln.price_final is None else str(ln.price_final),
                "amend_reason": ln.amend_reason,
                "price_current": None if ln.item_id not in current_prices else str(current_prices[ln.item_id]),
                "available": domain.stock_explained(on_hand, reserved).to_json(),
                "shortage": domain.shortage_explained(open_qty, available).to_json(),
                "can_send_now": str(min(open_qty, max(0, available))),
                "next_batch": batch,
            }
        )
    value = round_money(
        sum(
            (
                Decimal(ln.qty_requested if order.status == "SUBMITTED" else ln.qty_approved + ln.qty_backordered)
                * _price(ln)
                for ln in lines
            ),
            Decimal(0),
        )
    )
    credit = domain.credit_check(customer.credit_limit, _outstanding(session, customer.id), value)
    detail = get_order_any(session, order.id)
    actions = sorted(a for a, allowed in domain.ALLOWED_FROM.items() if order.status in allowed)
    return {
        **detail,
        "customer": {
            **detail["customer"],
            "kind": customer.kind,
            "state_code": customer.state_code,
        },
        "card_lines": out_lines,
        "shortage_total": str(total_short),
        "credit": {
            "limit": None if credit.limit is None else str(credit.limit),
            "outstanding": credit.outstanding.to_json(),
            "exposure": credit.exposure.to_json(),
            "over_limit": credit.over_limit,
        },
        "stale_choice_needed": stale is not None and order.status == "SUBMITTED",
        "waiting": order.status == "SUBMITTED" and order.id in _waiting_orders(session, [order.id]),
        "actions": actions,
        "tax_preview": _tax_preview(session, order, customer, lines, out_lines),
    }


def _tax_preview(
    session: Session,
    order: SalesOrder,
    customer: Customer,
    lines: Sequence[OrderLine],
    card_lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """MP10 (rows 14, 25): what an invoice would carry for each option, and whether the move needs an e-way bill.
    A preview only: the invoice computes it again from the rules in force on its own date."""
    supplier_state = identity.organization(session, order.organization_id)["state_code"]
    on = business_date()
    by_no = {int(c["line_no"]): c for c in card_lines}
    options = {
        "full": {ln.line_no: int(by_no[ln.line_no]["open"]) for ln in lines},
        "partial": {ln.line_no: int(by_no[ln.line_no]["can_send_now"]) for ln in lines},
    }
    out: dict[str, Any] = {"place_of_supply": tax_domain.state_label(customer.state_code)}
    for name, qty in options.items():
        taxed = [
            tax_service.TaxedLineIn(ln.line_no, ln.item_id, qty[ln.line_no], _price(ln))
            for ln in lines
            if qty[ln.line_no]
        ]
        if not taxed:
            out[name] = None
            continue
        try:
            computed = tax_service.compute(
                session, supplier_state=supplier_state, place_of_supply=customer.state_code, on=on, lines=taxed
            )
            verdict = tax_service.eway_verdict(session, computed.regime, computed.totals.total, on)
        except DomainError as exc:
            out[name] = {"error": exc.message}
            continue
        out[name] = {
            "packets": str(sum(t.qty for t in taxed)),
            "regime": computed.regime,
            "taxable": str(computed.totals.taxable),
            "by_tax": {k: str(v) for k, v in computed.totals.by_tax.items()},
            "total": str(computed.totals.total),
            "eway_required": verdict.required,
            "eway_reason": verdict.reason,
        }
    return out


# ---------- MP10: what billing and dispatch need from an order (ADR-0017) ----------

InvoicedProvider = Callable[[Session, uuid.UUID], dict[uuid.UUID, int]]
_invoiced_provider: InvoicedProvider | None = None


def register_invoiced_provider(provider: InvoicedProvider | None) -> None:
    """Billing (L6) tells sales how many packets of an order are on POSTED invoices, per item."""
    global _invoiced_provider
    _invoiced_provider = provider


def _invoiced(session: Session, order_id: uuid.UUID) -> dict[uuid.UUID, int]:
    return {} if _invoiced_provider is None else _invoiced_provider(session, order_id)


@dataclass(frozen=True)
class BillingLine:
    order_line_id: uuid.UUID
    line_no: int
    item_id: uuid.UUID
    approved: int
    backordered: int
    price: Decimal  # price_final if amended, else the captured price


@dataclass(frozen=True)
class BillingOrder:
    id: uuid.UUID
    order_no: str
    status: str
    customer_id: uuid.UUID
    customer_name: str
    customer_state: str
    customer_gstin: str | None
    payment_terms_days: int
    msme_terms: bool
    lines: list[BillingLine]


def order_for_billing(session: Session, order_id: uuid.UUID, lock: bool = False) -> BillingOrder:
    """The approved quantities and prices of an order, with its customer (locked when billing changes it)."""
    order = _lock_order(session, order_id) if lock else session.get(SalesOrder, order_id)
    if order is None:
        raise NotFoundError("order_not_found", "unknown order")
    customer = session.execute(select(Customer).where(Customer.id == order.customer_id)).scalar_one()
    return BillingOrder(
        id=order.id,
        order_no=order.order_no,
        status=order.status,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_state=customer.state_code,
        customer_gstin=customer.gstin,
        payment_terms_days=customer.payment_terms_days,
        msme_terms=customer.msme_terms,
        lines=[
            BillingLine(ln.id, ln.line_no, ln.item_id, ln.qty_approved, ln.qty_backordered, _price(ln))
            for ln in _lines(session, {order.id})
        ],
    )


def customer_terms(session: Session, customer_id: uuid.UUID) -> dict[str, Any]:
    c = session.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if c is None:
        raise NotFoundError("customer_not_found", "unknown customer", {"customer_id": str(customer_id)})
    return {
        "id": str(c.id),
        "code": c.code,
        "name": c.name,
        "state_code": c.state_code,
        "gstin": c.gstin,
        "payment_terms_days": c.payment_terms_days,
        "msme_terms": c.msme_terms,
        "credit_limit": str(c.credit_limit),
    }


def customers_brief(session: Session) -> list[dict[str, Any]]:
    return [customer_terms(session, c) for c in session.execute(select(Customer.id).order_by(Customer.code)).scalars()]


def sync_billing_status(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    order_id: uuid.UUID,
    invoiced: dict[uuid.UUID, int],
    dispatched: dict[uuid.UUID, int],
    reason: str,
) -> str:
    """After an invoice, a cancellation or a dispatch: set APPROVED / PART_APPROVED / INVOICED / DISPATCHED from the
    packets invoiced and dispatched per item, with a history row when it changes."""
    order = _lock_order(session, order_id)
    if order.status not in domain.BILLING_STATUSES:
        raise OrderError("order_not_approved", f"this order is {order.status}: only approved orders are billed")
    lines = _lines(session, {order.id})
    new_status = domain.billing_status(
        [
            (ln.qty_approved, ln.qty_backordered, invoiced.get(ln.item_id, 0), dispatched.get(ln.item_id, 0))
            for ln in lines
        ]
    )
    if new_status != order.status:
        before = order.status
        order.status = new_status
        session.flush()
        _history(session, organization_id, actor_id, order.id, before, new_status, reason)
    return new_status


def active_reservations_by_item(session: Session, order_id: uuid.UUID) -> dict[uuid.UUID, list[tuple[uuid.UUID, int]]]:
    """The order's ACTIVE reservations, per item: [(reservation id, packets)] (dispatch consumes them)."""
    lines = _lines(session, {order_id})
    item_of = {ln.id: ln.item_id for ln in lines}
    out: dict[uuid.UUID, list[tuple[uuid.UUID, int]]] = {}
    for res_id, line_id, qty in ledger.active_reservations(session, list(item_of)):
        out.setdefault(item_of[line_id], []).append((res_id, int(qty)))
    return out


def order_line_ids(session: Session, order_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    """item id -> order line id (each item appears once per order)."""
    return {ln.item_id: ln.id for ln in _lines(session, {order_id})}


def orders_to_bill(session: Session) -> list[dict[str, Any]]:
    """Approved orders with packets not yet invoiced (the 'Ready to invoice' list)."""
    orders = list(
        session.execute(
            select(SalesOrder)
            .where(SalesOrder.status.in_(("APPROVED", "PART_APPROVED")))
            .order_by(SalesOrder.created_at)
        ).scalars()
    )
    out = []
    for o in orders:
        lines = _lines(session, {o.id})
        done = _invoiced(session, o.id)
        open_qty = sum(max(0, ln.qty_approved - done.get(ln.item_id, 0)) for ln in lines)
        if open_qty <= 0:
            continue
        customer = session.execute(select(Customer).where(Customer.id == o.customer_id)).scalar_one()
        out.append(
            {
                "order_id": str(o.id),
                "order_no": o.order_no,
                "status": o.status,
                "customer_name": customer.name,
                "packets_to_invoice": str(open_qty),
                "value_ex_tax": str(
                    sum((max(0, ln.qty_approved - done.get(ln.item_id, 0)) * _price(ln) for ln in lines), Decimal(0))
                ),
            }
        )
    return out


def get_order_any(session: Session, order_id: uuid.UUID) -> dict[str, Any]:
    """`get_order` for staff who see every order (the inbox): no salesman row filter."""
    order = session.execute(select(SalesOrder).where(SalesOrder.id == order_id)).scalar_one_or_none()
    if order is None:
        raise NotFoundError("order_not_found", "unknown order")
    return _order_view(session, order)
