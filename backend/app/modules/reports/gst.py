"""GST summary, the GSTR-1-shaped export and law 4 (MP11, ADR-0018, K3). Read-only.

- The month's POSTED invoices and credit notes are sorted into GSTR-1 tables 4A (B2B), 5 (B2CL: unregistered,
  inter-state, above the `gst.b2cl_threshold` setting), 7 (B2CS), 9B (CDNR / CDNUR), 12 (HSN summary), 13 (documents
  issued) and GSTR-3B 3.1(a) (outward taxable supplies, net of credit notes).
- The export has the shape of the portal's offline-tool JSON, for review only: never filed, never sent.
- Law 4: Σ posted invoice tax lines - Σ credit-note tax lines (direct SQL) = the summary = the export read back.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.calendar import business_date
from app.modules.billing import service as billing
from app.modules.reports.domain import Column, Report
from app.modules.reports.service import ReportError, org_name
from app.modules.tax import service as tax

B2CL_THRESHOLD: Final = "gst.b2cl_threshold"
HEADS: Final = ("taxable", "igst", "cgst", "sgst")


def month_range(month: date) -> tuple[date, date]:
    first = month.replace(day=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, nxt - timedelta(days=1)


def _dec(row: dict[str, Any], key: str) -> Decimal:
    raw = row.get(key)
    return Decimal(str(raw)) if raw not in (None, "") else Decimal(0)


def heads(rows: list[dict[str, Any]]) -> dict[str, Decimal]:
    return {k: sum((_dec(r, k) for r in rows), Decimal(0)) for k in HEADS}


def sections(session: Session, month: date) -> dict[str, Any]:
    frm, to = month_range(month)
    rows = [r for r in billing.register_rows(session, frm, to) if r["status"] == "POSTED"]
    inv = [r for r in rows if r["doc_type"] == "INV"]
    threshold = Decimal(0)
    if any(not r["gstin"] and r["regime"] == "INTER" for r in inv):  # only then does table 5 vs 7 depend on it
        found = effective_settings.decimal_on(session, B2CL_THRESHOLD, to)
        if found is None:
            raise ReportError("b2cl_threshold_missing", "the B2CL threshold (gst.b2cl_threshold) is not configured")
        threshold = found
    notes = [r for r in rows if r["doc_type"] == "CN"]
    value: dict[str, Decimal] = {}
    for r in inv:
        value[r["doc_no"]] = value.get(r["doc_no"], Decimal(0)) + _dec(r, "total")
    b2b = [r for r in inv if r["gstin"]]
    b2cl = [r for r in inv if not r["gstin"] and r["regime"] == "INTER" and value[r["doc_no"]] > threshold]
    b2cs = [r for r in inv if not r["gstin"] and r not in b2cl]
    hsn: dict[tuple[str, str], dict[str, Decimal]] = {}
    for r in rows:
        acc = hsn.setdefault((r["hsn"], r["gst_rate"]), {k: Decimal(0) for k in ("qty", *HEADS)})
        for k in acc:
            acc[k] += _dec(r, k)
    return {
        "period": frm.strftime("%m%Y"),
        "from": frm,
        "to": to,
        "b2b": b2b,
        "b2cl": b2cl,
        "b2cs": b2cs,
        "cdnr": [r for r in notes if r["gstin"]],
        "cdnur": [r for r in notes if not r["gstin"]],
        "hsn": hsn,
        "docs": billing.documents_issued(session, frm, to),
        "gstr3b_31a": heads(rows),
    }


def _row(table: str, description: str, documents: str, h: dict[str, Decimal] | None) -> dict[str, Any]:
    if h is None:
        return {
            "table": table,
            "description": description,
            "documents": documents,
            **dict.fromkeys(HEADS, ""),
            "total": "",
        }
    return {
        "table": table,
        "description": description,
        "documents": documents,
        **{k: str(v) for k, v in h.items() if k in HEADS},
        "total": str(sum((h[k] for k in HEADS), Decimal(0))),
    }


def gst_summary(session: Session, month: date | None = None, _unused: date | None = None) -> Report:
    g = sections(session, month or business_date())
    out = []
    for table, label, part in (
        ("4A", "B2B: registered buyers", g["b2b"]),
        ("5", "B2CL: unregistered, inter-state, large", g["b2cl"]),
        ("7", "B2CS: unregistered, others", g["b2cs"]),
        ("9B", "Credit notes to registered buyers (CDNR)", g["cdnr"]),
        ("9B", "Credit notes to unregistered buyers (CDNUR)", g["cdnur"]),
    ):
        out.append(_row(table, label, str(len({r["doc_no"] for r in part})), heads(part)))
    for (code, rate), acc in sorted(g["hsn"].items()):
        out.append(_row("12", f"HSN {code} at {rate}% ({acc['qty'].normalize():f} units)", "", acc))
    for d in g["docs"]:
        label = f"{d['nature']}: {d['from'] or '-'} to {d['to'] or '-'} ({d['cancelled']} cancelled)"
        out.append(_row("13", label, d["net_issued"], None))
    out.append(_row("3B 3.1(a)", "Outward taxable supplies (net of credit notes)", "", g["gstr3b_31a"]))
    return Report(
        name="gst-summary",
        title=f"GST summary {g['from'].strftime('%B %Y')} (GSTR-1 and GSTR-3B 3.1)",
        organization=org_name(session),
        filters={"month": g["from"].strftime("%Y-%m")},
        columns=[
            Column("table", "Table"),
            Column("description", "What"),
            Column("documents", "Documents", "qty"),
            Column("taxable", "Taxable", "money"),
            Column("igst", "IGST", "money"),
            Column("cgst", "CGST", "money"),
            Column("sgst", "SGST", "money"),
            Column("total", "Total", "money"),
        ],
        rows=out,
        notes=[
            "Posted invoices and credit notes of the month; cancelled invoices appear in table 13 only.",
            "For review with your chartered accountant. Nothing is filed or sent to the GST portal.",
        ],
    )


def _items(rows: list[dict[str, Any]], sign: int = 1) -> list[dict[str, Any]]:
    def amt(r: dict[str, Any], k: str) -> str:
        return str(sign * _dec(r, k))

    return [
        {
            "num": n,
            "itm_det": {
                "rt": r["gst_rate"],
                "txval": amt(r, "taxable"),
                "iamt": amt(r, "igst"),
                "camt": amt(r, "cgst"),
                "samt": amt(r, "sgst"),
                "csamt": "0.00",
            },
        }
        for n, r in enumerate(rows, start=1)
    ]


def _by_doc(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    docs: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        docs.setdefault(r["doc_no"], []).append(r)
    return docs


def _ddmmyyyy(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d-%m-%Y")


def gstr1_export(session: Session, month: date) -> dict[str, Any]:
    """GSTR-1 in the shape of the portal's offline-tool JSON. For review only: never filed, never sent."""
    g = sections(session, month)
    gstin = tax.profile(session, g["to"]).get("gstin") or ""
    b2b: dict[str, list[dict[str, Any]]] = {}
    for no, lines in _by_doc(g["b2b"]).items():
        r = lines[0]
        b2b.setdefault(r["gstin"], []).append(
            {
                "inum": no,
                "idt": _ddmmyyyy(r["doc_date"]),
                "val": str(sum((_dec(x, "total") for x in lines), Decimal(0))),
                "pos": r["place_of_supply"],
                "rchrg": "N",
                "inv_typ": "R",
                "itms": _items(lines),
            }
        )
    cdnr: dict[str, list[dict[str, Any]]] = {}
    for no, lines in _by_doc(g["cdnr"]).items():
        r = lines[0]
        cdnr.setdefault(r["gstin"], []).append(
            {
                "nt_num": no,
                "nt_dt": _ddmmyyyy(r["doc_date"]),
                "ntty": "C",
                "val": str(-sum((_dec(x, "total") for x in lines), Decimal(0))),
                "pos": r["place_of_supply"],
                "itms": _items(lines, sign=-1),
            }
        )
    b2cs: dict[tuple[str, str, str], dict[str, Decimal]] = {}
    for r in g["b2cs"]:
        key = ("INTRA" if r["regime"] == "INTRA" else "INTER", r["place_of_supply"], r["gst_rate"])
        acc = b2cs.setdefault(key, {"txval": Decimal(0), "iamt": Decimal(0), "camt": Decimal(0), "samt": Decimal(0)})
        for src, dst in (("taxable", "txval"), ("igst", "iamt"), ("cgst", "camt"), ("sgst", "samt")):
            acc[dst] += _dec(r, src)
    b2cl = []
    for no, lines in _by_doc(g["b2cl"]).items():
        total = sum((_dec(x, "total") for x in lines), Decimal(0))
        b2cl.append(
            {"pos": lines[0]["place_of_supply"], "inv": [{"inum": no, "val": str(total), "itms": _items(lines)}]}
        )
    return {
        "_notice": "DEMO GSTR-1 shaped for review only: not filed, never sent to the GST portal",
        "gstin": gstin,
        "fp": g["period"],
        "b2b": [{"ctin": k, "inv": v} for k, v in sorted(b2b.items())],
        "b2cl": b2cl,
        "b2cs": [
            {"sply_ty": ty, "pos": pos, "rt": rt, **{k: str(v) for k, v in acc.items()}}
            for (ty, pos, rt), acc in sorted(b2cs.items())
        ],
        "cdnr": [{"ctin": k, "nt": v} for k, v in sorted(cdnr.items())],
        "cdnur": [
            {"nt_num": no, "nt_dt": _ddmmyyyy(lines[0]["doc_date"]), "ntty": "C", "itms": _items(lines, sign=-1)}
            for no, lines in _by_doc(g["cdnur"]).items()
        ],
        "hsn": {
            "data": [
                {
                    "num": n,
                    "hsn_sc": code,
                    "rt": rate,
                    "qty": str(acc["qty"]),
                    "txval": str(acc["taxable"]),
                    "iamt": str(acc["igst"]),
                    "camt": str(acc["cgst"]),
                    "samt": str(acc["sgst"]),
                }
                for n, ((code, rate), acc) in enumerate(sorted(g["hsn"].items()), start=1)
            ]
        },
        "doc_issue": {"doc_det": g["docs"]},
    }


