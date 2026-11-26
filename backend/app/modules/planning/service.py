"""Planning use cases (MP12, ADR-0019). Read-only except the approve actions (module 2), which create DRAFTS only.

Module 1: material runway (L1) and shortage attribution (L2).
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.calendar import business_date
from app.core.errors import DomainError
from app.core.explained import SourceRef
from app.modules.catalog import service as catalog
from app.modules.ledger import service as ledger
from app.modules.planning import domain
from app.modules.planning.domain import MaterialNeed, PlanningError, YieldLoss
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
