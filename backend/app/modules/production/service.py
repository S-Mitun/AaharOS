"""Production-run use cases (MP06, ADR-0002, ADR-0003, ADR-0013). Other modules call only this file.

Functions run in the caller's transaction and never commit (the API route commits once).

- `create_run`: DRAFT, numbered B-001, B-002, ... (decision E3); recipe version, batch multiplier, pack lines with the
  bulk allocated to each (over-allocation refused).
- `start_run`: DRAFT -> IN_PROGRESS; freezes the recipe and pack snapshots and the variance tolerance in force on the
  run date. Only ACTIVE versions can start, and the database freezes the snapshots, so a used version never changes.
- `issue_materials`: a material issue (MI/26-27/000001) RAW_STORE -> WIP at WAC, or a return WIP -> RAW_STORE at
  the run's own issued average.
- `complete_run`, atomic in one savepoint: lots, one RUN_COMPLETION journal, pack lines, fill-weight samples, the oil
  session, then the run -> COMPLETED in a single update and an audit row. Any refusal leaves nothing behind.
- `run_analysis` / `get_run`: variances, packing and mass balance computed on read from the frozen snapshot and the
  posted actuals (decision E1), every figure an `Explained` value.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import effective_settings, idempotency
from app.core.calendar import business_date, financial_year
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.explained import SourceRef
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.ledger import service as ledger
from app.modules.ledger.domain import LineSpec
from app.modules.production import domain
from app.modules.production.domain import (
    ConversionFacts,
    IssuedMaterial,
    IssueMove,
    LotPosition,
    LotState,
    MassBalance,
    MaterialFacts,
    PackagingUse,
    PackedMass,
    PackFacts,
    Packing,
    PackOutcome,
    PackStd,
    RecipeStd,
    RunCostingFacts,
    RunError,
    StdLine,
    Variance,
)
from app.modules.production.models import (
    FillWeightSample,
    MaterialIssue,
    MaterialIssueLine,
    OilSession,
    ProductionRun,
    RunCost,
    RunPackLine,
)
from app.modules.recipe import service as recipes
from app.modules.uom.domain import from_base, normalise, require_decimal, to_base
from app.modules.valuation import service as valuation

RUN_DOC: Final = "RUN"
RUN_SEQUENCE_FY: Final = "00-00"  # run numbers are perpetual, not per financial year (decision E3)
ISSUE_DOC: Final = "MI"
ISSUE_DIRECTIONS: Final = ("ISSUE", "RETURN")
DIRECTION_KIND: Final = {"ISSUE": "ISSUE", "RETURN": "RETURN"}


def _db_error(exc: DBAPIError) -> DomainError:
    err = domain_error_from_db(exc)
    if err is None:
        raise exc
    return err


def _next_number(session: Session, organization_id: uuid.UUID, doc: str, fy: str) -> int:
    return int(
        session.execute(
            text("SELECT aahar_next_doc_number(:o, :t, :fy)"), {"o": organization_id, "t": doc, "fy": fy}
        ).scalar_one()
    )


def _replayed_ids(stored: idempotency.StoredResponse, key: str) -> dict[str, Any]:
    if key not in stored.body:
        raise ConflictError("idempotency_key_reused", "this Idempotency-Key belongs to a different kind of request")
    return stored.body


# ---------- create and start ----------


@dataclass(frozen=True)
class PackLineRequest:
    pack_spec_version_id: uuid.UUID
    bulk_allocated_g: Decimal | None = None  # None with a single pack line: all the expected bulk


def create_run(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    recipe_version_id: uuid.UUID,
    batch_multiplier: Decimal,
    run_date: date,
    pack_lines: Sequence[PackLineRequest],
) -> uuid.UUID:
    """A DRAFT run with its pack lines. Versions must be ACTIVE and the pack specs must pack this recipe."""
    recipe_snap = recipes.recipe_snapshot(session, recipe_version_id)
    recipe = RecipeStd.from_snapshot(recipe_snap)
    recipe_id = uuid.UUID(recipe_snap["recipe_id"])
    bulk = domain.expected_bulk(recipe, batch_multiplier)
    if not pack_lines:
        raise RunError("no_pack_lines", "a run needs at least one pack line")
    if len({p.pack_spec_version_id for p in pack_lines}) != len(pack_lines):
        raise RunError("duplicate_pack_line", "each pack spec version may appear once in a run")
    domain.lot_numbers("x", len(pack_lines))  # refuses more pack lines than lot suffixes
    packs = [PackStd.from_snapshot(recipes.pack_snapshot(session, p.pack_spec_version_id)) for p in pack_lines]
    for pack in packs:
        if pack.recipe_id != recipe_id:
            raise RunError("pack_spec_for_other_recipe", f"pack spec {pack.code} packs a different recipe")
    if len(pack_lines) == 1 and pack_lines[0].bulk_allocated_g is None:
        allocations = [bulk]
    elif any(p.bulk_allocated_g is None for p in pack_lines):
        raise RunError("allocation_required", "with several pack lines, each needs its bulk allocated (g)")
    else:
        allocations = [require_decimal(p.bulk_allocated_g, "bulk_allocated_g") for p in pack_lines]
    domain.check_allocation(bulk, allocations)

    run_id = uuid.uuid4()
    try:
        with session.begin_nested():
            number = domain.run_no(_next_number(session, organization_id, RUN_DOC, RUN_SEQUENCE_FY))
            session.execute(
                insert(ProductionRun).values(
                    id=run_id,
                    organization_id=organization_id,
                    run_no=number,
                    recipe_version_id=recipe_version_id,
                    batch_multiplier=batch_multiplier,
                    status="DRAFT",
                    run_date=run_date,
                    operator_id=actor_id,
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(RunPackLine),
                [
                    {
                        "organization_id": organization_id,
                        "run_id": run_id,
                        "pack_spec_version_id": pack.version_id,
                        "bulk_allocated_g": alloc,
                        "expected_units": domain.stored_expected_units(alloc, pack.net_g),
                        "created_by": actor_id,
                    }
                    for pack, alloc in zip(packs, allocations, strict=True)
                ],
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="run.create",
                entity_type="production_run",
                entity_id=run_id,
                after={
                    "run_no": number,
                    "recipe_version_id": recipe_version_id,
                    "batch_multiplier": batch_multiplier,
                    "run_date": run_date,
                    "pack_lines": [
                        {"pack_spec_version_id": p.version_id, "bulk_allocated_g": a}
                        for p, a in zip(packs, allocations, strict=True)
                    ],
                },
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return run_id


def _lock_run(session: Session, run_id: uuid.UUID) -> ProductionRun:
    run = session.execute(
        select(ProductionRun).where(ProductionRun.id == run_id).with_for_update()
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("run_not_found", "unknown production run")
    return run


def _require_status(run: ProductionRun, status: str, doing: str) -> None:
    if run.status != status:
        raise RunError("bad_run_status", f"run {run.run_no} is {run.status}: only an {status} run can {doing}")


def _pack_lines(session: Session, run_id: uuid.UUID) -> list[RunPackLine]:
    return list(session.execute(select(RunPackLine).where(RunPackLine.run_id == run_id)).scalars())


def start_run(session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, run_id: uuid.UUID) -> None:
    """DRAFT -> IN_PROGRESS, freezing the recipe and pack snapshots and the tolerance in force on the run date."""
    run = _lock_run(session, run_id)
    _require_status(run, "DRAFT", "start")
    tolerance = effective_settings.decimal_on(session, domain.TOLERANCE_SETTING, run.run_date)
    if tolerance is None:
        raise RunError(
            "no_tolerance_configured",
            f"no {domain.TOLERANCE_SETTING} setting is in force on {run.run_date.isoformat()}: configure it first",
        )
    recipe_snap = {
        **recipes.recipe_snapshot(session, run.recipe_version_id),
        "variance_tolerance_pct": str(normalise(tolerance)),
        "tolerance_setting": domain.TOLERANCE_SETTING,
        "tolerance_as_of": run.run_date.isoformat(),
    }
    versions = {
        str(pl.pack_spec_version_id): recipes.pack_snapshot(session, pl.pack_spec_version_id)
        for pl in _pack_lines(session, run_id)
    }
    try:
        with session.begin_nested():
            session.execute(
                update(ProductionRun)
                .where(ProductionRun.id == run_id)
                .values(
                    status="IN_PROGRESS",
                    recipe_snapshot=recipe_snap,
                    pack_snapshot={"versions": versions},
                    started_at=func.now(),
                )
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="run.start",
                entity_type="production_run",
                entity_id=run_id,
                before={"status": "DRAFT"},
                after={
                    "status": "IN_PROGRESS",
                    "recipe_version_id": run.recipe_version_id,
                    "pack_spec_version_ids": sorted(versions),
                    "variance_tolerance_pct": tolerance,
                },
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    session.expire(run)


# ---------- material issues and returns ----------


@dataclass(frozen=True)
class MaterialLineIn:
    item_id: uuid.UUID
    qty: Decimal
    unit: str


@dataclass(frozen=True)
class IssueResult:
    issue_id: uuid.UUID
    issue_no: str
    journal_id: uuid.UUID
    replayed: bool


def net_issued(session: Session, run_id: uuid.UUID) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    """The run's net issues per item, (qty_base, value): issues minus returns, at the value they were posted at."""
    rows = session.execute(
        select(MaterialIssue.direction, MaterialIssueLine.item_id, MaterialIssueLine.qty_base, MaterialIssueLine.value)
        .join(MaterialIssue, MaterialIssue.id == MaterialIssueLine.issue_id)
        .where(MaterialIssue.run_id == run_id)
    ).all()
    out: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
    for direction, item_id, qty, value in rows:
        sign = 1 if direction == "ISSUE" else -1
        q, v = out.get(item_id, (Decimal(0), Decimal(0)))
        out[item_id] = (q + sign * qty, v + sign * value)
    return out


