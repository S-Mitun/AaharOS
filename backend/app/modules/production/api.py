"""Production-run routes (MP06).

- `POST /api/runs` and `POST /api/runs/{id}/start` need `run.start`; so do material issues and returns.
- `POST /api/runs/{id}/complete` needs `run.complete`.
- Reading a run (variances, packing, mass balance) needs `report.read`.
Issues and completion honour an `Idempotency-Key` header (a tablet on weak wi-fi): a duplicate submit returns the
first result (200 instead of 201) and posts nothing.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.production import service
from app.modules.production.schemas import CompleteBody, IssueBody, RunBody

router = APIRouter(prefix="/api", tags=["production"])
DbSession = Annotated[Session, Depends(get_session)]
IdempotencyKey = Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")]


@router.get("/runs")
def list_runs(_principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession) -> dict[str, Any]:
    return {"runs": service.list_runs(session)}


@router.get("/runs/{run_id}")
def get_run(
    run_id: uuid.UUID, _principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession
) -> dict[str, Any]:
    return service.get_run(session, run_id)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def create_run(
    body: RunBody, principal: Annotated[Principal, Depends(require("run.start"))], session: DbSession
) -> dict[str, Any]:
    run_id = service.create_run(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        recipe_version_id=body.recipe_version_id,
        batch_multiplier=Decimal(body.batch_multiplier),
        run_date=body.run_date,
        pack_lines=[
            service.PackLineRequest(
                p.pack_spec_version_id, None if p.bulk_allocated_g is None else Decimal(p.bulk_allocated_g)
            )
            for p in body.pack_lines
        ],
    )
    session.commit()
    return service.get_run(session, run_id)


@router.post("/runs/{run_id}/start")
def start_run(
    run_id: uuid.UUID, principal: Annotated[Principal, Depends(require("run.start"))], session: DbSession
) -> dict[str, Any]:
    service.start_run(session, organization_id=principal.organization_id, actor_id=principal.user_id, run_id=run_id)
    session.commit()
    return service.get_run(session, run_id)


@router.post("/runs/{run_id}/issues", status_code=status.HTTP_201_CREATED)
def issue_materials(
    run_id: uuid.UUID,
    body: IssueBody,
    response: Response,
    principal: Annotated[Principal, Depends(require("run.start"))],
    session: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    result = service.issue_materials(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        run_id=run_id,
        direction=body.direction,
        posting_date=body.posting_date,
        lines=[service.MaterialLineIn(ln.item_id, Decimal(ln.qty), ln.unit) for ln in body.lines],
        idempotency_key=idempotency_key,
    )
    session.commit()
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return {
        "replayed": result.replayed,
        "issue_id": str(result.issue_id),
        "issue_no": result.issue_no,
        "journal_id": str(result.journal_id),
        "run": service.get_run(session, run_id),
    }


@router.post("/runs/{run_id}/complete", status_code=status.HTTP_201_CREATED)
def complete_run(
    run_id: uuid.UUID,
    body: CompleteBody,
    response: Response,
    principal: Annotated[Principal, Depends(require("run.complete"))],
    session: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    scrap_g, loss_g = body.masses()
    oil = body.oil_session
    result = service.complete_run(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        run_id=run_id,
        results=[
            service.PackResultIn(
                pack_line_id=p.pack_line_id,
                good_units=int(p.good_units),
                packaging=[
                    service.PackagingIn(k.item_id, Decimal(k.used), Decimal(k.damaged), k.unit) for k in p.packaging
                ],
            )
            for p in body.pack_lines
        ],
        scrap_g=scrap_g,
        loss_g=loss_g,
        scrap_reason=body.scrap_reason,
        samples=[
            service.SampleIn(Decimal(s.gross_g), Decimal(s.net_g), s.sampled_at) for s in body.fill_weight_samples
        ],
        oil=None
        if oil is None
        else service.OilIn(
            Decimal(oil.fresh_ml),
            Decimal(oil.topup_ml),
            Decimal(oil.discard_ml),
            None if oil.tpc_pct is None else Decimal(oil.tpc_pct),
        ),
        posting_date=body.posting_date,
        idempotency_key=idempotency_key,
    )
    session.commit()
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return {"replayed": result.replayed, "journal_id": str(result.journal_id), **service.get_run(session, run_id)}
