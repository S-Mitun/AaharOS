"""Recipe and pack-spec use cases (MP06, ADR-0003, ADR-0013). Other modules call only this file.

Functions run in the caller's transaction and never commit (the API route commits once).
- recipes and pack specs, each with versions DRAFT -> ACTIVE -> RETIRED
- `activate_*` retires the version that was ACTIVE and activates this one, with an audit row
- `recipe_snapshot` / `pack_snapshot` return the JSON copy a production run freezes when it starts
"""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.recipe import domain
from app.modules.recipe.domain import PackLineIn, RecipeError, RecipeLineIn, SnapshotLine
from app.modules.recipe.models import PackSpec, PackSpecLine, PackSpecVersion, Recipe, RecipeLine, RecipeVersion
from app.modules.uom.domain import normalise


def _db_error(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


def _kind_of(session: Session, item_id: uuid.UUID) -> str:
    kinds = catalog.kinds_for(session, [item_id])
    if item_id not in kinds:
        raise NotFoundError("item_not_found", "unknown item", {"item_id": str(item_id)})
    return kinds[item_id]


# ---------- recipes ----------


def create_recipe(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    code: str,
    name: str,
    bulk_item_id: uuid.UUID,
) -> uuid.UUID:
    if _kind_of(session, bulk_item_id) != "BULK":
        raise RecipeError("not_bulk", "a recipe makes a BULK item (unpacked product)")
    if catalog.units_for(session, [bulk_item_id])[bulk_item_id].base_uom != "g":
        raise RecipeError("bulk_not_mass", "bulk is weighed: its base unit must be grams")
    recipe_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                insert(Recipe).values(
                    id=recipe_id,
                    organization_id=organization_id,
                    code=code,
                    name=name,
                    bulk_item_id=bulk_item_id,
                    created_by=actor_id,
                )
            )
    except DBAPIError as exc:
        err = _db_error(exc)
        if err.code == "duplicate":
            raise RecipeError("recipe_code_taken", f"a recipe with code {code!r} already exists") from exc
        raise err from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="recipe.create",
        entity_type="recipe",
        entity_id=recipe_id,
        after={"code": code, "name": name, "bulk_item_id": bulk_item_id},
    )
    return recipe_id


