"""The Owner Morning Brief (MP12, ADR-0019 L6): at most five cards and "Today's 3 actions", ranked by rupee impact.

Read-only. Every figure is read from posted records or from the planner, and carries an Explained.
Cards: today's orders · available vs pending · where profit leaks (top 3 ₹) · material runway · money to collect.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core.calendar import business_date
from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money
from app.modules.collections import service as collections
from app.modules.costing import service as costing
from app.modules.planning import domain
from app.modules.planning import service as planning
from app.modules.production import service as production
from app.modules.sales import service as sales

LEAK_DAYS: Final = 30  # batches this recent feed "where profit leaks"
MSME_DAYS: Final = 45  # MSMED Act: a buyer pays an MSME supplier within 45 days


def _plural(n: int, one: str, many: str) -> str:
    return (one if n == 1 else many).format(n=n)


def _inr(value: Decimal, formula: str, inputs: tuple[ExplainedInput, ...], method: str) -> Explained:
    return Explained(value=round_money(value), unit="INR", formula=formula, inputs=inputs, method=method)


def _leaks(session: Session, today: date) -> list[dict[str, Any]]:
    since = today - timedelta(days=LEAK_DAYS)
    found = []
    for run in production.list_runs(session):
        if run["status"] != "COMPLETED" or date.fromisoformat(run["run_date"]) < since:
            continue
        try:
            waterfall = costing.run_costing(session, uuid.UUID(run["id"])).waterfall
        except DomainError:
            continue
        if waterfall is None:
            continue
        for c in waterfall.components:
            if c.value > 0:
                found.append((c, run))
    found.sort(key=lambda x: (-x[0].value, x[1]["run_no"]))
    return [
        {
            "run_id": run["id"],
            "run_no": run["run_no"],
            "label": c.label,
            "value": c.explained.to_json(),
            "link": f"/leaks/{run['id']}",
        }
        for c, run in found[:3]
    ]


def _money(session: Session, today: date) -> dict[str, Any]:
    customers = []
    total = overdue = past_msme = Decimal(0)
    for c in sales.customers_brief(session):
        rows = [r for r in collections.open_invoices(session, uuid.UUID(c["id"])) if r.outstanding > 0]
        owed = sum((r.outstanding for r in rows), Decimal(0))
        late = sum((r.outstanding for r in rows if today > r.due_date), Decimal(0))
        msme = sum((r.outstanding for r in rows if (today - r.invoice_date).days > MSME_DAYS), Decimal(0))
        total, overdue, past_msme = total + owed, overdue + late, past_msme + msme
        if late > 0:
            customers.append({"customer_id": c["id"], "customer_name": c["name"], "overdue": round_money(late)})
    customers.sort(key=lambda x: (-x["overdue"], x["customer_name"]))
    return {
        "outstanding": str(round_money(total)),
        "overdue": _inr(
            overdue,
            "sum of unpaid invoice balances past their due date",
            tuple(ExplainedInput(x["customer_name"], x["overdue"], "INR") for x in customers),
            "Receivables",
        ).to_json(),
        "past_msme_45_days": str(round_money(past_msme)),
        "top_overdue": [{**x, "overdue": str(x["overdue"])} for x in customers[:3]],
        "link": "/admin/collections",
    }


def morning_brief(session: Session, on: date | None = None) -> dict[str, Any]:
    today = on or business_date()
    orders = sales.day_orders(session, today)
    plan: dict[str, Any] | None = None
    plan_note: str | None = None
    try:
        plan = planning.batch_plan(session, today)
    except DomainError as exc:
        plan_note = exc.message
    runway = planning.runway(session)
    leaks = _leaks(session, today)
    money = _money(session, today)

    candidates: list[domain.Action] = []
    if orders["to_decide"]["count"]:
        v = Decimal(orders["to_decide"]["value"])
        candidates.append(
            domain.Action(
                "decide",
                _plural(orders["to_decide"]["count"], "Decide {n} waiting order", "Decide {n} waiting orders"),
                v,
                "/admin/orders",
                _inr(
                    v,
                    "value ex-tax of orders not yet approved",
                    (ExplainedInput("orders waiting", Decimal(orders["to_decide"]["count"]), "orders"),),
                    "Order inbox",
                ),
            )
        )
    if plan is not None:
        value_met = Decimal(plan["value_met"])
        made = [b for b in plan["batches"] if b["batches"] and Decimal(b["batches"]["value"]) > 0]
        if value_met > 0 and made:
            what = ", ".join(
                _plural(int(b["batches"]["value"]), "{n} batch of ", "{n} batches of ") + b["pack_code"] for b in made
            )
            candidates.append(
                domain.Action(
                    "make",
                    f"Start {what} today",
                    value_met,
                    "/production/planner",
                    _inr(
                        value_met,
                        "value ex-tax of the open packets these batches supply",
                        tuple(
                            ExplainedInput(f"{b['pack_code']} batches", Decimal(b["batches"]["value"]), "batches")
                            for b in made
                        ),
                        "Batch planner (CP-SAT)",
                    ),
                )
            )
        waiting = (
            sum((Decimal(d["shortfall"]) * Decimal(d["value_per_packet"]) for d in plan["demand"]), Decimal(0))
            - value_met
        )
        if waiting > 0 and plan["materials_short"]:
            short = ", ".join(m["item_code"] for m in plan["materials_short"])
            candidates.append(
                domain.Action(
                    "buy",
                    f"Order {short}",
                    waiting,
                    "/production/planner",
                    _inr(
                        waiting,
                        "value of open packets today's plan cannot supply (short of materials)",
                        (
                            ExplainedInput("open packets short, at their price", waiting + value_met, "INR"),
                            ExplainedInput("supplied by today's plan", value_met, "INR"),
                        ),
                        "Batch planner (CP-SAT)",
                    ),
                )
            )
    if money["top_overdue"]:
        top = money["top_overdue"][0]
        v = Decimal(top["overdue"])
        candidates.append(
            domain.Action(
                "collect",
                f"Call {top['customer_name']} about the overdue balance",
                v,
                "/admin/collections",
                _inr(
                    v,
                    "unpaid balance past the due date",
                    (ExplainedInput("overdue", v, "INR", SourceRef("customer", top["customer_id"])),),
                    "Receivables",
                ),
            )
        )
    if leaks:
        top_leak = leaks[0]
        v = Decimal(top_leak["value"]["value"])
        candidates.append(
            domain.Action(
                "leak",
                f"Check {top_leak['label']} on batch {top_leak['run_no']}",
                v,
                top_leak["link"],
                _inr(
                    v,
                    "actual cost above standard for this component",
                    (ExplainedInput("variance", v, "INR", SourceRef("production_run", top_leak["run_id"])),),
                    "Where profit leaks",
                ),
            )
        )

    return {
        "date": today.isoformat(),
        "cards": {
            "orders": {**orders, "link": "/admin/orders"},
            "available_vs_pending": {
                "items": [] if plan is None else plan["demand"],
                "note": plan_note,
                "link": "/production/planner",
            },
            "leaks": {"top": leaks, "link": "/leaks"},
            "runway": {
                "packs": [
                    {"pack_code": r["pack_code"], "binding": r["binding"], "full_batches": r["full_batches"]}
                    for r in runway
                ],
                "link": "/production/planner",
            },
            "money": money,
        },
        "actions": [a.to_json() for a in domain.rank_actions(candidates)],
    }
