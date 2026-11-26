"""Planning use cases (MP12, ADR-0019). Read-only except the approve actions (module 2), which create DRAFTS only.

Module 1: material runway (L1) and shortage attribution (L2).
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Any, Final

from sqlalchemy import func, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.calendar import business_date, financial_year
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.explained import SourceRef
from app.core.money import round_money
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.ledger import service as ledger
from app.modules.planning import domain, planner
from app.modules.planning.domain import MaterialNeed, PlanningError, YieldLoss
from app.modules.planning.models import DraftPurchaseOrder, DraftPurchaseOrderLine, ItemPlanning
from app.modules.planning.planner import Demand, ItemParams, PackOption
from app.modules.production import service as production
from app.modules.recipe import service as recipes
from app.modules.sales import service as sales
from app.modules.uom.domain import from_base, normalise

ATTRIBUTION_DAYS: Final = "planning.attribution_days"
HOME_STORES: Final = ("RAW_STORE", "PACK_STORE")


def _on_hand_base(session: Session, item_id: uuid.UUID) -> Decimal:
    return sum((ledger.balance(session, item_id, store)[0] for store in HOME_STORES), Decimal(0))


def _active_packs(session: Session) -> list[dict[str, Any]]:
    """Every ACTIVE pack spec version with its recipe's ACTIVE version (both as frozen snapshots)."""
    out = []
    for spec in recipes.list_pack_specs(session):
        for v in spec["versions"]:
            if v["status"] != "ACTIVE":
                continue
            try:
                recipe = recipes.active_recipe_snapshot(session, uuid.UUID(spec["recipe_id"]))
            except DomainError:  # a pack whose recipe has no ACTIVE version is skipped
                continue
            out.append({"pack": recipes.pack_snapshot(session, uuid.UUID(v["id"])), "recipe": recipe})
    return out


def standard_batch(recipe: dict[str, Any], pack: dict[str, Any]) -> dict[uuid.UUID, Decimal]:
    """Base-unit quantity of each material one standard batch needs: recipe lines per batch, pack lines per good
    unit x the good units one batch should make (bulk yield / net weight)."""
    expected = Decimal(recipe["bulk_yield_g"]) / Decimal(pack["net_g"])
    need: dict[uuid.UUID, Decimal] = {}
    for ln in recipe["lines"]:
        item = uuid.UUID(ln["item_id"])
        need[item] = need.get(item, Decimal(0)) + Decimal(ln["qty_base"])
    for ln in pack["lines"]:
        item = uuid.UUID(ln["item_id"])
        need[item] = need.get(item, Decimal(0)) + Decimal(ln["qty_base"]) * expected
    return need


def runway(session: Session) -> list[dict[str, Any]]:
    """L1: for every active recipe and pack, the batches each material allows, the binding ones and full batches."""
    out = []
    for p in _active_packs(session):
        recipe, pack = p["recipe"], p["pack"]
        need = standard_batch(recipe, pack)
        units = catalog.units_for(session, need.keys())
        codes = catalog.codes_for(session, need.keys())
        source = SourceRef("pack_spec_version", pack["version_id"])
        needs = [
            MaterialNeed(
                codes[item],
                units[item].stock_uom,
                normalise(from_base(_on_hand_base(session, item), units[item].stock_uom, units[item])),
                normalise(from_base(qty, units[item].stock_uom, units[item])),
            )
            for item, qty in sorted(need.items(), key=lambda kv: codes[kv[0]])
        ]
        r = domain.runway(needs, source)
        out.append(
            {
                "pack_code": pack["code"],
                "pack_name": pack["name"],
                "recipe": f"{recipe['code']} v{recipe['version']}",
                "expected_good_per_batch": str(normalise(Decimal(recipe["bulk_yield_g"]) / Decimal(pack["net_g"]))),
                "materials": [
                    {
                        "item_code": ln.item_code,
                        "unit": ln.unit,
                        "available": str(ln.available),
                        "per_batch": str(ln.per_batch),
                        "batches": ln.explained.to_json(),
                        "binding": ln.item_code in r.binding,
                    }
                    for ln in r.lines
                ],
                "binding": list(r.binding),
                "full_batches": r.explained.to_json(),
            }
        )
    return out


