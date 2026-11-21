"""Evidence Pack, Tally XML and the bank statement (MP11, ADR-0018, K6-K8). Read-only.

- Evidence Pack: one ZIP with every report as CSV, the GSTR-1 export, every stock line, the audit-chain verification
  and its current head hash (the anchor MP03 asked for), the assumptions and the latest benchmark scoreboard.
- Tally XML: a standard import envelope with one sales voucher per posted invoice. A DEMO file: nothing connects
  to Tally.
- Bank stock and book-debts statement: drawing power = stock at book value x (1 - stock margin) + book debts up to
  90 days x (1 - debtors margin); the margins are effective-dated settings.
"""

import csv
import io
import json
import uuid
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.calendar import business_date
from app.core.config import get_settings
from app.core.money import round_money
from app.core.oracle import load_oracle
from app.modules.audit import service as audit
from app.modules.billing import service as billing
from app.modules.catalog import service as catalog
from app.modules.ledger import service as ledger
from app.modules.reports import close, gst
from app.modules.reports import service as reports
from app.modules.reports.domain import Column, Report, sum_column, to_csv
from app.modules.reports.service import ReportError, org_name

STOCK_MARGIN: Final = "bank.stock_margin_pct"
DEBTORS_MARGIN: Final = "bank.debtors_margin_pct"


# ---------- bank stock and book-debts statement (K8) ----------


def bank_statement(session: Session, as_of: date | None = None, _unused: date | None = None) -> Report:
    on = as_of or business_date()
    stock_margin = effective_settings.decimal_on(session, STOCK_MARGIN, on)
    debt_margin = effective_settings.decimal_on(session, DEBTORS_MARGIN, on)
    if stock_margin is None or debt_margin is None:
        raise ReportError(
            "bank_margins_missing", "the bank margins (bank.stock_margin_pct, bank.debtors_margin_pct) are not set"
        )
    kinds = {}
    stock: dict[str, Decimal] = {}
    for row in ledger.balances(session):
        item = uuid.UUID(row["item_id"])
        if item not in kinds:
            kinds[item] = catalog.kinds_for(session, [item])[item]
        label = {"RAW": "Raw materials", "PACK": "Packaging", "BULK": "Work in progress", "FG": "Finished goods"}[
            kinds[item]
        ]
        if row["location"] == "WIP":
            label = "Work in progress"
        stock[label] = stock.get(label, Decimal(0)) + Decimal(row["value"])
    ageing = reports.receivables_ageing(session, on)
    eligible = sum((Decimal(r["outstanding"]) for r in ageing.rows if int(r["age_days"]) <= 90), Decimal(0))
    older = sum((Decimal(r["outstanding"]) for r in ageing.rows if int(r["age_days"]) > 90), Decimal(0))
    rows: list[dict[str, Any]] = []
    for label in ("Raw materials", "Packaging", "Work in progress", "Finished goods"):
        value = stock.get(label, Decimal("0.00"))
        rows.append(
            {
                "what": label,
                "value": str(value),
                "margin_pct": str(stock_margin),
                "eligible": str(round_money(value * (100 - stock_margin) / 100)),
            }
        )
    rows.append(
        {
            "what": "Book debts up to 90 days",
            "value": str(eligible),
            "margin_pct": str(debt_margin),
            "eligible": str(round_money(eligible * (100 - debt_margin) / 100)),
        }
    )
    rows.append(
        {"what": "Book debts over 90 days (not eligible)", "value": str(older), "margin_pct": "100", "eligible": "0.00"}
    )
    return Report(
        name="bank-statement",
        title="Stock and book-debts statement (drawing power)",
        organization=org_name(session),
        filters={"as_of": on.isoformat()},
        columns=[
            Column("what", "Security"),
            Column("value", "Book value", "money"),
            Column("margin_pct", "Margin %", "pct"),
            Column("eligible", "Drawing power", "money"),
        ],
        rows=rows,
        totals={"value": sum_column(rows, "value"), "eligible": sum_column(rows, "eligible")},
        notes=[
            "Stock at book value (weighted average for raw materials, actual batch cost for finished goods).",
            "Margins are DEMO settings; use the figures in your bank's sanction letter.",
        ],
    )


# ---------- Tally XML (K7) ----------


def _amount(value: Decimal) -> str:
    return f"{value:.2f}"