def export_totals(export: dict[str, Any]) -> dict[str, Decimal]:
    """The tax heads read back out of an export: b2b + b2cl + b2cs - cdnr - cdnur."""
    total = {"txval": Decimal(0), "iamt": Decimal(0), "camt": Decimal(0), "samt": Decimal(0)}

    def add(det: dict[str, Any], sign: int) -> None:
        for k in total:
            total[k] += sign * Decimal(det[k])

    for party in export["b2b"]:
        for inv in party["inv"]:
            for it in inv["itms"]:
                add(it["itm_det"], 1)
    for block in export["b2cl"]:
        for inv in block["inv"]:
            for it in inv["itms"]:
                add(it["itm_det"], 1)
    for row in export["b2cs"]:
        add(row, 1)
    for party in export["cdnr"]:  # credit-note amounts are stored positive in the file and reduce the totals
        for nt in party["nt"]:
            for it in nt["itms"]:
                add(it["itm_det"], -1)
    for nt in export["cdnur"]:
        for it in nt["itms"]:
            add(it["itm_det"], -1)
    return {"taxable": total["txval"], "igst": total["iamt"], "cgst": total["camt"], "sgst": total["samt"]}


INVOICE_HEADS_SQL: Final = """
    SELECT coalesce(sum(t.amount) FILTER (WHERE t.tax = 'IGST'), 0),
           coalesce(sum(t.amount) FILTER (WHERE t.tax = 'CGST'), 0),
           coalesce(sum(t.amount) FILTER (WHERE t.tax = 'SGST'), 0)
      FROM invoice_tax_lines t JOIN invoice_lines l ON l.id = t.invoice_line_id
      JOIN invoices i ON i.id = l.invoice_id
     WHERE i.status = 'POSTED' AND i.invoice_date BETWEEN :f AND :t
"""
CREDIT_HEADS_SQL: Final = """
    SELECT coalesce(sum(t.amount) FILTER (WHERE t.tax = 'IGST'), 0),
           coalesce(sum(t.amount) FILTER (WHERE t.tax = 'CGST'), 0),
           coalesce(sum(t.amount) FILTER (WHERE t.tax = 'SGST'), 0)
      FROM credit_note_tax_lines t JOIN credit_note_lines l ON l.id = t.credit_note_line_id
      JOIN credit_notes n ON n.id = l.credit_note_id
     WHERE n.note_date BETWEEN :f AND :t
"""


