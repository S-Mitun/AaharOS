"""Costing use cases (MP07, ADR-0014). Other modules call only this file.

- standard cost cards: created append-only (migration 0008), one version per pack spec version at a time, found for a
  run by its run date (decision F4)
- `run_costing(run_id)`: run cost, cost per good unit, the waterfall and the FIFO / LAST sensitivity, every figure an
  `Explained` value, computed from `production.service.costing_facts` (the run's snapshot and posted actuals)
Costing writes no stock: run costs and their true-ups are posted by `production` (decision F1).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.money import round_money
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.costing import domain
from app.modules.costing.domain import CardLine, CostingError, MethodValue, RunCost, StandardCard, Waterfall
from app.modules.costing.models import StandardCostCard, StandardCostLine
from app.modules.production import service as production
from app.modules.production.domain import PackStd, RecipeStd, RunCostingFacts
from app.modules.recipe import service as recipes
from app.modules.uom.domain import normalise
from app.modules.valuation import service as valuation

SENSITIVITY_METHODS = ("WAC", "FIFO", "LAST")


def _db_error(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


# ---------- standard cost cards ----------


def create_card(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    pack_spec_version_id: uuid.UUID,
    effective_from: date,
    rates: Mapping[uuid.UUID, Decimal],  # rupees per stock unit (per kg, per L, per piece)
    conversion: Mapping[str, Decimal],  # rupees per batch, e.g. {"labour": 1200, "gas_power": 600}
) -> uuid.UUID:
    """A new card version for an ACTIVE pack spec version, built from its recipe's ACTIVE version."""
    pack = PackStd.from_snapshot(recipes.pack_snapshot(session, pack_spec_version_id))
    recipe = RecipeStd.from_snapshot(recipes.active_recipe_snapshot(session, pack.recipe_id))
    units = catalog.units_for(session, rates)
    if set(units) != set(rates):
        raise NotFoundError("item_not_found", "a rate names an unknown item")
    per_base = {item: domain.rate_per_base(rate, units[item]) for item, rate in rates.items()}
    lines, per_unit = domain.card_lines(recipe, pack, per_base, conversion)
    card_id = uuid.uuid4()
    try:
        with session.begin_nested():
            version = session.execute(
                select(func.coalesce(func.max(StandardCostCard.version), 0) + 1).where(
                    StandardCostCard.pack_spec_version_id == pack_spec_version_id
                )
            ).scalar_one()
            session.execute(
                insert(StandardCostCard).values(
                    id=card_id,
                    organization_id=organization_id,
                    pack_spec_version_id=pack_spec_version_id,
                    version=version,
                    per_unit=per_unit,
                    effective_from=effective_from,
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(StandardCostLine),
                [
                    {
                        "organization_id": organization_id,
                        "card_id": card_id,
                        "cost_kind": ln.cost_kind,
                        "item_id": ln.item_id,
                        "label": ln.label,
                        "std_qty_base": ln.std_qty_base,
                        "std_rate": ln.std_rate,
                        "created_by": actor_id,
                    }
                    for ln in lines
                ],
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="standard_cost_card.create",
                entity_type="standard_cost_card",
                entity_id=card_id,
                after={
                    "pack_spec": pack.code,
                    "pack_spec_version_id": pack_spec_version_id,
                    "version": version,
                    "effective_from": effective_from,
                    "per_unit": per_unit,
                    "lines": [
                        {"kind": ln.cost_kind, "label": ln.label, "qty": ln.std_qty_base, "rate": ln.std_rate}
                        for ln in lines
                    ],
                },
            )
    except DBAPIError as exc:
        err = _db_error(exc)
        if err.code == "duplicate":
            raise CostingError(
                "card_version_taken", "another card version was created at the same time; retry"
            ) from exc
        raise err from exc
    return card_id


def _card(session: Session, row: StandardCostCard) -> StandardCard:
    lines = session.execute(select(StandardCostLine).where(StandardCostLine.card_id == row.id)).scalars()
    return StandardCard(
        card_id=row.id,
        pack_spec_version_id=row.pack_spec_version_id,
        version=row.version,
        effective_from=row.effective_from,
        per_unit=row.per_unit,
        lines=tuple(
            CardLine(ln.cost_kind, ln.item_id, ln.label, ln.std_qty_base, ln.std_rate)
            for ln in sorted(lines, key=lambda x: (x.cost_kind, x.label))
        ),
    )


def card_for(session: Session, pack_spec_version_id: uuid.UUID, on: date) -> StandardCard | None:
    """The card in force on `on`: the latest effective date on or before it, then the highest version."""
    row = session.execute(
        select(StandardCostCard)
        .where(StandardCostCard.pack_spec_version_id == pack_spec_version_id, StandardCostCard.effective_from <= on)
        .order_by(StandardCostCard.effective_from.desc(), StandardCostCard.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    return None if row is None else _card(session, row)


def list_cards(session: Session) -> list[dict[str, Any]]:
    rows = list(
        session.execute(
            select(StandardCostCard).order_by(
                StandardCostCard.pack_spec_version_id, StandardCostCard.effective_from, StandardCostCard.version
            )
        ).scalars()
    )
    out = []
    for row in rows:
        card = _card(session, row)
        out.append(
            {
                "id": str(card.card_id),
                "pack_spec_version_id": str(card.pack_spec_version_id),
                "version": card.version,
                "effective_from": card.effective_from.isoformat(),
                "per_unit": str(card.per_unit),
                "per_unit_display": str(round_money(card.per_unit)),
                "lines": [
                    {
                        "cost_kind": ln.cost_kind,
                        "item_id": None if ln.item_id is None else str(ln.item_id),
                        "label": ln.label,
                        "std_qty_base": str(normalise(ln.std_qty_base)),
                        "std_rate": str(normalise(ln.std_rate)),
                    }
                    for ln in card.lines
                ],
            }
        )
    return out


# ---------- run costing ----------


@dataclass(frozen=True)
class RunCosting:
    facts: RunCostingFacts
    cost: RunCost
    waterfall: Waterfall | None
    waterfall_reason: str | None
    sensitivity: dict[str, dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        f = self.facts
        return {
            "run_id": str(f.run_id),
            "run_no": f.run_no,
            "cost_status": f.cost_status,
            "run_date": f.run_date.isoformat(),
            "lots": [
                {
                    "pack_spec": p.pack.code,
                    "lot_no": p.lot_no,
                    "good_units": p.good_units,
                    "lot_value": str(p.lot_value),
                }
                for p in f.packs
            ],
            "cost": self.cost.to_json(),
            "waterfall": None if self.waterfall is None else self.waterfall.to_json(),
            "waterfall_unavailable": self.waterfall_reason,
            "sensitivity": self.sensitivity,
            "note": "Direct (marginal) cost: monthly overheads are not absorbed into lots (ADR-0014, F7).",
        }


def _method_values(session: Session, facts: RunCostingFacts) -> dict[str, list[MethodValue]]:
    """Each material of the run re-valued under every method as of the journal that issued it (decision F6)."""
    out: dict[str, list[MethodValue]] = {m: [] for m in SENSITIVITY_METHODS}
    for m in facts.materials:
        issues = [mv for mv in m.moves if mv.direction == "ISSUE"]
        issued_qty = sum((mv.qty_base for mv in issues), Decimal(0))
        totals = dict.fromkeys(SENSITIVITY_METHODS, Decimal(0))
        fallback = dict.fromkeys(SENSITIVITY_METHODS, False)
        for mv in issues:
            at = valuation.sensitivity_at(session, m.item_id, mv.qty_base, mv.journal_id)
            for method in SENSITIVITY_METHODS:
                value = mv.value if method == "WAC" else at[method]["value"]
                if value is None:
                    value, fallback[method] = mv.value, True
                totals[method] += value
        for method in SENSITIVITY_METHODS:
            # returns come back in proportion: the net quantity carries the method's average for this run
            value = (
                totals[method] if m.qty_base == issued_qty else round_money(totals[method] * m.qty_base / issued_qty)
            )
            if method == "WAC":
                value = m.value
            out[method].append(MethodValue(m.item_code, m.value, value, fallback[method]))
    return out


def run_costing(session: Session, run_id: uuid.UUID) -> RunCosting:
    facts = production.costing_facts(session, run_id)
    cost = domain.run_cost(facts)
    cards = [card_for(session, p.pack.version_id, facts.run_date) for p in facts.packs]
    waterfall, reason = None, None
    if any(c is None for c in cards):
        reason = "no standard cost card in force on the run date for every pack line"
    else:
        try:
            waterfall = domain.waterfall(facts, [c for c in cards if c is not None])
        except CostingError as exc:
            reason = exc.message
    good = sum((p.good_units for p in facts.packs), 0) if len(facts.packs) == 1 else 0
    unit = facts.packs[0].pack.fg_stock_uom
    sensitivity = domain.sensitivity(cost.total.value, good, _method_values(session, facts), unit)
    return RunCosting(facts, cost, waterfall, reason, sensitivity)
