"""Reports against PostgreSQL (MP11, ADR-0018, module 1): every total equals a direct SQL query over posted rows, on
the NIT replay; and each report downloads as CSV, XLSX and a printable page."""

import io
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.db import org_scope
from app.core.oracle import load_oracle
from app.modules.judge.replay import replay_stock
from app.modules.reports import service as reports
from tests.db.conftest import BACKEND, Tenant, add_member, login_client

D = Decimal
DAY = date(2026, 11, 21)


@pytest.fixture(scope="module")
def nit(app_engine: Engine, owner_engine: Engine) -> Any:
    oracle = load_oracle(BACKEND.parent / "benchmark" / "expected_results.yaml")
    with Session(app_engine, expire_on_commit=False) as s:
        replay = replay_stock(s, oracle)
    t = Tenant(org=replay.organization_id, items=replay.item_ids, locations={}, customer=replay.item_ids["flour"])
    replay.auditor = add_member(owner_engine, t, "AUDITOR")[1]
    return replay


def scoped(app_engine: Engine, nit: Any) -> Session:
    s = Session(app_engine)
    org_scope(s, nit.organization_id)
    return s


def test_sales_register_equals_posted_invoice_lines(nit: Any, app_engine: Engine) -> None:
    with scoped(app_engine, nit) as s:
        r = reports.sales_register(s, DAY, DAY)
        direct = s.execute(
            text(
                "SELECT (SELECT sum(il.taxable) FROM invoice_lines il JOIN invoices i ON i.id = il.invoice_id"
                "        WHERE i.status = 'POSTED'),"
                " sum(tl.amount) FILTER (WHERE tl.tax = 'CGST'), sum(tl.amount) FILTER (WHERE tl.tax = 'SGST')"
                " FROM invoice_tax_lines tl JOIN invoice_lines il ON il.id = tl.invoice_line_id"
                " JOIN invoices i ON i.id = il.invoice_id WHERE i.status = 'POSTED'"
            )
        ).one()
    assert (D(r.totals["taxable"]), D(r.totals["cgst"]), D(r.totals["sgst"])) == tuple(direct)
    assert (r.totals["taxable"], r.totals["total"]) == ("7500.00", "7875.00")
    assert r.rows[0]["_source"]["type"] == "invoice"


def test_stock_summary_closes_on_the_balance_projection(nit: Any, app_engine: Engine) -> None:
    with scoped(app_engine, nit) as s:
        r = reports.stock_summary(s, date(2026, 11, 1), DAY)
        projection = dict(
            s.execute(
                text(
                    "SELECT i.code || '@' || l.code, sum(b.value) FROM inventory_balances b"
                    " JOIN items i ON i.id = b.item_id JOIN locations l ON l.id = b.location_id"
                    " WHERE l.kind = 'STORE' GROUP BY 1"
                )
            )
            .tuples()
            .all()
        )
    for row in r.rows:
        opening, inv, out, adj = (D(row[k]) for k in ("opening_value", "in_value", "out_value", "value_adjustments"))
        assert opening + inv - out + adj == D(row["closing_value"])
        assert D(row["closing_value"]) == projection.get(f"{row['item_code']}@{row['store']}", D(0))
    fg = next(row for row in r.rows if row["item_code"] == "murukku_200g")
    assert (fg["closing_qty"], fg["closing_value"]) == ("88", "2740.64")
    assert D(fg["value_adjustments"]) == D("842.55")  # J8's share for the 88 on hand


def test_production_report_matches_the_benchmark(nit: Any, app_engine: Engine) -> None:
    with scoped(app_engine, nit) as s:
        (row,) = reports.production_report(s, DAY, DAY).rows
    assert (row["run_no"], row["good_packets"], row["run_cost"]) == ("B-001", "188", "5855.00")
    assert (row["yield_variance_pct"], row["variance_vs_standard"]) == ("-6.00", "431.20")
    assert row["cost_per_packet"].startswith("31.14")


def test_ageing_and_purchase_register(nit: Any, app_engine: Engine) -> None:
    with scoped(app_engine, nit) as s:
        ageing = reports.receivables_ageing(s, DAY)
        purchases = reports.purchase_register(s, DAY, DAY)
    (row,) = ageing.rows
    assert (row["customer"], row["outstanding"], row["0-15"], row["beyond_msme_45_days"]) == (
        "DEMO Retailer A",
        "3875.00",
        "3875.00",
        False,
    )
    assert reports.receivables_ageing.__name__ and ageing.totals["outstanding"] == "3875.00"
    assert purchases.totals["value"] == "2700.00"
    with scoped(app_engine, nit) as s:
        later = reports.receivables_ageing(s, date(2027, 1, 20))  # 60 days on
    assert later.rows[0]["46-90"] == "3875.00" and later.rows[0]["beyond_msme_45_days"] is True


def test_formats_through_the_api(nit: Any, api_app: Any) -> None:
    client = login_client(api_app, nit.auditor)
    base = "/api/reports/sales-register?date_from=2026-11-21&date_to=2026-11-21"
    assert client.get(base).json()["totals"]["total"] == "7875.00"
    csv = client.get(base + "&format=csv")
    assert csv.headers["content-type"].startswith("text/csv") and "7875.00" in csv.text
    assert csv.text.splitlines()[0] == "Sales register"
    xlsx = client.get(base + "&format=xlsx")
    sheet = load_workbook(io.BytesIO(xlsx.content)).active
    assert any(c.value == D("7875.00") for row in sheet.iter_rows() for c in row)
    html = client.get(base + "&format=html")
    assert "Print or save as PDF" in html.text and "Sales register" in html.text
    assert client.get("/api/reports/stock-summary?date_from=2026-11-01&date_to=2026-11-21").status_code == 200
    assert client.get("/api/reports/nonsense").status_code == 422
    assert client.get("/api/reports").json()["reports"][0]["name"] == "sales-register"