def issue_materials(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    run_id: uuid.UUID,
    lines: Sequence[MaterialLineIn],
    direction: str = "ISSUE",
    posting_date: date | None = None,
    idempotency_key: uuid.UUID | None = None,
) -> IssueResult:
    """Issue raw materials to an IN_PROGRESS run (RAW_STORE -> WIP at WAC), or return them (WIP -> RAW_STORE)."""
    if direction not in ISSUE_DIRECTIONS:
        raise RunError("bad_direction", "direction must be ISSUE or RETURN")
    if not lines:
        raise RunError("no_lines", "a material issue needs at least one line")
    if len({ln.item_id for ln in lines}) != len(lines):
        raise RunError("duplicate_item", "an item may appear only once in a material issue")
    on = posting_date or business_date()
    item_ids = [ln.item_id for ln in lines]
    units = catalog.units_for(session, item_ids)
    kinds = catalog.kinds_for(session, item_ids)
    planned: list[tuple[uuid.UUID, Decimal]] = []
    for ln in lines:
        if ln.item_id not in units:
            raise NotFoundError("item_not_found", "unknown item", {"item_id": str(ln.item_id)})
        if kinds[ln.item_id] != "RAW":
            raise RunError(
                "not_raw_material", "material issues take raw materials; packaging is consumed at completion"
            )
        qty_base = to_base(ln.qty, ln.unit, units[ln.item_id])
        if qty_base <= 0:
            raise RunError("qty_not_positive", "issued quantities must be positive")
        planned.append((ln.item_id, qty_base))
    digest = idempotency.request_hash(
        {
            "op": "material_issue",
            "run_id": str(run_id),
            "direction": direction,
            "posting_date": on.isoformat(),
            "lines": sorted([str(i), q] for i, q in planned),
        }
    )
    try:
        with session.begin_nested():
            if idempotency_key is not None:
                stored = idempotency.claim(session, organization_id, idempotency_key, digest)
                if stored is not None:
                    body = _replayed_ids(stored, "issue_id")
                    return IssueResult(
                        uuid.UUID(body["issue_id"]), body["issue_no"], uuid.UUID(body["journal_id"]), replayed=True
                    )
            run = _lock_run(session, run_id)
            _require_status(run, "IN_PROGRESS", "take material issues")
            held = net_issued(session, run_id) if direction == "RETURN" else {}
            valued: list[tuple[uuid.UUID, Decimal, Decimal]] = []
            for item_id, qty_base in planned:
                if direction == "ISSUE":
                    value = valuation.issue_value(
                        session,
                        organization_id=organization_id,
                        item_id=item_id,
                        qty_base=qty_base,
                        from_location="RAW_STORE",
                    )
                else:
                    net_qty, net_value = held.get(item_id, (Decimal(0), Decimal(0)))
                    value = domain.returned_value(net_qty, net_value, qty_base)
                valued.append((item_id, qty_base, value))
            issue_id = uuid.uuid4()
            number = domain.issue_no(
                financial_year(on), _next_number(session, organization_id, ISSUE_DOC, financial_year(on))
            )
            src, dst = ("RAW_STORE", "WIP") if direction == "ISSUE" else ("WIP", "RAW_STORE")
            specs: list[LineSpec] = []
            for item_id, qty_base, value in valued:
                base = units[item_id].base_uom
                specs += [
                    LineSpec(item_id, dst, qty_base, base, value),
                    LineSpec(item_id, src, -qty_base, base, -value),
                ]
            posted = ledger.post(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                kind=DIRECTION_KIND[direction],
                source_type="material_issue",
                source_id=issue_id,
                posting_date=on,
                lines=specs,
            )
            session.execute(
                insert(MaterialIssue).values(
                    id=issue_id,
                    organization_id=organization_id,
                    issue_no=number,
                    run_id=run_id,
                    direction=direction,
                    posting_date=on,
                    journal_id=posted.journal_id,
                    created_by=actor_id,
                )
            )
            session.execute(
                insert(MaterialIssueLine),
                [
                    {
                        "organization_id": organization_id,
                        "issue_id": issue_id,
                        "item_id": item_id,
                        "qty_base": qty_base,
                        "value": value,
                        "created_by": actor_id,
                    }
                    for item_id, qty_base, value in valued
                ],
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="material_issue.post",
                entity_type="material_issue",
                entity_id=issue_id,
                after={
                    "issue_no": number,
                    "run_no": run.run_no,
                    "direction": direction,
                    "journal_id": posted.journal_id,
                    "lines": [{"item_id": i, "qty_base": q, "value": v} for i, q, v in valued],
                },
            )
            if idempotency_key is not None:
                idempotency.complete(
                    session,
                    organization_id,
                    idempotency_key,
                    201,
                    {"issue_id": issue_id, "issue_no": number, "journal_id": posted.journal_id},
                )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return IssueResult(issue_id, number, posted.journal_id, replayed=False)


