"""Costing routes (MP07): run costing (run cost, cost per good unit, waterfall, sensitivity) and standard cost cards.

Reading needs `report.read`; creating a card needs `recipe.manage` (standards belong with the recipe owner). Rates and
amounts arrive as decimal strings, never JSON numbers.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.costing import service
from app.modules.identity.service import Principal, require

router = APIRouter(prefix="/api", tags=["costing"])
DbSession = Annotated[Session, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("report.read"))]
MoneyText = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,6})?$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class RateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    rate: MoneyText  # rupees per stock unit (per kg, per L, per piece)


class ConversionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Label
    amount: MoneyText  # rupees per batch


class CardBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_spec_version_id: uuid.UUID
    effective_from: date
    rates: Annotated[list[RateBody], Field(min_length=1, max_length=100)]
    conversion: Annotated[list[ConversionBody], Field(max_length=20)] = []


@router.get("/runs/{run_id}/costing")
def run_costing(run_id: uuid.UUID, _principal: Reader, session: DbSession) -> dict[str, Any]:
    return service.run_costing(session, run_id).to_json()


@router.get("/standard-cost-cards")
def list_cards(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return {"cards": service.list_cards(session)}


@router.post("/standard-cost-cards", status_code=status.HTTP_201_CREATED)
def create_card(
    body: CardBody, principal: Annotated[Principal, Depends(require("recipe.manage"))], session: DbSession
) -> dict[str, Any]:
    card_id = service.create_card(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        pack_spec_version_id=body.pack_spec_version_id,
        effective_from=body.effective_from,
        rates={r.item_id: Decimal(r.rate) for r in body.rates},
        conversion={c.label: Decimal(c.amount) for c in body.conversion},
    )
    session.commit()
    return next(c for c in service.list_cards(session) if c["id"] == str(card_id))
