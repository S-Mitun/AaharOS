"""Reports (MP11, ADR-0018): read-only views over posted records, each a `Report` (domain.py) that renders as JSON,
CSV, XLSX or a printable page. Every row carries the source document it drills down to (`_source`).

Module 1 (K1, K2): sales register, purchase register, stock summary, stock ledger, production report, receivables
ageing. The GST summary and export (K3), the close cockpit (K5) and the evidence pack (K6) build on these.
"""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core.calendar import business_date
from app.core.db import scoped_org
from app.core.errors import DomainError
from app.modules.billing import service as billing
from app.modules.collections import service as collections
from app.modules.costing import service as costing
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.procurement import service as procurement
from app.modules.production import service as production
from app.modules.reports.domain import Column, Report, sum_column
from app.modules.sales import service as sales

AGEING_BUCKETS: Final = ((0, 15, "0-15"), (16, 45, "16-45"), (46, 90, "46-90"), (91, None, "90+"))
MSME_DAYS: Final = 45


class ReportError(DomainError):
    """A report request that cannot be answered."""


def _org_name(session: Session) -> str:
    org = scoped_org(session)
    if org is None:
        raise ReportError("no_organization", "reports need an organization")
    o = identity.organization(session, org)
    return f"{o['name']} ({o['code']})"


def _range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    to = date_to or business_date()
    frm = date_from or to.replace(day=1)
    if frm > to:
        raise ReportError("bad_date_range", "the start date is after the end date")
    return frm, to


def _filters(frm: date, to: date, **more: Any) -> dict[str, str]:
    out = {"from": frm.isoformat(), "to": to.isoformat()}
    out.update({k: str(v) for k, v in more.items() if v is not None})
    return out


# ---------- sales register ----------

SALES_COLUMNS = [
    Column("doc_date", "Date", "date"),
    Column("doc_no", "Document"),
    Column("doc_type", "Type"),
    Column("status", "Status"),
    Column("customer", "Customer"),
    Column("gstin", "GSTIN"),
    Column("place_of_supply", "Place of supply"),
    Column("hsn", "HSN"),
    Column("item", "Product"),
    Column("qty", "Qty", "qty"),
    Column("taxable", "Taxable", "money"),
    Column("cgst", "CGST", "money"),
    Column("sgst", "SGST", "money"),
    Column("igst", "IGST", "money"),
    Column("total", "Total", "money"),
]


def _counts(row: dict[str, Any]) -> bool:
    return bool(row["status"] == "POSTED")


def sales_register(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
) -> Report:
    frm, to = _range(date_from, date_to)
    rows = billing.register_rows(session, frm, to)
    if customer_id is not None:
        rows = [r for r in rows if r["customer_id"] == str(customer_id)]
    if item_id is not None:
        rows = [r for r in rows if r["item_id"] == str(item_id)]
    for r in rows:
        r["_source"] = {"type": "invoice", "id": r["invoice_id"] if r["doc_type"] == "CN" else r["doc_id"]}
    return Report(
        name="sales-register",
        title="Sales register",
        organization=_org_name(session),
        filters=_filters(frm, to, customer=customer_id, item=item_id),
        columns=SALES_COLUMNS,
        rows=rows,
        totals={k: sum_column(rows, k, _counts) for k in ("qty", "taxable", "cgst", "sgst", "igst", "total")},
        notes=[
            "Totals count POSTED invoices and credit notes (credit notes are negative); cancelled invoices are listed "
            "with their status and left out of the totals.",
        ],
    )


# ---------- purchase register (MP05, reused) ----------


def purchase_register(session: Session, date_from: date | None = None, date_to: date | None = None) -> Report:
    frm, to = _range(date_from, date_to)
    data = procurement.register(session, date_from=frm, date_to=to)
    rows = data["rows"]
    for r in rows:
        r["_source"] = {"type": "purchase_receipt", "id": r["receipt_id"]}
    return Report(
        name="purchase-register",
        title="Purchase register",
        organization=_org_name(session),
        filters=_filters(frm, to),
        columns=[
            Column("received_on", "Date", "date"),
            Column("receipt_no", "Receipt"),
            Column("status", "Status"),
            Column("supplier_name", "Supplier"),
            Column("supplier_invoice_ref", "Supplier invoice"),
            Column("item_code", "Item"),
            Column("qty", "Qty", "qty"),
            Column("unit", "Unit"),
            Column("rate", "Rate", "money"),
            Column("value", "Stock value", "money"),
            Column("freight", "Freight (not in stock)", "money"),
        ],
        rows=rows,
        totals={"value": data["totals"]["stock_value"], "freight": data["totals"]["freight_excluded_from_stock"]},
        notes=[data["note"], "Purchase GST is input credit, never stock value."],
    )


