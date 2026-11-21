"""Report routes (MP11): the catalogue, and each report as JSON (the screen), CSV, XLSX or a printable page.
Read-only, `report.read` (admin, production, owner, auditor)."""

import json
import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.reports import close, domain, exports, gst, service
from app.modules.reports.domain import Report

router = APIRouter(prefix="/api/reports", tags=["reports"])
DbSession = Annotated[Session, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("report.read"))]
Format = Literal["json", "csv", "xlsx", "html"]

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render(report: Report, fmt: Format) -> Any:
    start = report.filters.get("from", report.filters.get("as_of", ""))
    stem = f"{report.name}_{start}_{report.filters.get('to', '')}".rstrip("_")
    if fmt == "csv":
        return Response(
            domain.to_csv(report),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
        )
    if fmt == "xlsx":
        return Response(
            domain.to_xlsx(report),
            media_type=XLSX_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
        )
    if fmt == "html":
        return HTMLResponse(domain.to_html(report))
    return report.to_json()


@router.get("")
def catalogue(_principal: Reader) -> dict[str, Any]:
    return {"reports": service.catalogue()}


@router.get("/stock-ledger")
def stock_ledger(
    _principal: Reader,
    session: DbSession,
    item_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    format: Format = "json",
) -> Any:
    return render(service.stock_ledger(session, item_id, date_from, date_to), format)


@router.get("/receivables-ageing")
def ageing(_principal: Reader, session: DbSession, as_of: date | None = None, format: Format = "json") -> Any:
    return render(service.receivables_ageing(session, as_of), format)


@router.get("/sales-register")
def sales_register(
    _principal: Reader,
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    format: Format = "json",
) -> Any:
    return render(service.sales_register(session, date_from, date_to, customer_id, item_id), format)


class CloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: date
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


@router.get("/close")
def close_cockpit(principal: Reader, session: DbSession, month: date | None = None) -> dict[str, Any]:
    return close.cockpit(session, principal.organization_id, month)


@router.post("/close/lock")
def close_month(
    body: CloseBody, principal: Annotated[Principal, Depends(require("period.lock"))], session: DbSession
) -> dict[str, Any]:
    close.close_month(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        month=body.month,
        reason=body.reason,
    )
    session.commit()
    return close.cockpit(session, principal.organization_id, body.month)


@router.post("/close/reopen")
def reopen_month(
    body: CloseBody, principal: Annotated[Principal, Depends(require("period.reopen"))], session: DbSession
) -> dict[str, Any]:
    close.reopen_month(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        month=body.month,
        reason=body.reason,
    )
    session.commit()
    return close.cockpit(session, principal.organization_id, body.month)


@router.get("/bank-statement")
def bank_statement(_principal: Reader, session: DbSession, as_of: date | None = None, format: Format = "json") -> Any:
    return render(exports.bank_statement(session, as_of), format)


@router.get("/tally-xml")
def tally(_principal: Reader, session: DbSession, date_from: date, date_to: date) -> Response:
    return Response(
        exports.tally_xml(session, date_from, date_to),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="tally_sales_{date_from}_{date_to}_DEMO.xml"'},
    )


@router.get("/evidence-pack")
def evidence(principal: Reader, session: DbSession, date_from: date, date_to: date) -> Response:
    return Response(
        exports.evidence_pack(session, principal.organization_id, date_from, date_to),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="evidence_pack_{date_from}_{date_to}_DEMO.zip"'},
    )


@router.get("/gst-summary")
def gst_summary(_principal: Reader, session: DbSession, month: date | None = None, format: Format = "json") -> Any:
    return render(gst.gst_summary(session, month), format)


@router.get("/gstr1-export")
def gstr1_export(_principal: Reader, session: DbSession, month: date) -> Any:
    """The month's GSTR-1-shaped JSON, for review only (never filed, never sent)."""
    body = gst.gstr1_export(session, month)
    return Response(
        json.dumps(body, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="GSTR1_{body["fp"]}_DEMO.json"'},
    )


@router.get("/{name}")
def report(
    name: Annotated[str, Query(pattern=r"^[a-z-]{3,40}$")] | str,
    _principal: Reader,
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    format: Format = "json",
) -> Any:
    fn = service.REPORTS.get(name)
    if fn is None or name in ("sales-register", "receivables-ageing"):
        raise service.ReportError("unknown_report", f"no report called {name!r}")
    return render(fn(session, date_from, date_to), format)