# ---------- completion ----------


@dataclass(frozen=True)
class PackagingIn:
    item_id: uuid.UUID
    used: Decimal  # taken from the packaging store, damaged included
    damaged: Decimal = Decimal(0)
    unit: str = "piece"


@dataclass(frozen=True)
class PackResultIn:
    pack_line_id: uuid.UUID
    good_units: int
    packaging: Sequence[PackagingIn] = ()


@dataclass(frozen=True)
class SampleIn:
    gross_g: Decimal
    net_g: Decimal
    sampled_at: datetime | None = None


@dataclass(frozen=True)
class OilIn:
    fresh_ml: Decimal
    topup_ml: Decimal = Decimal(0)
    discard_ml: Decimal = Decimal(0)
    tpc_pct: Decimal | None = None


@dataclass(frozen=True)
class CompletionResult:
    run_id: uuid.UUID
    journal_id: uuid.UUID
    lot_ids: dict[uuid.UUID, uuid.UUID]  # pack line -> lot
    replayed: bool


def _ordered(run: ProductionRun, lines: Sequence[RunPackLine]) -> list[tuple[RunPackLine, PackStd]]:
    """Pack lines in a stable order, (pack spec code, version): it decides the lot suffix and the rounding remainder."""
    versions = (run.pack_snapshot or {}).get("versions", {})
    paired = [(pl, PackStd.from_snapshot(versions[str(pl.pack_spec_version_id)])) for pl in lines]
    return sorted(paired, key=lambda p: (p[1].code, p[1].version))