# ---------- stock ----------


def stock_summary(session: Session, date_from: date | None = None, date_to: date | None = None) -> Report:
    frm, to = _range(date_from, date_to)
    rows = ledger.movement_summary(session, frm, to)
    for r in rows:
        r["_source"] = {"type": "stock_ledger", "id": r["item_id"]}
    return Report(
        name="stock-summary",
        title="Stock summary",
        organization=_org_name(session),
        filters=_filters(frm, to),
        columns=[
            Column("store", "Store"),
            Column("item_code", "Item"),
            Column("unit", "Unit"),
            Column("opening_qty", "Opening qty", "qty"),
            Column("opening_value", "Opening value", "money"),
            Column("in_qty", "In qty", "qty"),
            Column("in_value", "In value", "money"),
            Column("out_qty", "Out qty", "qty"),
            Column("out_value", "Out value", "money"),
            Column("value_adjustments", "Value adjustments", "money"),
            Column("closing_qty", "Closing qty", "qty"),
            Column("closing_value", "Closing value", "money"),
        ],
        rows=rows,
        totals={
            k: sum_column(rows, k)
            for k in ("opening_value", "in_value", "out_value", "value_adjustments", "closing_value")
        },
        notes=[
            "Closing = opening + in - out + value adjustments, exactly. Value adjustments are run-cost true-ups "
            "(labour and gas added to finished goods after they were made).",
            "Stores only; virtual locations (supplier, customer, scrap) are where stock comes from or goes to.",
        ],
    )


def stock_ledger(
    session: Session, item_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None
) -> Report:
    frm, to = _range(date_from, date_to)
    data = ledger.stock_ledger(session, item_id=item_id, date_from=frm, date_to=to, limit=2000)
    rows = [
        {
            "posting_date": r["posting_date"],
            "kind": r["kind"],
            "location": r["location"],
            "item_code": r["item_code"],
            "qty": r["qty"],
            "uom": r["uom"],
            "value": r["value"],
            "running_qty": r["running"]["qty"],
            "running_value": r["running"]["value"],
            "reason": r["reason"],
            "_source": r["source"],
        }
        for r in data["rows"]
    ]
    opening = data["opening"][0] if data["opening"] else None
    notes = ["Every movement in posting order with its source document and the running balance."]
    if opening:
        notes.insert(0, f"Opening on {frm.isoformat()}: {opening['qty']} {opening['uom']}, value {opening['value']}.")
    if data["truncated"]:
        notes.append("Showing the first 2,000 movements: narrow the dates to see the rest.")
    return Report(
        name="stock-ledger",
        title="Stock ledger",
        organization=_org_name(session),
        filters=_filters(frm, to, item=item_id),
        columns=[
            Column("posting_date", "Date", "date"),
            Column("kind", "Movement"),
            Column("location", "Location"),
            Column("item_code", "Item"),
            Column("qty", "Qty", "qty"),
            Column("uom", "Unit"),
            Column("value", "Value", "money"),
            Column("running_qty", "Balance qty", "qty"),
            Column("running_value", "Balance value", "money"),
            Column("reason", "Reason"),
        ],
        rows=rows,
        notes=notes,
    )


# ---------- production ----------


