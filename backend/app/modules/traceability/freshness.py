"""The shelf freshness radar (MP13, T5, ADR-0020). Read-only estimates; nothing is posted.

Per customer x finished-goods lot: packets delivered in the last 90 days minus the packets the customer is estimated
to have sold, read from their own order rhythm for that item (oldest best-before sold first). The range comes from
the slowest and fastest gaps between their orders; with fewer than two orders there is not enough history, so the
whole delivery may still be on the shelf. A lot is flagged when its best-before is within `freshness.alert_days`
(an effective-dated DEMO setting) and the high estimate is above zero.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.calendar import business_date
from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money
from app.modules.catalog import service as catalog
from app.modules.dispatch import service as dispatch
from app.modules.sales import service as sales
from app.modules.traceability import domain
from app.modules.traceability.domain import LotDelivery, OrderDay

ALERT_DAYS: Final = "freshness.alert_days"
WINDOW_DAYS: Final = 90
NOTE: Final = (
    "An estimate from each customer's order rhythm over the last 90 days, not a shelf count: the low and high"
    " come from their fastest and slowest gaps between orders."
)


class FreshnessError(DomainError):
    pass


def radar(session: Session, customer_ids: set[uuid.UUID] | None = None, on: date | None = None) -> dict[str, Any]:
    """Every customer x lot that may still be on a shelf, flagged ones first. `customer_ids` limits it (salesman)."""
    today = on or business_date()
    alert = effective_settings.decimal_on(session, ALERT_DAYS, today)
    if alert is None:
        raise FreshnessError("setting_missing", f"the setting {ALERT_DAYS} is not configured", {"key": ALERT_DAYS})
    since = today - timedelta(days=WINDOW_DAYS)
    groups: dict[tuple[uuid.UUID, uuid.UUID], list[dispatch.Delivery]] = {}
    for d in dispatch.deliveries_since(session, since):
        if customer_ids is None or d.customer_id in customer_ids:
            groups.setdefault((d.customer_id, d.item_id), []).append(d)
    points: dict[tuple[uuid.UUID, uuid.UUID], list[sales.OrderPoint]] = {}
    for p in sales.order_points(session, since):
        points.setdefault((p.customer_id, p.item_id), []).append(p)
    names = catalog.names_for(session, {item for _, item in groups})
    rows: list[dict[str, Any]] = []
    for (customer, item), sent in groups.items():
        orders = points.get((customer, item), [])
        rates, estimates = domain.shelf_estimates(
            [
                LotDelivery(
                    str(d.lot_id), d.lot_no, d.best_before, d.dispatch_date, d.qty, str(d.dispatch_id), d.dispatch_no
                )
                for d in sent
            ],
            [OrderDay(o.order_date, o.packets) for o in orders],
            today,
            int(alert),
        )
        price = orders[-1].price if orders else None
        for e in estimates:
            if e.high.value <= 0:
                continue
            at_risk = (
                None
                if price is None
                else Explained(
                    round_money(e.high.value * price),
                    "INR",
                    "high estimate on the shelf x the customer's latest price",
                    (
                        ExplainedInput("packets that may be on the shelf", e.high.value, "packets"),
                        ExplainedInput(
                            f"price on {orders[-1].order_no}",
                            price,
                            "INR/packet",
                            SourceRef("sales_order", str(orders[-1].order_id)),
                        ),
                    ),
                    method="estimate from order rhythm",
                )
            )
            rows.append(
                {
                    "customer_id": str(customer),
                    "customer_code": sent[0].customer_code,
                    "customer_name": sent[0].customer_name,
                    "item_code": names[item][0],
                    "item_name": names[item][1],
                    "lot_id": e.lot_id,
                    "lot_no": e.lot_no,
                    "best_before": None if e.best_before is None else e.best_before.isoformat(),
                    "days_to_best_before": e.days_to_best_before,
                    "delivered": e.delivered.to_json(),
                    "low": str(e.low),
                    "central": None if e.central is None else str(e.central),
                    "high": e.high.to_json(),
                    "enough_history": rates is not None,
                    "rates": None
                    if rates is None
                    else {
                        "orders": rates.orders,
                        "span_days": rates.span_days,
                        "central": str(rates.central),
                        "slow": str(rates.slow),
                        "fast": str(rates.fast),
                    },
                    "flagged": e.flagged,
                    "value_at_risk": None if at_risk is None else at_risk.to_json(),
                }
            )
    rows.sort(
        key=lambda r: (
            not r["flagged"],
            r["days_to_best_before"] if r["days_to_best_before"] is not None else 10**6,
            -Decimal(r["high"]["value"]),
            r["customer_code"],
            r["lot_no"],
        )
    )
    return {
        "as_of": today.isoformat(),
        "alert_days": str(alert),
        "window_days": WINDOW_DAYS,
        "flagged": sum(1 for r in rows if r["flagged"]),
        "rows": rows,
        "note": NOTE,
    }


def top_alert(session: Session, on: date | None = None) -> dict[str, Any] | None:
    """The flagged row with the most rupees at stake (the Morning brief's "Visit" candidate), or None."""
    try:
        rows = radar(session, on=on)["rows"]
    except FreshnessError:
        return None
    flagged: list[dict[str, Any]] = [r for r in rows if r["flagged"] and r["value_at_risk"] is not None]
    if not flagged:
        return None
    best: dict[str, Any] = max(flagged, key=lambda r: (Decimal(r["value_at_risk"]["value"]), r["customer_code"]))
    return best