def create_recipe_version(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    recipe_id: uuid.UUID,
    bulk_yield_g: Decimal,
    effective_from: date,
    lines: Sequence[RecipeLineIn],
) -> uuid.UUID:
    """A new DRAFT version (next version number) with its ingredient lines in base units."""
    if session.execute(select(Recipe.id).where(Recipe.id == recipe_id)).scalar_one_or_none() is None:
        raise NotFoundError("recipe_not_found", "unknown recipe")
    item_ids = [ln.item_id for ln in lines]
    units = catalog.units_for(session, item_ids)
    kinds = catalog.kinds_for(session, item_ids)
    plan = domain.plan_recipe_lines(lines, {i: (units[i], kinds[i]) for i in units if i in kinds})
    bulk = domain.check_bulk_yield(bulk_yield_g)
    version_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(select(Recipe.id).where(Recipe.id == recipe_id).with_for_update())  # serialise numbering
            number = session.execute(
                select(func.coalesce(func.max(RecipeVersion.version), 0) + 1).where(
                    RecipeVersion.recipe_id == recipe_id
                )
            ).scalar_one()
            session.execute(
                insert(RecipeVersion).values(
                    id=version_id,
                    organization_id=organization_id,
                    recipe_id=recipe_id,
                    version=number,
                    status=domain.DRAFT,
                    bulk_yield_g=bulk,
                    effective_from=effective_from,
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(RecipeLine),
                [
                    {
                        "organization_id": organization_id,
                        "recipe_version_id": version_id,
                        "item_id": p.item_id,
                        "qty_base": p.qty_base,
                        "driver": domain.PER_BATCH,
                        "tolerance_pct": p.tolerance_pct,
                        "created_by": actor_id,
                    }
                    for p in plan
                ],
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="recipe.version.create",
                entity_type="recipe_version",
                entity_id=version_id,
                after={
                    "recipe_id": recipe_id,
                    "version": number,
                    "bulk_yield_g": bulk,
                    "lines": [
                        {"item_id": p.item_id, "qty_base": p.qty_base, "tolerance_pct": p.tolerance_pct} for p in plan
                    ],
                },
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return version_id


def activate_recipe_version(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, version_id: uuid.UUID
) -> uuid.UUID | None:
    """DRAFT -> ACTIVE; the version that was ACTIVE becomes RETIRED. Returns the retired version's id, if any."""
    version = session.execute(
        select(RecipeVersion).where(RecipeVersion.id == version_id).with_for_update()
    ).scalar_one_or_none()
    if version is None:
        raise NotFoundError("recipe_version_not_found", "unknown recipe version")
    session.execute(select(Recipe.id).where(Recipe.id == version.recipe_id).with_for_update())
    lines = session.execute(
        select(func.count()).select_from(RecipeLine).where(RecipeLine.recipe_version_id == version_id)
    ).scalar_one()
    domain.check_activation(version.status, lines)
    return _activate(session, organization_id, actor_id, RecipeVersion, RecipeVersion.recipe_id, version, "recipe")


def _activate(
    session: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    model: Any,
    parent_column: Any,
    version: Any,
    label: str,
) -> uuid.UUID | None:
    parent_id = getattr(version, parent_column.key)
    try:
        with session.begin_nested():
            retired = session.execute(
                update(model)
                .where(parent_column == parent_id, model.status == domain.ACTIVE)
                .values(status=domain.RETIRED)
                .returning(model.id)
            ).scalar_one_or_none()
            session.execute(update(model).where(model.id == version.id).values(status=domain.ACTIVE))
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action=f"{label}.version.activate",
                entity_type=f"{label}_version",
                entity_id=version.id,
                before={"status": domain.DRAFT, "active_version_id": retired},
                after={"status": domain.ACTIVE, "retired_version_id": retired},
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    session.expire(version)
    return retired


# ---------- pack specs ----------


def create_pack_spec(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    code: str,
    name: str,
    recipe_id: uuid.UUID,
    fg_item_id: uuid.UUID,
) -> uuid.UUID:
    if session.execute(select(Recipe.id).where(Recipe.id == recipe_id)).scalar_one_or_none() is None:
        raise NotFoundError("recipe_not_found", "unknown recipe")
    if _kind_of(session, fg_item_id) != "FG":
        raise RecipeError("not_finished_good", "a pack spec packs into a finished-goods (FG) item")
    pack_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                insert(PackSpec).values(
                    id=pack_id,
                    organization_id=organization_id,
                    code=code,
                    name=name,
                    recipe_id=recipe_id,
                    fg_item_id=fg_item_id,
                    created_by=actor_id,
                )
            )
    except DBAPIError as exc:
        err = _db_error(exc)
        if err.code == "duplicate":
            raise RecipeError("pack_spec_code_taken", f"a pack spec with code {code!r} already exists") from exc
        raise err from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="pack_spec.create",
        entity_type="pack_spec",
        entity_id=pack_id,
        after={"code": code, "name": name, "recipe_id": recipe_id, "fg_item_id": fg_item_id},
    )
    return pack_id


