"""One report shape and its renderers (MP11, ADR-0018, K1). Pure: no database.

A report is a header (title, organization, filters, generated-at, method notes), typed columns, rows of exact strings
(money and quantities never become floats), optional totals, and for each row the source document it drills down
to. The same report renders as JSON (the screen), CSV, XLSX and a printable HTML page (saved as PDF by the browser).
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Any, Final

KINDS: Final = ("text", "date", "money", "qty", "pct", "bool")


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = "text"


@dataclass
class Report:
    name: str
    title: str
    organization: str
    filters: dict[str, str]
    columns: list[Column]
    rows: list[dict[str, Any]]
    totals: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "organization": self.organization,
            "filters": self.filters,
            "generated_at": self.generated_at,
            "columns": [{"key": c.key, "label": c.label, "kind": c.kind} for c in self.columns],
            "rows": self.rows,
            "totals": self.totals,
            "notes": self.notes,
        }


def sum_column(rows: list[dict[str, Any]], key: str, where: Any = None) -> str:
    """Exact sum of a decimal-string column (rows failing `where` are skipped)."""
    total = sum(
        (Decimal(r[key]) for r in rows if r.get(key) not in (None, "") and (where is None or where(r))), Decimal(0)
    )
    return str(total)


def _header_lines(report: Report) -> list[list[str]]:
    lines = [[report.title], [report.organization], [f"Generated {report.generated_at}"]]
    if report.filters:
        lines.append(["Filters: " + "; ".join(f"{k} = {v}" for k, v in report.filters.items())])
    lines += [[f"Note: {n}"] for n in report.notes]
    return lines


def _cell(row: dict[str, Any], key: str) -> str:
    v = row.get(key)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def to_csv(report: Report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for line in _header_lines(report):
        w.writerow(line)
    w.writerow([])
    w.writerow([c.label for c in report.columns])
    for r in report.rows:
        w.writerow([_cell(r, c.key) for c in report.columns])
    if report.totals:
        w.writerow([report.totals.get(c.key, "Total" if i == 0 else "") for i, c in enumerate(report.columns)])
    return buf.getvalue()


def to_xlsx(report: Report) -> bytes:
    """Money and quantities are written as text-exact Decimals; Excel shows them as numbers with 2 or 3 places."""
    from openpyxl import Workbook  # type: ignore[import-untyped]
    from openpyxl.styles import Font  # type: ignore[import-untyped]

    wb = Workbook()
    ws = wb.active
    ws.title = report.name[:31]
    for line in _header_lines(report):
        ws.append(line)
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append([c.label for c in report.columns])
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)

    def value(c: Column, raw: str) -> Any:
        if raw != "" and c.kind in ("money", "qty", "pct"):
            return Decimal(raw)
        return raw

    for r in report.rows:
        ws.append([value(c, _cell(r, c.key)) for c in report.columns])
    if report.totals:
        ws.append(
            [
                value(c, report.totals[c.key]) if c.key in report.totals else ("Total" if i == 0 else "")
                for i, c in enumerate(report.columns)
            ]
        )
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
    for i, c in enumerate(report.columns, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(12, min(40, len(c.label) + 4))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_html(report: Report) -> str:
    head = "".join(
        f"<th class={'r' if c.kind in ('money', 'qty', 'pct') else ''}>{escape(c.label)}</th>" for c in report.columns
    )

    def tds(row: dict[str, Any]) -> str:
        return "".join(
            f"<td class={'r' if c.kind in ('money', 'qty', 'pct') else ''}>{escape(_cell(row, c.key))}</td>"
            for c in report.columns
        )

    body = "".join(f"<tr>{tds(r)}</tr>" for r in report.rows)
    total = ""
    if report.totals:
        cells = {c.key: report.totals.get(c.key, "") for c in report.columns}
        cells[report.columns[0].key] = cells[report.columns[0].key] or "Total"
        total = f"<tfoot><tr>{tds(cells)}</tr></tfoot>"
    notes = "".join(f"<p class=note>{escape(n)}</p>" for n in report.notes)
    filters = "; ".join(f"{escape(k)} = {escape(v)}" for k, v in report.filters.items())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(report.title)}</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 24px; font-size: 12px; color: #1f1c17; }}
 h1 {{ font-size: 18px; margin: 0 0 4px; }} .meta {{ color: #5f584c; margin: 0 0 8px; }}
 table {{ border-collapse: collapse; width: 100%; }} th, td {{ border-bottom: 1px solid #e3ddd1; padding: 4px 6px; }}
 th {{ text-align: left; background: #f3efe7; }} .r {{ text-align: right; font-variant-numeric: tabular-nums; }}
 tfoot td {{ font-weight: 700; border-top: 2px solid #1f1c17; }} .note {{ color: #5f584c; font-size: 11px; }}
 @media print {{ .noprint {{ display: none; }} body {{ margin: 0; }} }}
</style></head><body>
<p class=noprint><button onclick="window.print()">Print or save as PDF</button></p>
<h1>{escape(report.title)}</h1>
<p class=meta>{escape(report.organization)} · generated {escape(report.generated_at)}
{' · ' + filters if filters else ''}</p>
{notes}
<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody>{total}</table>
<p class=note>DEMO data. Every figure comes from posted records in AaharOS.</p>
</body></html>"""
