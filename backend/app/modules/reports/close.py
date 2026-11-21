"""Month-end close (MP11, ADR-0018, K5): the Close Cockpit and closing / reopening a month.

The cockpit is a checklist of what is still open (counts with links to the screen that fixes it) and this
organization's integrity checks. Open items are warnings the closer sees and may accept; a failing integrity check
blocks the close. Closing writes a period lock (the database then refuses postings dated in that month, AH003);
reopening needs a reason and keeps the lock row (migration 0011).
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.calendar import business_date
from app.modules.audit import service as audit
from app.modules.billing import service as billing
from app.modules.collections import service as collections
from app.modules.ledger import service as ledger
from app.modules.production import service as production
from app.modules.reports import gst
from app.modules.reports.service import ReportError, org_name
from app.modules.sales import service as sales


def integrity_checks(session: Session, organization_id: uuid.UUID) -> list[dict[str, Any]]:
    """The conservation laws and guards for one organization (row-level security keeps the others out)."""
    chain = audit.verify(session, organization_id)
    mass = [m for m in production.mass_law_results(session) if m["organization_id"] == str(organization_id)]
    checks = [
        ("Audit chain intact", chain.ok, 0 if chain.ok else 1),
        ("Law 1 quantity: every stock journal balances", None, len(ledger.journal_imbalances(session))),
        ("Stock balances rebuild identically from the ledger", None, len(ledger.projection_diff(session))),
        (
            "Law 2 value: every batch's lots = materials + run costs",
            None,
            len(production.run_value_mismatches(session)),
        ),
        ("Law 3 mass: every batch reconciles, gaps disclosed", None, sum(1 for m in mass if not m["holds"])),
        ("Law 4 tax: invoice tax lines = GST summary = export", None, len(gst.law4(session))),
        ("Invoices add up to their headers", None, len(billing.tax_line_mismatches(session))),
        ("No store promises more stock than it holds", None, len(ledger.over_reserved(session))),
    ]
    return [
        {"check": label, "ok": (problems == 0) if ok is None else ok, "problems": problems}
        for label, ok, problems in checks
    ]


def cockpit(session: Session, organization_id: uuid.UUID, month: date | None = None) -> dict[str, Any]:
    period = (month or business_date()).replace(day=1)
    frm, to = gst.month_range(period)
    runs = [r for r in production.list_runs(session) if frm <= date.fromisoformat(r["run_date"]) <= to]
    invoices_open = [
        i
        for i in billing.invoice_list(session)
        if i["status"] == "POSTED"
        and i["dispatched"] != i["packets"]
        and frm <= date.fromisoformat(i["invoice_date"]) <= to
    ]
    money = collections.overview(session)
    mass = [m for m in production.mass_law_results(session) if m["organization_id"] == str(organization_id)]
    items = [
        (
            "orders_to_decide",
            "Orders waiting for a decision",
            len(sales.inbox(session, "to_decide")["orders"]),
            "/admin/orders",
        ),
        ("ready_to_invoice", "Approved orders not yet invoiced", len(sales.orders_to_bill(session)), "/admin/invoices"),
        ("invoices_to_dispatch", "Invoices of the month not fully dispatched", len(invoices_open), "/admin/invoices"),
        (
            "provisional_costs",
            "Completed batches whose run costs are not final",
            sum(1 for r in runs if r["status"] == "COMPLETED" and r["cost_status"] != "FINAL"),
            "/leaks",
        ),
        (
            "open_batches",
            "Batches started but not completed",
            sum(1 for r in runs if r["status"] == "IN_PROGRESS"),
            "/leaks",
        ),
        (
            "mass_gaps",
            "Batches with a mass gap above tolerance (shown, not hidden)",
            sum(1 for m in mass if m["flagged"]),
            "/auditor/reports",
        ),
        (
            "advances",
            "Customers holding an unallocated advance",
            sum(1 for c in money["customers"] if Decimal(c["advance"]) > 0),
            "/admin/collections",
        ),
        (
            "overdue",
            "Customers with overdue invoices",
            sum(1 for c in money["customers"] if Decimal(c["overdue"]) > 0),
            "/admin/collections",
        ),
    ]
    checks = integrity_checks(session, organization_id)
    locks = [lk for lk in ledger.period_locks(session) if lk["period"] == period.isoformat()]
    return {
        "organization": org_name(session),
        "month": period.isoformat(),
        "locked": ledger.is_locked(session, period),
        "checklist": [
            {"key": k, "label": label, "count": count, "ok": count == 0, "link": link}
            for k, label, count, link in items
        ],
        "integrity": checks,
        "can_close": all(c["ok"] for c in checks),
        "history": locks,
    }


def close_month(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, month: date, reason: str
) -> uuid.UUID:
    failing = [c["check"] for c in integrity_checks(session, organization_id) if not c["ok"]]
    if failing:
        raise ReportError(
            "integrity_failing", "the month cannot be closed while an integrity check fails", {"failing": failing}
        )
    return ledger.lock_period(session, organization_id=organization_id, actor_id=actor_id, month=month, reason=reason)


def reopen_month(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, month: date, reason: str
) -> None:
    ledger.reopen_period(session, organization_id=organization_id, actor_id=actor_id, month=month, reason=reason)