def recent_losses(session: Session, item_id: uuid.UUID, on: date) -> list[YieldLoss]:
    days = effective_settings.decimal_on(session, ATTRIBUTION_DAYS, on)
    if days is None:
        raise PlanningError("attribution_window_missing", "the look-back window (planning.attribution_days) is not set")
    since = on - timedelta(days=int(days))
    losses = []
    for run in production.list_runs(session):
        if run["status"] != "COMPLETED" or not since <= date.fromisoformat(run["run_date"]) <= on:
            continue
        a = production.run_analysis(session, uuid.UUID(run["id"]))
        for pl in a.pack_lines:
            if pl.pack.fg_item_id == item_id and pl.good_units is not None:
                losses.append(YieldLoss(a.run_no, pl.expected_units, pl.good_units))
    return losses


def shortage_attribution(session: Session, order_id: uuid.UUID, on: date | None = None) -> dict[str, Any]:
    """L2: for each short line of an order, how much of the shortage recent yield losses explain."""
    today = on or business_date()
    card = sales.inbox_card(session, order_id)
    lines = []
    for ln in card["card_lines"]:
        shortage = int(Decimal(ln["shortage"]["value"]))
        if shortage <= 0:
            continue
        explained = domain.shortage_attribution(
            shortage, recent_losses(session, uuid.UUID(ln["item_id"]), today), SourceRef("sales_order", str(order_id))
        )
        lines.append(
            {
                "item_id": ln["item_id"],
                "item_name": ln["item_name"],
                "shortage": str(shortage),
                "attributed_to_yield_loss": explained.to_json(),
                "would_have_been": str(shortage - int(explained.value)),
            }
        )
    return {"order_id": str(order_id), "order_no": card["order_no"], "lines": lines}


# ---------- module 2: planning settings, the batch planner and drafts (L3-L5) ----------

BATCHES_PER_DAY: Final = "planning.batches_per_day"


def item_params(session: Session) -> dict[uuid.UUID, ItemParams]:
    return {
        r.item_id: ItemParams(r.reorder_level_base, r.safety_stock_base, r.min_order_base, r.lead_time_days)
        for r in session.execute(select(ItemPlanning)).scalars()
    }


def set_item_params(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    item_id: uuid.UUID,
    reorder_level_base: Decimal,
    safety_stock_base: Decimal,
    min_order_base: Decimal,
    lead_time_days: int,
) -> None:
    """Master data (L3): an item's reorder level, safety stock, minimum order (base units) and lead time. Audited."""
    values = {
        "reorder_level_base": reorder_level_base,
        "safety_stock_base": safety_stock_base,
        "min_order_base": min_order_base,
        "lead_time_days": lead_time_days,
    }
    if min(reorder_level_base, safety_stock_base, min_order_base) < 0 or not 0 <= lead_time_days <= 365:
        raise PlanningError("bad_planning_params", "planning settings are not negative; lead time is 0 to 365 days")
    catalog.kinds_for(session, [item_id])  # 404 for an unknown item
    session.execute(
        pg_insert(ItemPlanning)
        .values(organization_id=organization_id, item_id=item_id, created_by=actor_id, **values)
        .on_conflict_do_update(index_elements=["organization_id", "item_id"], set_=values)
    )
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="planning.item_params",
        entity_type="item",
        entity_id=item_id,
        after=values,
    )