def _sql_heads(session: Session, frm: date, to: date) -> dict[str, Decimal]:
    inv = session.execute(text(INVOICE_HEADS_SQL), {"f": frm, "t": to}).one()
    cn = session.execute(text(CREDIT_HEADS_SQL), {"f": frm, "t": to}).one()
    return {head: Decimal(inv[n]) - Decimal(cn[n]) for n, head in enumerate(("igst", "cgst", "sgst"))}


def law4(session: Session) -> list[dict[str, str]]:
    """Every month with documents: tax lines (SQL) = GST summary = export read back. Empty means the law holds.
    Runs in the caller's organization (row-level security)."""
    months = session.execute(
        text(
            "SELECT DISTINCT date_trunc('month', d)::date FROM"
            " (SELECT invoice_date AS d FROM invoices UNION SELECT note_date FROM credit_notes) x ORDER BY 1"
        )
    ).scalars()
    bad = []
    for m in months:
        frm, to = month_range(m)
        lines = _sql_heads(session, frm, to)
        summary = sections(session, m)["gstr3b_31a"]
        exported = export_totals(gstr1_export(session, m))
        for head in ("igst", "cgst", "sgst"):
            if not lines[head] == summary[head] == exported[head]:
                bad.append(
                    {
                        "month": frm.strftime("%Y-%m"),
                        "tax": head.upper(),
                        "tax_lines": str(lines[head]),
                        "gst_summary": str(summary[head]),
                        "export": str(exported[head]),
                    }
                )
    return bad