def tally_xml(session: Session, date_from: date, date_to: date) -> str:
    """One sales voucher per posted invoice: the party is debited the total; sales and each tax ledger credited."""
    vouchers = []
    for b in billing.invoices(session, status="POSTED"):
        if not date_from <= b.invoice_date <= date_to:
            continue
        view = billing.invoice_view(session, b.id)
        party = escape(view["customer"]["name"])
        rate = view["lines"][0]["taxes"][0]["rate_pct"] if view["lines"] and view["lines"][0]["taxes"] else ""
        entries = [
            (party, Decimal(view["total"]), True),
            (
                f"Sales GST {escape(str(rate))}%" if view["regime"] == "INTER" else "Sales GST (local)",
                Decimal(view["taxable"]),
                False,
            ),
            *((f"{head} Output", Decimal(amount), False) for head, amount in view["by_tax"].items()),
        ]
        if Decimal(view["round_off"]) != 0:
            entries.append(("Round Off", Decimal(view["round_off"]), False))
        ledger_xml = "".join(
            "<ALLLEDGERENTRIES.LIST>"
            f"<LEDGERNAME>{name}</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>{'Yes' if debit else 'No'}</ISDEEMEDPOSITIVE>"
            f"<AMOUNT>{_amount(-amount if debit else amount)}</AMOUNT>"
            "</ALLLEDGERENTRIES.LIST>"
            for name, amount, debit in entries
        )
        vouchers.append(
            '<TALLYMESSAGE xmlns:UDF="TallyUDF"><VOUCHER VCHTYPE="Sales" ACTION="Create">'
            f"<DATE>{b.invoice_date.strftime('%Y%m%d')}</DATE>"
            f"<VOUCHERNUMBER>{escape(b.invoice_no)}</VOUCHERNUMBER>"
            f"<PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>"
            f"<PARTYGSTIN>{escape(view['customer'].get('gstin') or '')}</PARTYGSTIN>"
            f"<PLACEOFSUPPLY>{escape(view['place_of_supply'])}</PLACEOFSUPPLY>"
            f"<NARRATION>DEMO invoice {escape(b.invoice_no)} from AaharOS</NARRATION>"
            f"{ledger_xml}</VOUCHER></TALLYMESSAGE>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- DEMO export from AaharOS: sales vouchers for import into Tally; nothing connects to Tally -->\n"
        "<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA>"
        "<REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC><REQUESTDATA>"
        + "".join(vouchers)
        + "</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>\n"
    )


# ---------- Evidence Pack (K6) ----------


def _csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns)
    for r in rows:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in columns])
    return buf.getvalue()


def evidence_pack(session: Session, organization_id: uuid.UUID, date_from: date, date_to: date) -> bytes:
    """Everything an auditor needs for the range, in one ZIP, generated from posted records."""
    month = date_from.replace(day=1)
    files: dict[str, str] = {
        "reports/sales_register.csv": to_csv(reports.sales_register(session, date_from, date_to)),
        "reports/purchase_register.csv": to_csv(reports.purchase_register(session, date_from, date_to)),
        "reports/stock_summary.csv": to_csv(reports.stock_summary(session, date_from, date_to)),
        "reports/production.csv": to_csv(reports.production_report(session, date_from, date_to)),
        "reports/receivables_ageing.csv": to_csv(reports.receivables_ageing(session, date_to)),
        "reports/gst_summary.csv": to_csv(gst.gst_summary(session, month)),
        f"gst/GSTR1_{month.strftime('%m%Y')}_DEMO.json": json.dumps(gst.gstr1_export(session, month), indent=2),
        "tally/sales_vouchers_DEMO.xml": tally_xml(session, date_from, date_to),
    }
    lines = ledger.stock_lines_export(session, date_from, date_to)
    files["ledger/stock_lines.csv"] = _csv(lines, list(lines[0]) if lines else ["posting_date"])
    verdict = audit.verify(session, organization_id)
    head = audit.chain_head(session, organization_id)
    files["audit/verification.json"] = json.dumps(
        {
            "organization_id": str(organization_id),
            "ok": verdict.ok,
            "rows_checked": verdict.rows_checked,
            "first_bad_seq": verdict.first_bad_seq,
            "reason": verdict.reason,
            "chain_head": head,
            "note": "Keep this head hash outside AaharOS: a later verification that ends on another hash means the "
            "audit trail was rewritten.",
        },
        indent=2,
    )
    files["integrity.json"] = json.dumps(close.integrity_checks(session, organization_id), indent=2)
    oracle = load_oracle(Path(get_settings().oracle_path))  # Decimal-only loader, never floats
    files["assumptions.md"] = "# Assumptions (from the benchmark oracle)\n\n" + "".join(
        f"- **{k}:** {v}\n" for k, v in (oracle.get("assumptions") or {}).items()
    )
    results = Path(get_settings().oracle_path).parent / "results" / "latest.json"
    if results.exists():
        files["benchmark/latest.json"] = results.read_text(encoding="utf-8")
    files["README.txt"] = (
        f"AaharOS Evidence Pack (DEMO)\n{org_name(session)}\nPeriod {date_from.isoformat()} to {date_to.isoformat()}\n"
        "Every file is generated from posted records. CSV money values are exact (no rounding beyond paise).\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in sorted(files.items()):
            z.writestr(name, content)
    return buf.getvalue()