def batch_plan(session: Session, on: date | None = None) -> dict[str, Any]:
    """L4: the next production day's batches, what they use, what a full plan lacks and what to buy. Recommends only."""
    today = on or business_date()
    capacity = effective_settings.decimal_on(session, BATCHES_PER_DAY, today)
    if capacity is None:
        raise PlanningError("capacity_missing", "the daily batch capacity (planning.batches_per_day) is not set")
    packs = _active_packs(session)
    material_ids: set[uuid.UUID] = set()
    options = []
    for p in packs:
        need = standard_batch(p["recipe"], p["pack"])
        material_ids |= set(need)
        expected = Decimal(p["recipe"]["bulk_yield_g"]) / Decimal(p["pack"]["net_g"])
        options.append((p, need, int(expected.to_integral_value(rounding=ROUND_FLOOR))))
    demand_raw = sales.open_demand(session)
    fg_ids = set(demand_raw) | {uuid.UUID(p["pack"]["fg_item_id"]) for p, _, _ in options}
    codes = catalog.codes_for(session, material_ids | fg_ids)
    units = catalog.units_for(session, material_ids)
    demand = []
    for item, (packets, value) in demand_raw.items():
        atp = int(ledger.available_to_promise(session, item, as_of=today)["available"])
        demand.append(Demand(codes[item], packets, atp, value / packets))
    params_by_id = item_params(session)
    result = planner.plan(
        [
            PackOption(
                p["pack"]["code"],
                p["pack"]["version_id"],
                codes[uuid.UUID(p["pack"]["fg_item_id"])],
                good,
                {codes[i]: q for i, q in need.items()},
            )
            for p, need, good in options
        ],
        demand,
        {codes[i]: _on_hand_base(session, i) for i in material_ids},
        int(capacity),
        {codes[i]: prm for i, prm in params_by_id.items() if i in codes},
    )
    by_code = {codes[i]: i for i in material_ids}

    def qty_view(code: str, base: Decimal) -> dict[str, str]:
        item = by_code[code]
        return {
            "item_code": code,
            "qty": str(normalise(from_base(base, units[item].stock_uom, units[item]))),
            "unit": units[item].stock_uom,
            "qty_base": str(normalise(base)),
        }

    return {
        "date": today.isoformat(),
        "capacity": str(int(capacity)),
        "status": result.status,
        "demand": [
            {
                "item_code": d.fg_item,
                "open_packets": str(d.open_packets),
                "available": str(d.available),
                "shortfall": str(d.shortfall),
                "value_per_packet": str(round_money(d.value_per_packet)),
                "met_today": str(result.met.get(d.fg_item, 0)),
            }
            for d in demand
        ],
        "batches": [
            {
                "pack_code": p["pack"]["code"],
                "pack_version_id": p["pack"]["version_id"],
                "recipe_version_id": p["recipe"]["version_id"],
                "batches": result.explained[p["pack"]["code"]].to_json()
                if p["pack"]["code"] in result.explained
                else None,
                "good_packets_per_batch": str(good),
            }
            for p, _, good in options
        ],
        "value_met": str(result.value_met),
        "materials_used": [qty_view(m, q) for m, q in sorted(result.materials_used.items()) if q],
        "materials_short": [qty_view(m, q) for m, q in sorted(result.short.items())],
        "purchases": [
            {
                **qty_view(pu.item, pu.qty),
                "item_id": str(by_code[pu.item]),
                "needed_by": (today + timedelta(days=pu.lead_time_days)).isoformat(),
                "lead_time_days": pu.lead_time_days,
                "explained": pu.explained.to_json(),
            }
            for pu in result.purchases
            if pu.item in by_code
        ],
        "note": "A recommendation. Approving a batch creates a DRAFT batch; approving purchases creates a "
        "DRAFT purchase order. Nothing is posted.",
    }


def approve_batch(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    recipe_version_id: uuid.UUID,
    pack_version_id: uuid.UUID,
    batches: int,
    run_date: date | None = None,
) -> uuid.UUID:
    """L5: a DRAFT production batch from the plan (starting it stays a manual step on the floor)."""
    if not 1 <= batches <= 20:
        raise PlanningError("bad_batches", "approve 1 to 20 batches at a time")
    return production.create_run(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        recipe_version_id=recipe_version_id,
        batch_multiplier=Decimal(batches),
        run_date=run_date or business_date(),
        pack_lines=[production.PackLineRequest(pack_version_id)],
    )


@dataclass(frozen=True)
class DraftLineIn:
    item_id: uuid.UUID
    qty_base: Decimal
    needed_by: date
    reason: str | None = None