def create_pack_spec_version(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    pack_spec_id: uuid.UUID,
    net_g: Decimal,
    units_per_carton: int,
    shelf_life_days: int,
    effective_from: date,
    lines: Sequence[PackLineIn],
) -> uuid.UUID:
    if session.execute(select(PackSpec.id).where(PackSpec.id == pack_spec_id)).scalar_one_or_none() is None:
        raise NotFoundError("pack_spec_not_found", "unknown pack spec")
    domain.check_pack_header(net_g, units_per_carton, shelf_life_days)
    plan = domain.plan_pack_lines(lines, catalog.kinds_for(session, [ln.item_id for ln in lines]))
    version_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(select(PackSpec.id).where(PackSpec.id == pack_spec_id).with_for_update())
            number = session.execute(
                select(func.coalesce(func.max(PackSpecVersion.version), 0) + 1).where(
                    PackSpecVersion.pack_spec_id == pack_spec_id
                )
            ).scalar_one()
            session.execute(
                insert(PackSpecVersion).values(
                    id=version_id,
                    organization_id=organization_id,
                    pack_spec_id=pack_spec_id,
                    version=number,
                    status=domain.DRAFT,
                    net_g=net_g,
                    shelf_life_days=shelf_life_days,
                    units_per_carton=units_per_carton,
                    effective_from=effective_from,
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(PackSpecLine),
                [
                    {
                        "organization_id": organization_id,
                        "pack_spec_version_id": version_id,
                        "item_id": p.item_id,
                        "qty_per_good_unit": p.qty_per_good_unit,
                        "driver": domain.PER_GOOD_UNIT,
                        "tolerance_pct": p.tolerance_pct,
                        "created_by": actor_id,
                    }
                    for p in plan
                ],
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="pack_spec.version.create",
                entity_type="pack_spec_version",
                entity_id=version_id,
                after={
                    "pack_spec_id": pack_spec_id,
                    "version": number,
                    "net_g": net_g,
                    "units_per_carton": units_per_carton,
                    "shelf_life_days": shelf_life_days,
                    "lines": [
                        {
                            "item_id": p.item_id,
                            "qty_per_good_unit": p.qty_per_good_unit,
                            "tolerance_pct": p.tolerance_pct,
                        }
                        for p in plan
                    ],
                },
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return version_id


def activate_pack_spec_version(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, version_id: uuid.UUID
) -> uuid.UUID | None:
    version = session.execute(
        select(PackSpecVersion).where(PackSpecVersion.id == version_id).with_for_update()
    ).scalar_one_or_none()
    if version is None:
        raise NotFoundError("pack_spec_version_not_found", "unknown pack spec version")
    session.execute(select(PackSpec.id).where(PackSpec.id == version.pack_spec_id).with_for_update())
    lines = session.execute(
        select(func.count()).select_from(PackSpecLine).where(PackSpecLine.pack_spec_version_id == version_id)
    ).scalar_one()
    domain.check_activation(version.status, lines)
    return _activate(
        session, organization_id, actor_id, PackSpecVersion, PackSpecVersion.pack_spec_id, version, "pack_spec"
    )


# ---------- what a run needs ----------


def _snapshot_lines(
    session: Session, rows: Sequence[tuple[uuid.UUID, Decimal, str, Decimal | None]]
) -> list[SnapshotLine]:
    ids = [r[0] for r in rows]
    codes = catalog.codes_for(session, ids)
    units = catalog.units_for(session, ids)
    lines = [
        SnapshotLine(item, codes[item], units[item].base_uom, units[item].stock_uom, qty, driver, tol)
        for item, qty, driver, tol in rows
    ]
    return sorted(lines, key=lambda ln: ln.item_code)


def recipe_snapshot(session: Session, version_id: uuid.UUID) -> dict[str, Any]:
    """The frozen copy of an ACTIVE recipe version: header, bulk item, yield and every line in base units."""
    row = session.execute(
        select(RecipeVersion, Recipe)
        .join(Recipe, Recipe.id == RecipeVersion.recipe_id)
        .where(RecipeVersion.id == version_id)
    ).one_or_none()
    if row is None:
        raise NotFoundError("recipe_version_not_found", "unknown recipe version")
    version, recipe = row
    if version.status != domain.ACTIVE:
        raise RecipeError(
            "version_not_active", f"recipe {recipe.code} v{version.version} is {version.status}, not ACTIVE"
        )
    rows = session.execute(
        select(RecipeLine.item_id, RecipeLine.qty_base, RecipeLine.driver, RecipeLine.tolerance_pct).where(
            RecipeLine.recipe_version_id == version_id
        )
    ).tuples()
    return domain.recipe_snapshot(
        recipe_id=recipe.id,
        code=recipe.code,
        name=recipe.name,
        version_id=version.id,
        version=version.version,
        effective_from=version.effective_from,
        bulk_item_id=recipe.bulk_item_id,
        bulk_item_code=catalog.codes_for(session, [recipe.bulk_item_id])[recipe.bulk_item_id],
        bulk_yield_g=version.bulk_yield_g,
        lines=_snapshot_lines(session, list(rows)),
    )


def pack_snapshot(session: Session, version_id: uuid.UUID) -> dict[str, Any]:
    """The frozen copy of an ACTIVE pack spec version, with its recipe id so a run can check they belong together."""
    row = session.execute(
        select(PackSpecVersion, PackSpec)
        .join(PackSpec, PackSpec.id == PackSpecVersion.pack_spec_id)
        .where(PackSpecVersion.id == version_id)
    ).one_or_none()
    if row is None:
        raise NotFoundError("pack_spec_version_not_found", "unknown pack spec version")
    version, spec = row
    if version.status != domain.ACTIVE:
        raise RecipeError(
            "version_not_active", f"pack spec {spec.code} v{version.version} is {version.status}, not ACTIVE"
        )
    rows = session.execute(
        select(
            PackSpecLine.item_id, PackSpecLine.qty_per_good_unit, PackSpecLine.driver, PackSpecLine.tolerance_pct
        ).where(PackSpecLine.pack_spec_version_id == version_id)
    ).tuples()
    return domain.pack_snapshot(
        pack_spec_id=spec.id,
        code=spec.code,
        name=spec.name,
        version_id=version.id,
        version=version.version,
        effective_from=version.effective_from,
        recipe_id=spec.recipe_id,
        fg_item_id=spec.fg_item_id,
        fg_item_code=catalog.codes_for(session, [spec.fg_item_id])[spec.fg_item_id],
        fg_stock_uom=catalog.units_for(session, [spec.fg_item_id])[spec.fg_item_id].stock_uom,
        net_g=version.net_g,
        units_per_carton=version.units_per_carton,
        shelf_life_days=version.shelf_life_days,
        lines=_snapshot_lines(session, list(rows)),
    )


def version_status(
    session: Session, *, recipe_version_id: uuid.UUID | None = None, pack_spec_version_id: uuid.UUID | None = None
) -> str:
    if recipe_version_id is not None:
        status = session.execute(
            select(RecipeVersion.status).where(RecipeVersion.id == recipe_version_id)
        ).scalar_one_or_none()
    else:
        status = session.execute(
            select(PackSpecVersion.status).where(PackSpecVersion.id == pack_spec_version_id)
        ).scalar_one_or_none()
    if status is None:
        raise NotFoundError("version_not_found", "unknown recipe or pack spec version")
    return status


def active_recipe_snapshot(session: Session, recipe_id: uuid.UUID) -> dict[str, Any]:
    """The snapshot of a recipe's ACTIVE version (what a standard cost card is built from)."""
    found = session.execute(
        select(RecipeVersion.id).where(RecipeVersion.recipe_id == recipe_id, RecipeVersion.status == domain.ACTIVE)
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError("no_active_version", "this recipe has no ACTIVE version")
    return recipe_snapshot(session, found)


def active_recipe_version(session: Session, recipe_code: str) -> uuid.UUID:
    found = session.execute(
        select(RecipeVersion.id)
        .join(Recipe, Recipe.id == RecipeVersion.recipe_id)
        .where(Recipe.code == recipe_code, RecipeVersion.status == domain.ACTIVE)
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError("no_active_version", f"recipe {recipe_code!r} has no ACTIVE version")
    return found


def active_pack_spec_version(session: Session, pack_spec_code: str) -> uuid.UUID:
    found = session.execute(
        select(PackSpecVersion.id)
        .join(PackSpec, PackSpec.id == PackSpecVersion.pack_spec_id)
        .where(PackSpec.code == pack_spec_code, PackSpecVersion.status == domain.ACTIVE)
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError("no_active_version", f"pack spec {pack_spec_code!r} has no ACTIVE version")
    return found


def units_per_carton(session: Session, fg_item_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Packets per carton from each finished good's ACTIVE pack spec version (MP08, G2: the carton-aware stepper).
    A finished good with no ACTIVE pack spec is left out."""
    if not fg_item_ids:
        return {}
    rows = session.execute(
        select(PackSpec.fg_item_id, PackSpecVersion.units_per_carton)
        .join(PackSpecVersion, PackSpecVersion.pack_spec_id == PackSpec.id)
        .where(PackSpec.fg_item_id.in_(set(fg_item_ids)), PackSpecVersion.status == domain.ACTIVE)
        .order_by(PackSpec.code)
    ).tuples()
    out: dict[uuid.UUID, int] = {}
    for item_id, per_carton in rows:
        out.setdefault(item_id, per_carton)
    return out


def active_pack_net_g(session: Session, fg_item_id: uuid.UUID) -> Decimal:
    """Net grams of a finished good's ACTIVE pack spec (MP13: the passport of an opening-stock lot)."""
    found = session.execute(
        select(PackSpecVersion.net_g)
        .join(PackSpec, PackSpec.id == PackSpecVersion.pack_spec_id)
        .where(PackSpec.fg_item_id == fg_item_id, PackSpecVersion.status == domain.ACTIVE)
        .order_by(PackSpec.code)
        .limit(1)
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError("no_active_version", "this finished good has no ACTIVE pack spec")
    return Decimal(found)


def pack_spec_versions_for(session: Session, fg_item_id: uuid.UUID) -> list[uuid.UUID]:
    """Every pack spec version (any status) that packs this finished good (MP09: which runs will make it)."""
    return list(
        session.execute(
            select(PackSpecVersion.id)
            .join(PackSpec, PackSpec.id == PackSpecVersion.pack_spec_id)
            .where(PackSpec.fg_item_id == fg_item_id)
        ).scalars()
    )


# ---------- read models ----------


def _qty(d: Decimal | None) -> str | None:
    return None if d is None else str(normalise(d))


def list_recipes(session: Session) -> list[dict[str, Any]]:
    recipes = list(session.execute(select(Recipe).order_by(Recipe.code)).scalars())
    versions = list(session.execute(select(RecipeVersion).order_by(RecipeVersion.version)).scalars())
    lines = list(session.execute(select(RecipeLine)).scalars())
    codes = catalog.codes_for(session, {r.bulk_item_id for r in recipes} | {ln.item_id for ln in lines})
    out = []
    for r in recipes:
        out.append(
            {
                "id": str(r.id),
                "code": r.code,
                "name": r.name,
                "bulk_item_code": codes[r.bulk_item_id],
                "versions": [
                    {
                        "id": str(v.id),
                        "version": v.version,
                        "status": v.status,
                        "bulk_yield_g": _qty(v.bulk_yield_g),
                        "effective_from": v.effective_from.isoformat(),
                        "lines": [
                            {
                                "item_id": str(ln.item_id),
                                "item_code": codes[ln.item_id],
                                "qty_base": _qty(ln.qty_base),
                                "driver": ln.driver,
                                "tolerance_pct": _qty(ln.tolerance_pct),
                            }
                            for ln in sorted(lines, key=lambda x: codes[x.item_id])
                            if ln.recipe_version_id == v.id
                        ],
                    }
                    for v in versions
                    if v.recipe_id == r.id
                ],
            }
        )
    return out


def list_pack_specs(session: Session) -> list[dict[str, Any]]:
    specs = list(session.execute(select(PackSpec).order_by(PackSpec.code)).scalars())
    versions = list(session.execute(select(PackSpecVersion).order_by(PackSpecVersion.version)).scalars())
    lines = list(session.execute(select(PackSpecLine)).scalars())
    codes = catalog.codes_for(session, {s.fg_item_id for s in specs} | {ln.item_id for ln in lines})
    return [
        {
            "id": str(s.id),
            "code": s.code,
            "name": s.name,
            "recipe_id": str(s.recipe_id),
            "fg_item_code": codes[s.fg_item_id],
            "versions": [
                {
                    "id": str(v.id),
                    "version": v.version,
                    "status": v.status,
                    "net_g": _qty(v.net_g),
                    "units_per_carton": v.units_per_carton,
                    "shelf_life_days": v.shelf_life_days,
                    "effective_from": v.effective_from.isoformat(),
                    "lines": [
                        {
                            "item_id": str(ln.item_id),
                            "item_code": codes[ln.item_id],
                            "qty_per_good_unit": _qty(ln.qty_per_good_unit),
                            "driver": ln.driver,
                            "tolerance_pct": _qty(ln.tolerance_pct),
                        }
                        for ln in sorted(lines, key=lambda x: codes[x.item_id])
                        if ln.pack_spec_version_id == v.id
                    ],
                }
                for v in versions
                if v.pack_spec_id == s.id
            ],
        }
        for s in specs
    ]