def complete_run(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    run_id: uuid.UUID,
    results: Sequence[PackResultIn],
    scrap_g: Decimal = Decimal(0),
    loss_g: Decimal = Decimal(0),
    scrap_reason: str | None = None,
    samples: Sequence[SampleIn] = (),
    oil: OilIn | None = None,
    posting_date: date | None = None,
    idempotency_key: uuid.UUID | None = None,
) -> CompletionResult:
    """Post the run's output atomically. Any refusal rolls the whole completion back and leaves the run IN_PROGRESS."""
    on = posting_date or business_date()
    reason = (scrap_reason or "").strip() or None
    run = session.execute(select(ProductionRun).where(ProductionRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise NotFoundError("run_not_found", "unknown production run")
    if run.recipe_snapshot is None:  # a COMPLETED run is checked after the key, so a retried submit replays
        _require_status(run, "IN_PROGRESS", "be completed")
    ordered = _ordered(run, _pack_lines(session, run_id))
    by_id = {r.pack_line_id: r for r in results}
    if len(by_id) != len(results) or set(by_id) != {pl.id for pl, _ in ordered}:
        raise RunError("pack_lines_mismatch", "give exactly one result for every pack line of the run")
    if samples and len(ordered) > 1:
        raise RunError(
            "samples_need_single_pack_line",
            "fill-weight samples are recorded per run, so they are accepted for single-pack-line runs only",
        )
    recipe = RecipeStd.from_snapshot(run.recipe_snapshot or {})

    # packaging in base units, checked against each pack spec
    pkg_items = {p.item_id for r in results for p in r.packaging}
    units = catalog.units_for(session, pkg_items | {pack.fg_item_id for _, pack in ordered})
    draft: list[tuple[RunPackLine, PackStd, PackResultIn, list[tuple[uuid.UUID, Decimal, Decimal]]]] = []
    for pl, pack in ordered:
        res = by_id[pl.id]
        if len({p.item_id for p in res.packaging}) != len(res.packaging):
            raise RunError("duplicate_item", "each packaging item appears once per pack line")
        uses = []
        for p in res.packaging:
            if pack.line_for(p.item_id) is None:
                raise RunError("not_in_pack_spec", f"this packaging item is not in pack spec {pack.code}")
            uses.append(
                (p.item_id, to_base(p.used, p.unit, units[p.item_id]), to_base(p.damaged, p.unit, units[p.item_id]))
            )
        draft.append((pl, pack, res, uses))
    domain.check_completion(
        [
            PackOutcome(
                pl.id,
                pl.bulk_allocated_g,
                res.good_units,
                pack.fg_item_id,
                "piece",
                None,
                tuple(PackagingUse(i, units[i].base_uom, u, d, Decimal(0)) for i, u, d in uses),
            )
            for pl, pack, res, uses in draft
        ],
        scrap_g,
        loss_g,
        reason,
    )
    for s in samples:
        if require_decimal(s.net_g, "net_g") <= 0 or require_decimal(s.gross_g, "gross_g") < s.net_g:
            raise RunError("bad_sample", "a sample needs 0 < net <= gross (grams)")
    digest = idempotency.request_hash(
        {
            "op": "run_completion",
            "run_id": str(run_id),
            "posting_date": on.isoformat(),
            "scrap_g": scrap_g,
            "loss_g": loss_g,
            "reason": reason,
            "results": sorted(
                [str(pl.id), res.good_units, sorted([str(i), u, d] for i, u, d in uses)] for pl, _, res, uses in draft
            ),
            "samples": [[s.gross_g, s.net_g] for s in samples],
            "oil": None if oil is None else [oil.fresh_ml, oil.topup_ml, oil.discard_ml, oil.tpc_pct],
        }
    )

    try:
        with session.begin_nested():
            if idempotency_key is not None:
                stored = idempotency.claim(session, organization_id, idempotency_key, digest)
                if stored is not None:
                    body = _replayed_ids(stored, "run_completion_journal_id")
                    return CompletionResult(
                        run_id,
                        uuid.UUID(body["run_completion_journal_id"]),
                        {uuid.UUID(k): uuid.UUID(v) for k, v in body["lot_ids"].items()},
                        replayed=True,
                    )
            run = _lock_run(session, run_id)
            _require_status(run, "IN_PROGRESS", "be completed")
            issued_now = net_issued(session, run_id)
            issued_units = catalog.units_for(session, issued_now)
            issued = [
                IssuedMaterial(i, issued_units[i].base_uom, q, v)
                for i, (q, v) in sorted(issued_now.items(), key=lambda x: str(x[0]))
            ]

            # one FG lot per pack line that made good units: mfg = run date, best-before from the pack spec
            lot_nos = domain.lot_numbers(run.run_no, len(draft))
            lots: dict[uuid.UUID, uuid.UUID] = {}
            for (pl, pack, res, _), lot_no in zip(draft, lot_nos, strict=True):
                if res.good_units > 0:
                    lots[pl.id] = ledger.create_lot(
                        session,
                        organization_id=organization_id,
                        actor_id=actor_id,
                        item_id=pack.fg_item_id,
                        lot_no=lot_no,
                        source_type="production_run",
                        source_id=run_id,
                        mfg_date=run.run_date,
                        best_before=domain.best_before(run.run_date, pack.shelf_life_days),
                    )

            # packaging valued at WAC per item over all pack lines, then split by quantity used
            used_by_item: dict[uuid.UUID, list[tuple[uuid.UUID, Decimal]]] = defaultdict(list)
            for pl, _, _, uses in draft:
                for item_id, used, _ in uses:
                    if used > 0:
                        used_by_item[item_id].append((pl.id, used))
            pkg_value: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = {}
            for item_id, parts in sorted(used_by_item.items(), key=lambda x: str(x[0])):
                total = valuation.issue_value(
                    session,
                    organization_id=organization_id,
                    item_id=item_id,
                    qty_base=sum((q for _, q in parts), Decimal(0)),
                    from_location="PACK_STORE",
                )
                for (pl_id, _), share in zip(parts, domain.split_value(total, [q for _, q in parts]), strict=True):
                    pkg_value[(pl_id, item_id)] = share

            outcomes = [
                PackOutcome(
                    pack_line_id=pl.id,
                    bulk_allocated_g=pl.bulk_allocated_g,
                    good_units=res.good_units,
                    fg_item_id=pack.fg_item_id,
                    fg_base_uom=units[pack.fg_item_id].base_uom,
                    lot_id=lots.get(pl.id),
                    packaging=tuple(
                        PackagingUse(i, units[i].base_uom, u, d, pkg_value.get((pl.id, i), Decimal(0)))
                        for i, u, d in uses
                    ),
                )
                for pl, pack, res, uses in draft
            ]
            plan = domain.plan_completion(issued, outcomes, bulk_item_id=recipe.bulk_item_id, scrap_g=scrap_g)
            posted = ledger.post(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                kind="RUN_COMPLETION",
                source_type="production_run",
                source_id=run_id,
                posting_date=on,
                lines=plan.lines,
            )
            for pl, _, res, uses in draft:
                session.execute(
                    update(RunPackLine)
                    .where(RunPackLine.id == pl.id)
                    .values(
                        good_units=res.good_units,
                        packaging_actual={str(i): str(normalise(u)) for i, u, _ in uses},
                        damage={str(i): str(normalise(d)) for i, _, d in uses if d},
                        lot_id=lots.get(pl.id),
                    )
                )
            if samples:
                session.execute(
                    insert(FillWeightSample),
                    [
                        {
                            "organization_id": organization_id,
                            "run_id": run_id,
                            "sampled_at": s.sampled_at or datetime.now(UTC),
                            "gross_g": s.gross_g,
                            "net_g": s.net_g,
                            "created_by": actor_id,
                        }
                        for s in samples
                    ],
                )
            if oil is not None:
                session.execute(
                    insert(OilSession).values(
                        organization_id=organization_id,
                        run_id=run_id,
                        fresh_ml=oil.fresh_ml,
                        topup_ml=oil.topup_ml,
                        discard_ml=oil.discard_ml,
                        tpc_pct=oil.tpc_pct,
                        created_by=actor_id,
                    )
                )
            session.execute(
                update(ProductionRun)
                .where(ProductionRun.id == run_id)
                .values(
                    status="COMPLETED", completed_at=func.now(), scrap_g=scrap_g, loss_g=loss_g, scrap_reason=reason
                )
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="run.complete",
                entity_type="production_run",
                entity_id=run_id,
                before={"status": "IN_PROGRESS"},
                after={
                    "status": "COMPLETED",
                    "run_no": run.run_no,
                    "journal_id": posted.journal_id,
                    "scrap_g": scrap_g,
                    "loss_g": loss_g,
                    "pack_lines": [
                        {
                            "pack_line_id": pl.id,
                            "good_units": res.good_units,
                            "lot_id": lots.get(pl.id),
                            "lot_value": plan.lot_value[pl.id],
                            "written_off": plan.written_off[pl.id],
                        }
                        for pl, _, res, _ in draft
                    ],
                },
                note=reason,
            )
            if idempotency_key is not None:
                idempotency.complete(
                    session,
                    organization_id,
                    idempotency_key,
                    201,
                    {"run_completion_journal_id": posted.journal_id, "lot_ids": {str(k): v for k, v in lots.items()}},
                )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    session.expire_all()
    return CompletionResult(run_id, posted.journal_id, lots, replayed=False)


# ---------- read models: variances, packing and mass balance on read (decision E1) ----------


@dataclass(frozen=True)
class PackLineAnalysis:
    pack_line_id: uuid.UUID
    pack: PackStd
    bulk_allocated_g: Decimal
    expected_units: Decimal
    good_units: int | None
    lot_no: str | None
    yield_variance: Variance | None
    packaging: tuple[tuple[Variance, Variance], ...]  # (flexible, batch view)
    packing: Packing | None

    def flexible(self, item_code: str) -> Variance:
        return next(f for f, _ in self.packaging if f.label == item_code)

    def batch_view(self, item_code: str) -> Variance:
        return next(b for _, b in self.packaging if b.label == item_code)


@dataclass(frozen=True)
class RunAnalysis:
    run_id: uuid.UUID
    run_no: str
    status: str
    tolerance_pct: Decimal
    expected_bulk_g: Decimal
    unallocated_g: Decimal
    ingredients: tuple[Variance, ...]
    pack_lines: tuple[PackLineAnalysis, ...]
    mass_balance: MassBalance | None
    flags: tuple[str, ...] = field(default_factory=tuple)

    def ingredient(self, item_code: str) -> Variance:
        return next(v for v in self.ingredients if v.label == item_code)

    def to_json(self) -> dict[str, Any]:
        return {
            "tolerance_pct": str(normalise(self.tolerance_pct)),
            "expected_bulk_g": str(normalise(self.expected_bulk_g)),
            "unallocated_bulk_g": str(normalise(self.unallocated_g)),
            "ingredients": [v.to_json() for v in self.ingredients],
            "pack_lines": [
                {
                    "pack_line_id": str(p.pack_line_id),
                    "pack_spec": p.pack.code,
                    "pack_spec_version": p.pack.version,
                    "bulk_allocated_g": str(normalise(p.bulk_allocated_g)),
                    "expected_units": str(normalise(p.expected_units)),
                    "good_units": p.good_units,
                    "lot_no": p.lot_no,
                    "yield": None if p.yield_variance is None else p.yield_variance.to_json(),
                    "packaging": [{"flexible": f.to_json(), "batch_view": b.to_json()} for f, b in p.packaging],
                    "packing": None if p.packing is None else p.packing.to_json(),
                }
                for p in self.pack_lines
            ],
            "mass_balance": None if self.mass_balance is None else self.mass_balance.to_json(),
            "flags": list(self.flags),
        }


def _lot_nos(session: Session, lot_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    return {lot_id: ledger.lot_no(session, lot_id) for lot_id in lot_ids}


def run_analysis(session: Session, run_id: uuid.UUID) -> RunAnalysis:
    """Variances, packing and mass balance, recomputed from the frozen snapshot and the posted actuals."""
    run = session.execute(select(ProductionRun).where(ProductionRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise NotFoundError("run_not_found", "unknown production run")
    if run.recipe_snapshot is None:
        raise RunError("run_not_started", f"run {run.run_no} has not started, so it has no frozen standard yet")
    source = SourceRef("production_run", str(run_id))
    recipe = RecipeStd.from_snapshot(run.recipe_snapshot)
    tolerance = Decimal(run.recipe_snapshot["variance_tolerance_pct"])
    issued = {i: q for i, (q, _) in net_issued(session, run_id).items()}
    extra = [i for i in issued if all(ln.item_id != i for ln in recipe.lines)]
    extra_lines = {}
    if extra:
        codes, units = catalog.codes_for(session, extra), catalog.units_for(session, extra)
        extra_lines = {i: StdLine(i, codes[i], units[i].base_uom, units[i].stock_uom, Decimal(0), None) for i in extra}
    ingredients = domain.ingredient_variances(recipe, run.batch_multiplier, issued, tolerance, extra_lines, source)

    ordered = _ordered(run, _pack_lines(session, run_id))
    lot_nos = _lot_nos(session, [pl.lot_id for pl, _ in ordered if pl.lot_id is not None])
    nets = list(session.execute(select(FillWeightSample.net_g).where(FillWeightSample.run_id == run_id)).scalars())
    analyses = []
    packed = []
    for pl, pack in ordered:
        good = pl.good_units
        used = {uuid.UUID(k): Decimal(v) for k, v in (pl.packaging_actual or {}).items()}
        if good is None:
            analyses.append(
                PackLineAnalysis(pl.id, pack, pl.bulk_allocated_g, pl.expected_units, None, None, None, (), None)
            )
            continue
        analyses.append(
            PackLineAnalysis(
                pack_line_id=pl.id,
                pack=pack,
                bulk_allocated_g=pl.bulk_allocated_g,
                expected_units=pl.expected_units,
                good_units=good,
                lot_no=None if pl.lot_id is None else lot_nos[pl.lot_id],
                yield_variance=domain.yield_variance(pack, pl.bulk_allocated_g, good, tolerance, source),
                packaging=tuple(domain.packaging_variances(pack, pl.bulk_allocated_g, good, used, tolerance, source)),
                packing=domain.packing(good, pack.units_per_carton, source),
            )
        )
        packed.append(PackedMass(pack.code, good, pack.net_g, domain.giveaway_g(nets, pack.net_g, good)))
    bulk = domain.expected_bulk(recipe, run.batch_multiplier)
    unallocated = bulk - sum((pl.bulk_allocated_g for pl, _ in ordered), Decimal(0))
    balance = (
        domain.mass_balance(bulk, unallocated, packed, run.scrap_g, run.loss_g, source)
        if run.status == "COMPLETED"
        else None
    )
    variances = [*ingredients, *(v for p in analyses for v in ([p.yield_variance] if p.yield_variance else []))]
    variances += [f for p in analyses for f, _ in p.packaging]
    return RunAnalysis(
        run_id=run.id,
        run_no=run.run_no,
        status=run.status,
        tolerance_pct=tolerance,
        expected_bulk_g=bulk,
        unallocated_g=unallocated,
        ingredients=tuple(ingredients),
        pack_lines=tuple(analyses),
        mass_balance=balance,
        flags=tuple(f"{v.label} {v.pct_display}%" if v.pct is not None else v.label for v in variances if v.flagged),
    )


def _issues(session: Session, run_id: uuid.UUID) -> list[dict[str, Any]]:
    issues = list(
        session.execute(
            select(MaterialIssue).where(MaterialIssue.run_id == run_id).order_by(MaterialIssue.issue_no)
        ).scalars()
    )
    lines = (
        list(
            session.execute(
                select(MaterialIssueLine).where(MaterialIssueLine.issue_id.in_([i.id for i in issues]))
            ).scalars()
        )
        if issues
        else []
    )
    codes = catalog.codes_for(session, {ln.item_id for ln in lines})
    units = catalog.units_for(session, {ln.item_id for ln in lines})
    return [
        {
            "id": str(i.id),
            "issue_no": i.issue_no,
            "direction": i.direction,
            "posting_date": i.posting_date.isoformat(),
            "journal_id": str(i.journal_id),
            "lines": [
                {
                    "item_id": str(ln.item_id),
                    "item_code": codes[ln.item_id],
                    "qty": str(from_base(ln.qty_base, units[ln.item_id].stock_uom, units[ln.item_id])),
                    "uom": units[ln.item_id].stock_uom,
                    "value": str(ln.value),
                }
                for ln in sorted(lines, key=lambda x: codes[x.item_id])
                if ln.issue_id == i.id
            ],
        }
        for i in issues
    ]


def get_run(session: Session, run_id: uuid.UUID) -> dict[str, Any]:
    run = session.execute(select(ProductionRun).where(ProductionRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise NotFoundError("run_not_found", "unknown production run")
    out: dict[str, Any] = {
        "id": str(run.id),
        "run_no": run.run_no,
        "status": run.status,
        "cost_status": run.cost_status,
        "run_date": run.run_date.isoformat(),
        "recipe_version_id": str(run.recipe_version_id),
        "batch_multiplier": str(normalise(run.batch_multiplier)),
        "started_at": None if run.started_at is None else run.started_at.isoformat(),
        "completed_at": None if run.completed_at is None else run.completed_at.isoformat(),
        "scrap_g": str(normalise(run.scrap_g)),
        "loss_g": str(normalise(run.loss_g)),
        "scrap_reason": run.scrap_reason,
        "issues": _issues(session, run_id),
        "oil_sessions": [
            {
                "fresh_ml": str(normalise(o.fresh_ml)),
                "topup_ml": str(normalise(o.topup_ml)),
                "discard_ml": str(normalise(o.discard_ml)),
                "tpc_pct": None if o.tpc_pct is None else str(normalise(o.tpc_pct)),
            }
            for o in session.execute(select(OilSession).where(OilSession.run_id == run_id)).scalars()
        ],
        "fill_weight_samples": [
            {
                "gross_g": str(normalise(s.gross_g)),
                "net_g": str(normalise(s.net_g)),
                "sampled_at": s.sampled_at.isoformat(),
            }
            for s in session.execute(
                select(FillWeightSample).where(FillWeightSample.run_id == run_id).order_by(FillWeightSample.sampled_at)
            ).scalars()
        ],
    }
    if run.recipe_snapshot is None:
        out["pack_lines"] = [
            {
                "pack_line_id": str(pl.id),
                "pack_spec_version_id": str(pl.pack_spec_version_id),
                "bulk_allocated_g": str(normalise(pl.bulk_allocated_g)),
                "expected_units": str(normalise(pl.expected_units)),
            }
            for pl in _pack_lines(session, run_id)
        ]
        out["analysis"] = None
    else:
        out["recipe"] = {k: run.recipe_snapshot[k] for k in ("code", "name", "version", "bulk_item_code")}
        out["analysis"] = run_analysis(session, run_id).to_json()
    return out


def list_runs(session: Session) -> list[dict[str, Any]]:
    runs = list(session.execute(select(ProductionRun).order_by(ProductionRun.run_no)).scalars())
    good = {
        run_id: total
        for run_id, total in session.execute(
            select(RunPackLine.run_id, func.sum(RunPackLine.good_units)).group_by(RunPackLine.run_id)
        ).tuples()
    }
    return [
        {
            "id": str(r.id),
            "run_no": r.run_no,
            "status": r.status,
            "cost_status": r.cost_status,
            "run_date": r.run_date.isoformat(),
            "recipe": None
            if r.recipe_snapshot is None
            else f"{r.recipe_snapshot['code']} v{r.recipe_snapshot['version']}",
            "good_units": good.get(r.id),
        }
        for r in runs
    ]


# ---------- integrity (make integrity, invariant S6) ----------


def completed_run_wip_mismatches(session: Session) -> list[dict[str, str]]:
    """S6: for every COMPLETED run, its WIP is zero per item, in quantity and value (net issues = what completion
    consumed), read from the ledger lines of its material issues and its completion journal. A completed run with no
    completion journal is listed too. Empty means S6 holds (sees all organizations as the owner)."""
    rows = session.execute(
        text(
            """
            WITH run_journals AS (
              SELECT r.id AS run_id, mi.journal_id
                FROM production_runs r JOIN material_issues mi ON mi.run_id = r.id
               WHERE r.status = 'COMPLETED'
              UNION ALL
              SELECT r.id, j.id
                FROM production_runs r
                JOIN stock_journals j ON j.source_type = 'production_run' AND j.source_id = r.id
                                     AND j.kind = 'RUN_COMPLETION'
               WHERE r.status = 'COMPLETED'
            )
            SELECT r.organization_id, r.run_no, sl.item_id::text, sum(sl.qty_base), sum(sl.value)
              FROM run_journals rj
              JOIN production_runs r ON r.id = rj.run_id
              JOIN stock_lines sl ON sl.journal_id = rj.journal_id
              JOIN locations l ON l.id = sl.location_id AND l.code = 'WIP'
             GROUP BY r.organization_id, r.run_no, sl.item_id
            HAVING sum(sl.qty_base) <> 0 OR sum(sl.value) <> 0
            UNION ALL
            SELECT r.organization_id, r.run_no, 'no completion journal', 0, 0
              FROM production_runs r
             WHERE r.status = 'COMPLETED' AND NOT EXISTS (
                   SELECT 1 FROM stock_journals j
                    WHERE j.source_type = 'production_run' AND j.source_id = r.id AND j.kind = 'RUN_COMPLETION')
            """
        )
    ).all()
    return [
        {"organization_id": str(o), "run_no": n, "item_id": i, "wip_qty": str(q), "wip_value": str(v)}
        for o, n, i, q, v in rows
    ]


def mass_balance_gaps(session: Session) -> list[dict[str, str]]:
    """Completed runs with an unexplained mass gap (law 3 is reported, not failed: the gap is shown, never hidden)."""
    out = []
    for run_id, org, run_no in session.execute(
        select(ProductionRun.id, ProductionRun.organization_id, ProductionRun.run_no).where(
            ProductionRun.status == "COMPLETED"
        )
    ).all():
        balance = run_analysis(session, run_id).mass_balance
        if balance is not None and balance.unexplained_g != 0:
            out.append(
                {
                    "organization_id": str(org),
                    "run_no": run_no,
                    "unexplained_kg": str(normalise(balance.unexplained_g / 1000)),
                }
            )
    return out


# ---------- run costs (MP07, ADR-0014 decisions F1-F3) ----------


@dataclass(frozen=True)
class RunCostResult:
    run_cost_id: uuid.UUID
    journal_id: uuid.UUID
    replayed: bool


def _lot_states(session: Session, organization_id: uuid.UUID, run: ProductionRun) -> list[LotState]:
    """The run's pack lines in completion order, each with where its lot's units are now (under the item locks)."""
    ordered = _ordered(run, _pack_lines(session, run.id))
    units = catalog.units_for(session, {pack.fg_item_id for _, pack in ordered})
    for item_id in sorted({pack.fg_item_id for _, pack in ordered}, key=str):
        ledger.lock_item_stores(session, organization_id, item_id)
    states = []
    for pl, pack in ordered:
        positions: tuple[LotPosition, ...] = ()
        if pl.lot_id is not None:
            positions = tuple(
                LotPosition(code, q, v)
                for code, q, v in ledger.lot_positions(session, pack.fg_item_id, pl.lot_id)
                if q > 0
            )
        states.append(
            LotState(pl.id, pl.bulk_allocated_g, pack.fg_item_id, units[pack.fg_item_id].base_uom, pl.lot_id, positions)
        )
    return states


def record_run_cost(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    run_id: uuid.UUID,
    kind: str,
    amount: Decimal,
    incurred_on: date | None = None,
    idempotency_key: uuid.UUID | None = None,
) -> RunCostResult:
    """A direct run cost (labour, gas/power, other) on a COMPLETED run with PROVISIONAL costs. One savepoint: the
    run_costs row, a value-only COST_TRUE_UP journal that spreads it over the run's lots, and an audit row."""
    money = domain.check_run_cost(kind, amount)
    on = incurred_on or business_date()
    digest = idempotency.request_hash(
        {"op": "run_cost", "run_id": str(run_id), "kind": kind, "amount": money, "incurred_on": on.isoformat()}
    )
    try:
        with session.begin_nested():
            if idempotency_key is not None:
                stored = idempotency.claim(session, organization_id, idempotency_key, digest)
                if stored is not None:
                    body = _replayed_ids(stored, "run_cost_id")
                    return RunCostResult(uuid.UUID(body["run_cost_id"]), uuid.UUID(body["journal_id"]), replayed=True)
            run = _lock_run(session, run_id)
            _require_status(run, "COMPLETED", "take run costs (record them once the output is posted)")
            if run.cost_status != "PROVISIONAL":
                raise RunError("costs_final", f"run {run.run_no}'s costs are FINAL: no more run costs can be added")
            recipe = RecipeStd.from_snapshot(run.recipe_snapshot or {})
            plan = domain.plan_true_up(
                money, _lot_states(session, organization_id, run), bulk_item_id=recipe.bulk_item_id
            )
            cost_id = uuid.uuid4()
            posted = ledger.post(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                kind="COST_TRUE_UP",
                source_type="run_cost",
                source_id=cost_id,
                posting_date=on,
                lines=plan.lines,
            )
            session.execute(
                insert(RunCost).values(
                    id=cost_id,
                    organization_id=organization_id,
                    run_id=run_id,
                    kind=kind,
                    amount=money,
                    incurred_on=on,
                    journal_id=posted.journal_id,
                    created_by=actor_id,
                )
            )
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="run.cost",
                entity_type="run_cost",
                entity_id=cost_id,
                after={
                    "run_no": run.run_no,
                    "kind": kind,
                    "amount": money,
                    "incurred_on": on,
                    "journal_id": posted.journal_id,
                    "shares": {str(k): v for k, v in plan.share.items()},
                    "written_off": {str(k): v for k, v in plan.written_off.items() if v},
                },
            )
            if idempotency_key is not None:
                idempotency.complete(
                    session,
                    organization_id,
                    idempotency_key,
                    201,
                    {"run_cost_id": cost_id, "journal_id": posted.journal_id},
                )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return RunCostResult(cost_id, posted.journal_id, replayed=False)


def finalise_costs(
    session: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, run_id: uuid.UUID
) -> None:
    """PROVISIONAL -> FINAL (decision F3): the run takes no more run costs; its cost per unit is final."""
    run = _lock_run(session, run_id)
    _require_status(run, "COMPLETED", "have its costs finalised")
    if run.cost_status == "FINAL":
        raise RunError("costs_final", f"run {run.run_no}'s costs are already FINAL")
    total = session.execute(
        select(func.coalesce(func.sum(RunCost.amount), 0)).where(RunCost.run_id == run_id)
    ).scalar_one()
    try:
        with session.begin_nested():
            session.execute(update(ProductionRun).where(ProductionRun.id == run_id).values(cost_status="FINAL"))
            audit.record(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="run.cost.finalise",
                entity_type="production_run",
                entity_id=run_id,
                before={"cost_status": "PROVISIONAL"},
                after={"cost_status": "FINAL", "run_no": run.run_no, "conversion_total": Decimal(total)},
            )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    session.expire(run)


# ---------- what costing reads (MP07) ----------


def costing_facts(session: Session, run_id: uuid.UUID) -> RunCostingFacts:
    """Everything costing needs about a COMPLETED run, read from the run, its issues and its journals."""
    run = session.execute(select(ProductionRun).where(ProductionRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise NotFoundError("run_not_found", "unknown production run")
    if run.status != "COMPLETED" or run.recipe_snapshot is None:
        raise RunError("run_not_completed", f"run {run.run_no} is {run.status}: costing needs a completed run")
    completion = ledger.journal_for(session, "RUN_COMPLETION", "production_run", run_id)
    if completion is None:
        raise RunError("no_completion_journal", f"run {run.run_no} has no completion journal")

    moves: dict[uuid.UUID, list[IssueMove]] = defaultdict(list)
    for direction, journal_id, item_id, qty, value in session.execute(
        select(
            MaterialIssue.direction,
            MaterialIssue.journal_id,
            MaterialIssueLine.item_id,
            MaterialIssueLine.qty_base,
            MaterialIssueLine.value,
        )
        .join(MaterialIssue, MaterialIssue.id == MaterialIssueLine.issue_id)
        .where(MaterialIssue.run_id == run_id)
        .order_by(MaterialIssue.issue_no)
    ).all():
        moves[item_id].append(IssueMove(journal_id, direction, qty, value))
    completion_lines = ledger.journal_lines(session, completion)
    packaging: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
    for ln in completion_lines:
        if ln.location == "PACK_STORE":
            q, v = packaging.get(ln.item_id, (Decimal(0), Decimal(0)))
            packaging[ln.item_id] = (q - ln.qty_base, v - ln.value)
    ids = set(moves) | set(packaging)
    codes, units = catalog.codes_for(session, ids), catalog.units_for(session, ids)
    materials = []
    for item_id, item_moves in moves.items():
        sign = {"ISSUE": 1, "RETURN": -1}
        materials.append(
            MaterialFacts(
                item_id,
                codes[item_id],
                "INGREDIENT",
                units[item_id].base_uom,
                units[item_id].stock_uom,
                sum((sign[m.direction] * m.qty_base for m in item_moves), Decimal(0)),
                sum((sign[m.direction] * m.value for m in item_moves), Decimal(0)),
                tuple(item_moves),
            )
        )
    for item_id, (q, v) in packaging.items():
        materials.append(
            MaterialFacts(
                item_id,
                codes[item_id],
                "PACKAGING",
                units[item_id].base_uom,
                units[item_id].stock_uom,
                q,
                v,
                (IssueMove(completion, "ISSUE", q, v),),
            )
        )
    materials.sort(key=lambda m: (m.role, m.item_code))

    conversion = tuple(
        ConversionFacts(c.id, c.kind, c.amount, c.incurred_on, c.journal_id)
        for c in session.execute(select(RunCost).where(RunCost.run_id == run_id).order_by(RunCost.created_at)).scalars()
    )
    true_ups = [c.journal_id for c in conversion if c.journal_id is not None]
    written_off = sum(
        (
            ln.value
            for j in (completion, *true_ups)
            for ln in ledger.journal_lines(session, j)
            if ln.location == "SCRAP"
        ),
        Decimal(0),
    )
    packs = []
    for pl, pack in _ordered(run, _pack_lines(session, run_id)):
        held = [] if pl.lot_id is None else ledger.lot_positions(session, pack.fg_item_id, pl.lot_id)
        held = [(c, q, v) for c, q, v in held if q > 0]
        packs.append(
            PackFacts(
                pack_line_id=pl.id,
                pack=pack,
                bulk_allocated_g=pl.bulk_allocated_g,
                good_units=pl.good_units or 0,
                used={uuid.UUID(k): Decimal(v) for k, v in (pl.packaging_actual or {}).items()},
                damaged={uuid.UUID(k): Decimal(v) for k, v in (pl.damage or {}).items()},
                lot_id=pl.lot_id,
                lot_no=None if pl.lot_id is None else ledger.lot_no(session, pl.lot_id),
                lot_qty=sum((q for _, q, _ in held), Decimal(0)),
                lot_value=sum((v for _, _, v in held), Decimal(0)),
            )
        )
    return RunCostingFacts(
        run_id=run.id,
        run_no=run.run_no,
        cost_status=run.cost_status,
        run_date=run.run_date,
        batch_multiplier=run.batch_multiplier,
        recipe=RecipeStd.from_snapshot(run.recipe_snapshot),
        packs=tuple(packs),
        materials=tuple(materials),
        conversion=conversion,
        completion_journal_id=completion,
        written_off=written_off,
    )


def run_value_mismatches(session: Session) -> list[dict[str, str]]:
    """Law 2 per run (make integrity): for every COMPLETED run, the value its completion and true-ups put into its
    lots and into SCRAP = its net material issues + the packaging its completion took + its run costs. Read from the
    material issue lines, run_costs and the journals' lines, so a dispatch (which only moves lot value) never
    matters. Empty means law 2 holds per run (sees all organizations as the owner)."""
    rows = session.execute(
        text(
            """
            WITH done AS (
              SELECT r.id, r.organization_id, r.run_no, j.id AS completion
                FROM production_runs r
                JOIN stock_journals j ON j.source_type = 'production_run' AND j.source_id = r.id
                                     AND j.kind = 'RUN_COMPLETION'
               WHERE r.status = 'COMPLETED'
            ), issued AS (
              SELECT mi.run_id, sum(CASE mi.direction WHEN 'ISSUE' THEN l.value ELSE -l.value END) AS v
                FROM material_issues mi JOIN material_issue_lines l ON l.issue_id = mi.id GROUP BY mi.run_id
            ), costs AS (
              SELECT run_id, sum(amount) AS v FROM run_costs GROUP BY run_id
            ), packaging AS (
              SELECT d.id AS run_id, -sum(sl.value) AS v
                FROM done d JOIN stock_lines sl ON sl.journal_id = d.completion
                JOIN locations l ON l.id = sl.location_id AND l.code = 'PACK_STORE' GROUP BY d.id
            ), output AS (
              SELECT d.id AS run_id, sum(sl.value) AS v
                FROM done d
                JOIN stock_journals j ON j.id = d.completion
                     OR (j.kind = 'COST_TRUE_UP' AND j.id IN (SELECT journal_id FROM run_costs WHERE run_id = d.id))
                JOIN stock_lines sl ON sl.journal_id = j.id
                JOIN locations l ON l.id = sl.location_id
               WHERE (j.kind = 'RUN_COMPLETION' AND l.code IN ('FG_STORE', 'SCRAP'))
                  OR (j.kind = 'COST_TRUE_UP' AND l.code <> 'CONVERSION_COST')
               GROUP BY d.id
            )
            SELECT d.organization_id, d.run_no,
                   coalesce(i.v, 0) + coalesce(p.v, 0) + coalesce(c.v, 0) AS inputs, coalesce(o.v, 0) AS outputs
              FROM done d
              LEFT JOIN issued i ON i.run_id = d.id
              LEFT JOIN packaging p ON p.run_id = d.id
              LEFT JOIN costs c ON c.run_id = d.id
              LEFT JOIN output o ON o.run_id = d.id
             WHERE coalesce(i.v, 0) + coalesce(p.v, 0) + coalesce(c.v, 0) <> coalesce(o.v, 0)
            """
        )
    ).all()
    return [
        {"organization_id": str(o), "run_no": n, "materials_and_costs": str(i), "into_lots_and_scrap": str(v)}
        for o, n, i, v in rows
    ]


def next_batch_for(session: Session, fg_item_id: uuid.UUID) -> dict[str, Any] | None:
    """The earliest batch not yet completed (DRAFT or IN_PROGRESS) that will pack this finished good, with its
    planned packets (expected units of its pack lines for the item). None if no batch is planned. MP12 replaces this
    stub with the batch planner."""
    versions = recipes.pack_spec_versions_for(session, fg_item_id)
    if not versions:
        return None
    row = session.execute(
        select(
            ProductionRun.id,
            ProductionRun.run_no,
            ProductionRun.run_date,
            ProductionRun.status,
            func.sum(RunPackLine.expected_units),
        )
        .join(RunPackLine, RunPackLine.run_id == ProductionRun.id)
        .where(ProductionRun.status.in_(("DRAFT", "IN_PROGRESS")), RunPackLine.pack_spec_version_id.in_(versions))
        .group_by(ProductionRun.id, ProductionRun.run_no, ProductionRun.run_date, ProductionRun.status)
        .order_by(ProductionRun.run_date, ProductionRun.run_no)
        .limit(1)
    ).one_or_none()
    if row is None:
        return None
    run_id, run_no, run_date, status, planned = row
    return {
        "run_id": str(run_id),
        "run_no": run_no,
        "run_date": run_date.isoformat(),
        "status": status,
        "planned_packets": str(int(planned)),
    }
