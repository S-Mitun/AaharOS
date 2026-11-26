"""Planning routes (MP12): material runway and shortage attribution. Read-only (`report.read`)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.planning import service

router = APIRouter(prefix="/api/planning", tags=["planning"])
DbSession = Annotated[Session, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("report.read"))]


@router.get("/runway")
def runway(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return {"packs": service.runway(session)}


@router.get("/shortage/{order_id}")
def shortage(order_id: uuid.UUID, _principal: Reader, session: DbSession) -> dict[str, Any]:
    return service.shortage_attribution(session, order_id)


@router.get("/plan")
def plan(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return service.batch_plan(session)


class BatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_version_id: uuid.UUID
    pack_version_id: uuid.UUID
    batches: Annotated[int, Field(ge=1, le=20)]
    run_date: date | None = None


@router.post("/batches", status_code=status.HTTP_201_CREATED)
def approve_batch(
    body: BatchBody, principal: Annotated[Principal, Depends(require("run.start"))], session: DbSession
) -> dict[str, Any]:
    run_id = service.approve_batch(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        recipe_version_id=body.recipe_version_id,
        pack_version_id=body.pack_version_id,
        batches=body.batches,
        run_date=body.run_date,
    )
    session.commit()
    return {"run_id": str(run_id), "status": "DRAFT"}


class DraftLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    qty_base: Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,6})?$")]
    needed_by: date
    reason: Annotated[str, StringConstraints(max_length=300)] | None = None


class DraftBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: uuid.UUID | None = None
    note: Annotated[str, StringConstraints(max_length=500)] | None = None
    lines: Annotated[list[DraftLineBody], Field(min_length=1, max_length=100)]


@router.post("/purchase-drafts", status_code=status.HTTP_201_CREATED)
def create_draft(
    body: DraftBody, principal: Annotated[Principal, Depends(require("receipt.post"))], session: DbSession
) -> dict[str, Any]:
    draft_id, draft_no = service.create_draft_po(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        supplier_id=body.supplier_id,
        note=body.note,
        lines=[service.DraftLineIn(ln.item_id, Decimal(ln.qty_base), ln.needed_by, ln.reason) for ln in body.lines],
    )
    session.commit()
    return {"id": str(draft_id), "draft_no": draft_no, "status": "DRAFT"}


@router.get("/purchase-drafts")
def drafts(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return {"drafts": service.draft_pos(session)}


class CancelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(min_length=1, max_length=300)]


@router.post("/purchase-drafts/{draft_id}/cancel")
def cancel_draft(
    draft_id: uuid.UUID,
    body: CancelBody,
    principal: Annotated[Principal, Depends(require("receipt.post"))],
    session: DbSession,
) -> dict[str, Any]:
    service.cancel_draft_po(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        draft_id=draft_id,
        reason=body.reason,
    )
    session.commit()
    return {"id": str(draft_id), "status": "CANCELLED"}


@router.get("/item-settings")
def item_settings(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return {"items": service.item_params_view(session)}


Base = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,6})?$")]


class ItemSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reorder_level_base: Base
    safety_stock_base: Base
    min_order_base: Base
    lead_time_days: Annotated[int, Field(ge=0, le=365)]


@router.put("/item-settings/{item_id}")
def put_item_settings(
    item_id: uuid.UUID,
    body: ItemSettingsBody,
    principal: Annotated[Principal, Depends(require("settings.manage"))],
    session: DbSession,
) -> dict[str, Any]:
    service.set_item_params(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        item_id=item_id,
        reorder_level_base=Decimal(body.reorder_level_base),
        safety_stock_base=Decimal(body.safety_stock_base),
        min_order_base=Decimal(body.min_order_base),
        lead_time_days=body.lead_time_days,
    )
    session.commit()
    return {"item_id": str(item_id), "saved": True}
