"""Recipe and pack-spec routes (MP06): list, create, add a DRAFT version, activate.

Reading needs `report.read` (auditors read recipes too); every change needs `recipe.manage`.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.recipe import service
from app.modules.recipe.domain import PackLineIn, RecipeLineIn
from app.modules.recipe.schemas import PackSpecBody, PackSpecVersionBody, RecipeBody, RecipeVersionBody

router = APIRouter(prefix="/api", tags=["recipes"])
DbSession = Annotated[Session, Depends(get_session)]
Manager = Annotated[Principal, Depends(require("recipe.manage"))]
Reader = Annotated[Principal, Depends(require("report.read"))]


@router.get("/recipes")
def list_recipes(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return {"recipes": service.list_recipes(session)}


@router.post("/recipes", status_code=status.HTTP_201_CREATED)
def create_recipe(body: RecipeBody, principal: Manager, session: DbSession) -> dict[str, Any]:
    recipe_id = service.create_recipe(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        code=body.code,
        name=body.name,
        bulk_item_id=body.bulk_item_id,
    )
    session.commit()
    return {"id": str(recipe_id)}


@router.post("/recipes/{recipe_id}/versions", status_code=status.HTTP_201_CREATED)
def create_recipe_version(
    recipe_id: uuid.UUID, body: RecipeVersionBody, principal: Manager, session: DbSession
) -> dict[str, Any]:
    version_id = service.create_recipe_version(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        recipe_id=recipe_id,
        bulk_yield_g=Decimal(body.bulk_yield_g),
        effective_from=body.effective_from,
        lines=[RecipeLineIn(ln.item_id, Decimal(ln.qty), ln.unit, ln.tolerance()) for ln in body.lines],
    )
    session.commit()
    return {"id": str(version_id), "status": "DRAFT"}


@router.post("/recipes/versions/{version_id}/activate")
def activate_recipe_version(version_id: uuid.UUID, principal: Manager, session: DbSession) -> dict[str, Any]:
    retired = service.activate_recipe_version(
        session, organization_id=principal.organization_id, actor_id=principal.user_id, version_id=version_id
    )
    session.commit()
    return {"id": str(version_id), "status": "ACTIVE", "retired_version_id": None if retired is None else str(retired)}


@router.get("/pack-specs")
def list_pack_specs(_principal: Reader, session: DbSession) -> dict[str, Any]:
    return {"pack_specs": service.list_pack_specs(session)}


@router.post("/pack-specs", status_code=status.HTTP_201_CREATED)
def create_pack_spec(body: PackSpecBody, principal: Manager, session: DbSession) -> dict[str, Any]:
    pack_id = service.create_pack_spec(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        code=body.code,
        name=body.name,
        recipe_id=body.recipe_id,
        fg_item_id=body.fg_item_id,
    )
    session.commit()
    return {"id": str(pack_id)}


@router.post("/pack-specs/{pack_spec_id}/versions", status_code=status.HTTP_201_CREATED)
def create_pack_spec_version(
    pack_spec_id: uuid.UUID, body: PackSpecVersionBody, principal: Manager, session: DbSession
) -> dict[str, Any]:
    version_id = service.create_pack_spec_version(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        pack_spec_id=pack_spec_id,
        net_g=Decimal(body.net_g),
        units_per_carton=int(body.units_per_carton),
        shelf_life_days=int(body.shelf_life_days),
        effective_from=body.effective_from,
        lines=[PackLineIn(ln.item_id, Decimal(ln.qty_per_good_unit), ln.tolerance()) for ln in body.lines],
    )
    session.commit()
    return {"id": str(version_id), "status": "DRAFT"}


@router.post("/pack-specs/versions/{version_id}/activate")
def activate_pack_spec_version(version_id: uuid.UUID, principal: Manager, session: DbSession) -> dict[str, Any]:
    retired = service.activate_pack_spec_version(
        session, organization_id=principal.organization_id, actor_id=principal.user_id, version_id=version_id
    )
    session.commit()
    return {"id": str(version_id), "status": "ACTIVE", "retired_version_id": None if retired is None else str(retired)}