def create_draft_po(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    lines: list[DraftLineIn],
    supplier_id: uuid.UUID | None = None,
    note: str | None = None,
) -> tuple[uuid.UUID, str]:
    """L5: a DRAFT purchase order: what to buy and by when. Intent only: no stock and no money move."""
    if not lines:
        raise PlanningError("empty_draft", "a draft purchase order needs at least one line")
    if any(ln.qty_base <= 0 for ln in lines):
        raise PlanningError("qty_not_positive", "each line needs a positive quantity")
    catalog.kinds_for(session, [ln.item_id for ln in lines])
    on = business_date()
    try:
        with session.begin_nested():
            fy = financial_year(on)
            number = session.execute(
                text("SELECT aahar_next_doc_number(:o, 'DPO', :fy)"), {"o": organization_id, "fy": fy}
            ).scalar_one()
            draft_no = f"DPO/{fy}/{int(number):06d}"
            draft_id = uuid.uuid4()
            session.execute(
                insert(DraftPurchaseOrder).values(
                    id=draft_id,
                    organization_id=organization_id,
                    draft_no=draft_no,
                    supplier_id=supplier_id,
                    note=(note or "").strip() or None,
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(DraftPurchaseOrderLine),
                [
                    {
                        "organization_id": organization_id,
                        "draft_id": draft_id,
                        "line_no": n,
                        "item_id": ln.item_id,
                        "qty_base": ln.qty_base,
                        "needed_by": ln.needed_by,
                        "reason": ln.reason,
                        "created_by": actor_id,
                    }
                    for n, ln in enumerate(lines, start=1)
                ],
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="planning.draft_po",
                entity_type="draft_purchase_order",
                entity_id=draft_id,
                after={
                    "draft_no": draft_no,
                    "supplier_id": supplier_id,
                    "lines": [
                        {"item_id": ln.item_id, "qty_base": ln.qty_base, "needed_by": ln.needed_by} for ln in lines
                    ],
                },
            )
    except DBAPIError as exc:
        err = domain_error_from_db(exc)
        if err is None:
            raise
        raise err from exc
    return draft_id, draft_no


def draft_pos(session: Session) -> list[dict[str, Any]]:
    drafts = list(session.execute(select(DraftPurchaseOrder).order_by(DraftPurchaseOrder.created_at.desc())).scalars())
    lines = list(
        session.execute(
            select(DraftPurchaseOrderLine).where(DraftPurchaseOrderLine.draft_id.in_([d.id for d in drafts]))
        ).scalars()
    )
    ids = {ln.item_id for ln in lines}
    codes = catalog.codes_for(session, ids)
    units = catalog.units_for(session, ids)
    return [
        {
            "id": str(d.id),
            "draft_no": d.draft_no,
            "status": d.status,
            "created_at": d.created_at.isoformat(),
            "note": d.note,
            "lines": [
                {
                    "item_code": codes[ln.item_id],
                    "qty": str(normalise(from_base(ln.qty_base, units[ln.item_id].stock_uom, units[ln.item_id]))),
                    "unit": units[ln.item_id].stock_uom,
                    "needed_by": ln.needed_by.isoformat(),
                    "reason": ln.reason,
                }
                for ln in sorted(lines, key=lambda x: x.line_no)
                if ln.draft_id == d.id
            ],
        }
        for d in drafts
    ]


def cancel_draft_po(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, draft_id: uuid.UUID, reason: str
) -> None:
    """A draft is cancelled with a reason, never deleted. Its lines stay as written."""
    reason = reason.strip()
    if not reason:
        raise PlanningError("reason_required", "say why the draft is cancelled")
    draft = session.execute(
        select(DraftPurchaseOrder).where(DraftPurchaseOrder.id == draft_id).with_for_update()
    ).scalar_one_or_none()
    if draft is None:
        raise NotFoundError("draft_not_found", "unknown draft purchase order")
    if draft.status != "DRAFT":
        raise ConflictError("draft_already_cancelled", "this draft is already cancelled")
    draft.status = "CANCELLED"
    draft.cancelled_at = func.now()
    draft.cancel_reason = reason
    session.flush()
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="planning.draft_po_cancel",
        entity_type="draft_purchase_order",
        entity_id=draft_id,
        before={"status": "DRAFT"},
        after={"status": "CANCELLED", "reason": reason},
    )


def item_params_view(session: Session) -> list[dict[str, Any]]:
    rows = list(session.execute(select(ItemPlanning)).scalars())
    codes = catalog.codes_for(session, {r.item_id for r in rows})
    return sorted(
        (
            {
                "item_id": str(r.item_id),
                "item_code": codes[r.item_id],
                "reorder_level_base": str(normalise(r.reorder_level_base)),
                "safety_stock_base": str(normalise(r.safety_stock_base)),
                "min_order_base": str(normalise(r.min_order_base)),
                "lead_time_days": r.lead_time_days,
            }
            for r in rows
        ),
        key=lambda x: str(x["item_code"]),
    )