def production_report(session: Session, date_from: date | None = None, date_to: date | None = None) -> Report:
    frm, to = _range(date_from, date_to)
    rows = []
    for run in production.list_runs(session):
        run_day = date.fromisoformat(run["run_date"])
        if run["status"] != "COMPLETED" or not frm <= run_day <= to:
            continue
        run_id = uuid.UUID(run["id"])
        a = production.run_analysis(session, run_id)
        c = costing.run_costing(session, run_id)
        planned = sum((pl.expected_units for pl in a.pack_lines), Decimal(0))
        good = sum((pl.good_units or 0 for pl in a.pack_lines), 0)
        yield_pct = next((pl.yield_variance.pct_display for pl in a.pack_lines if pl.yield_variance), None)
        mb = a.mass_balance
        rows.append(
            {
                "run_no": a.run_no,
                "run_date": run["run_date"],
                "recipe": run["recipe"],
                "planned_packets": str(planned.normalize()),
                "good_packets": str(good),
                "yield_variance_pct": "" if yield_pct is None else str(yield_pct),
                "flags": ", ".join(a.flags),
                "scrap_kg": "" if mb is None else str((mb.scrap_g / 1000).normalize()),
                "unexplained_kg": "" if mb is None else str((mb.unexplained_g / 1000).normalize()),
                "run_cost": str(c.cost.total.value),
                "cost_per_packet": "" if c.cost.per_good_unit is None else str(c.cost.per_good_unit.value),
                "variance_vs_standard": "" if c.waterfall is None else str(c.waterfall.total.value),
                "cost_status": run["cost_status"],
                "_source": {"type": "production_run", "id": run["id"]},
            }
        )
    return Report(
        name="production",
        title="Production report",
        organization=_org_name(session),
        filters=_filters(frm, to),
        columns=[
            Column("run_no", "Batch"),
            Column("run_date", "Date", "date"),
            Column("recipe", "Recipe"),
            Column("planned_packets", "Planned packets", "qty"),
            Column("good_packets", "Good packets", "qty"),
            Column("yield_variance_pct", "Yield variance %", "pct"),
            Column("flags", "Flagged"),
            Column("scrap_kg", "Waste kg", "qty"),
            Column("unexplained_kg", "Unexplained kg", "qty"),
            Column("run_cost", "Run cost", "money"),
            Column("cost_per_packet", "Cost per good packet", "money"),
            Column("variance_vs_standard", "Variance vs standard (+ = unfavourable)", "money"),
            Column("cost_status", "Cost status"),
        ],
        rows=rows,
        totals={
            k: sum_column(rows, k) for k in ("planned_packets", "good_packets", "run_cost", "variance_vs_standard")
        },
        notes=["Completed batches only. Cost is direct (materials at WAC + labour + gas); overheads are not absorbed."],
    )


# ---------- receivables ageing ----------


def _bucket(days: int) -> str:
    for low, high, label in AGEING_BUCKETS:
        if days >= low and (high is None or days <= high):
            return label
    return AGEING_BUCKETS[0][2]


def receivables_ageing(session: Session, as_of: date | None = None) -> Report:
    on = as_of or business_date()
    rows = []
    for c in sales.customers_brief(session):
        for inv in collections.open_invoices(session, uuid.UUID(c["id"])):
            owed = inv.outstanding
            if owed <= 0 or inv.invoice_date > on:
                continue
            age = (on - inv.invoice_date).days
            row = {
                "customer": c["name"],
                "invoice_no": inv.invoice_no,
                "invoice_date": inv.invoice_date.isoformat(),
                "due_date": inv.due_date.isoformat(),
                "age_days": str(age),
                "outstanding": str(owed),
                "beyond_msme_45_days": age > MSME_DAYS,
                "_source": {"type": "invoice", "id": str(inv.invoice_id)},
            }
            for _, _, label in AGEING_BUCKETS:
                row[label] = str(owed) if _bucket(age) == label else "0.00"
            rows.append(row)
    return Report(
        name="receivables-ageing",
        title="Receivables ageing",
        organization=_org_name(session),
        filters={"as_of": on.isoformat()},
        columns=[
            Column("customer", "Customer"),
            Column("invoice_no", "Invoice"),
            Column("invoice_date", "Invoice date", "date"),
            Column("due_date", "Due", "date"),
            Column("age_days", "Age (days)", "qty"),
            *(Column(label, f"{label} days", "money") for _, _, label in AGEING_BUCKETS),
            Column("outstanding", "Outstanding", "money"),
            Column("beyond_msme_45_days", "Past 45 days (MSME)", "bool"),
        ],
        rows=rows,
        totals={k: sum_column(rows, k) for k in ("outstanding", *(label for _, _, label in AGEING_BUCKETS))},
        notes=[
            "Age is counted from the invoice date. The MSME marker flags invoices older than 45 days (MSMED Act s.15).",
        ],
    )


# ---------- registry ----------

REPORTS: Final[dict[str, Callable[..., Report]]] = {
    "sales-register": sales_register,
    "purchase-register": purchase_register,
    "stock-summary": stock_summary,
    "production": production_report,
    "receivables-ageing": receivables_ageing,
}


def catalogue() -> list[dict[str, str]]:
    titles = {
        "sales-register": "Sales register (by customer and product, net of credit notes)",
        "purchase-register": "Purchase register",
        "stock-summary": "Stock summary (opening, in, out, closing by quantity and value)",
        "production": "Production report (planned vs actual, yield, waste, variance in rupees)",
        "receivables-ageing": "Receivables ageing (0-15, 16-45, 46-90, 90+, MSME 45-day marker)",
    }
    return [{"name": k, "title": v} for k, v in titles.items()]
