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
from app.modules.reports import gst
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


# ---------- module 2: GST summary, export, law 4 ----------


def test_gst_summary_and_export_for_nit(nit: Any, app_engine: Engine) -> None:
    with scoped(app_engine, nit) as s:
        summary = gst.gst_summary(s, DAY)
        export = gst.gstr1_export(s, DAY)
        assert gst.law4(s) == []
    rows = {(r["table"], r["description"][:3]): r for r in summary.rows}
    b2b = rows[("4A", "B2B")]
    assert (b2b["documents"], b2b["taxable"], b2b["cgst"], b2b["sgst"], b2b["igst"]) == (
        "1",
        "7500.00",
        "187.50",
        "187.50",
        "0.00",
    )
    gstr3b = next(r for r in summary.rows if r["table"] == "3B 3.1(a)")
    assert (gstr3b["taxable"], gstr3b["total"]) == ("7500.00", "7875.00")
    assert export["_notice"].startswith("DEMO GSTR-1") and export["fp"] == "112026"
    (party,) = export["b2b"]
    assert party["ctin"] == "33DEMOA0000A1Z0" and party["inv"][0]["val"] == "7875.00"
    assert party["inv"][0]["itms"][0]["itm_det"]["camt"] == "187.50"
    assert export["hsn"]["data"][0]["hsn_sc"] == "21069099"


def test_export_totals_catch_a_changed_file() -> None:
    det = {"rt": "5", "txval": "7500.00", "iamt": "0.00", "camt": "187.50", "samt": "187.50", "csamt": "0.00"}
    export: dict[str, Any] = {
        "b2b": [{"ctin": "X", "inv": [{"itms": [{"num": 1, "itm_det": det}]}]}],
        "b2cl": [],
        "b2cs": [],
        "cdnr": [
            {
                "ctin": "X",
                "nt": [{"itms": [{"num": 1, "itm_det": {**det, "txval": "300.00", "camt": "7.50", "samt": "7.50"}}]}],
            }
        ],
        "cdnur": [],
    }
    assert gst.export_totals(export) == {
        "taxable": D("7200.00"),
        "igst": D(0),
        "cgst": D("180.00"),
        "sgst": D("180.00"),
    }


def test_law4_holds_with_a_credit_note_and_a_cancelled_invoice(nit: Any, app_engine: Engine) -> None:
    """Runs last in this file: it adds documents to the NIT tenant."""
    import uuid as _uuid

    from app.modules.billing import service as billing
    from app.modules.billing.domain import CreditLineIn
    from app.modules.reports import gst
    from app.modules.sales import service as sales

    with scoped(app_engine, nit) as s:
        org = nit.organization_id
        billing.post_credit_note(
            s,
            organization_id=org,
            actor_id=None,
            invoice_id=nit.invoice_a_id,
            reason="DEMO: festival discount",
            lines=[CreditLineIn(1, 150, D("2.00"))],
            note_date=DAY,
        )
        b = nit.order_ids["6_order_B"]
        sales.approve_order(s, organization_id=org, actor_id=None, order_id=b, partial=True)  # 88 held
        inv_b = billing.create_invoice(s, organization_id=org, actor_id=None, order_id=b, invoice_date=DAY)
        billing.cancel_invoice(s, organization_id=org, actor_id=None, invoice_id=inv_b.invoice_id, reason="DEMO: wrong")
        s.commit()
        assert gst.law4(s) == []
        summary = gst.gst_summary(s, DAY)
        export = gst.gstr1_export(s, DAY)
    cdnr = next(r for r in summary.rows if "(CDNR)" in r["description"])
    assert (cdnr["documents"], cdnr["taxable"], cdnr["cgst"]) == ("1", "-300.00", "-7.50")
    gstr3b = next(r for r in summary.rows if r["table"] == "3B 3.1(a)")
    assert (gstr3b["taxable"], gstr3b["cgst"], gstr3b["igst"]) == ("7200.00", "180.00", "0.00")  # B's IGST cancelled
    table13 = next(r for r in summary.rows if r["table"] == "13" and r["description"].startswith("Invoices"))
    assert table13["documents"] == "1" and "(1 cancelled)" in table13["description"]
    assert export["cdnr"][0]["nt"][0]["itms"][0]["itm_det"]["txval"] == "300.00"
    assert _uuid.UUID(str(nit.invoice_a_id))


# ---------- module 5: bank statement, Tally XML, evidence pack, row 26 ----------


def test_bank_statement_drawing_power(nit: Any, app_engine: Engine) -> None:
    from app.modules.reports import exports

    with scoped(app_engine, nit) as s:
        r = exports.bank_statement(s, DAY)
        owed = D(reports.receivables_ageing(s, DAY).totals["outstanding"])  # 3,875 less any credit note above
    rows = {row["what"]: row for row in r.rows}
    assert rows["Raw materials"]["value"] == "8665.00"  # flour 5,175 + oil 2,730 + spice 760
    assert rows["Packaging"]["value"] == "1080.00"  # pouches 765 + cartons 315
    assert rows["Finished goods"]["value"] == "2740.64"
    debts = (owed * D("0.60")).quantize(D("0.01"))
    assert rows["Book debts up to 90 days"]["eligible"] == str(debts)  # 60% of book debts up to 90 days
    assert D(r.totals["eligible"]) == D("9364.23") + debts  # stock 12,485.64 x 75% + debts


def test_tally_xml_and_evidence_pack(nit: Any, api_app: Any) -> None:
    import zipfile
    from xml.etree import ElementTree

    client = login_client(api_app, nit.auditor)
    xml = client.get("/api/reports/tally-xml?date_from=2026-11-01&date_to=2026-11-30")
    assert xml.status_code == 200
    root = ElementTree.fromstring(xml.content)  # noqa: S314 - our own generated file, not untrusted input
    (voucher,) = root.iter("VOUCHER")
    amounts = {e.findtext("LEDGERNAME"): e.findtext("AMOUNT") for e in voucher.iter("ALLLEDGERENTRIES.LIST")}
    assert amounts["DEMO Retailer A"] == "-7875.00"  # the party is debited the total
    assert (amounts["CGST Output"], amounts["SGST Output"]) == ("187.50", "187.50")
    assert sum(D(a) for a in amounts.values()) == 0  # a balanced voucher

    pack = client.get("/api/reports/evidence-pack?date_from=2026-11-01&date_to=2026-11-30")
    assert pack.status_code == 200 and pack.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(pack.content))
    names = set(z.namelist())
    for expected in (
        "reports/sales_register.csv",
        "reports/gst_summary.csv",
        "ledger/stock_lines.csv",
        "audit/verification.json",
        "integrity.json",
        "assumptions.md",
        "tally/sales_vouchers_DEMO.xml",
    ):
        assert expected in names, expected
    import json

    audit_result = json.loads(z.read("audit/verification.json"))
    assert audit_result["ok"] is True and len(audit_result["chain_head"]["last_hash"]) == 64
    assert all(c["ok"] for c in json.loads(z.read("integrity.json")))
    assert "A3:" in z.read("assumptions.md").decode()


def test_the_nit_tenant_passes_every_integrity_check(nit: Any) -> None:
    assert len(nit.integrity) == 8
    assert [c["check"] for c in nit.integrity if not c["ok"]] == []
