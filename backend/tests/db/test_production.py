"""Production runs against PostgreSQL (MP06): the atomic completion (a failure at any write persists nothing),
version workflow and frozen snapshots, the 500 g pack from seed data with no code change, a mixed split with a
zero-good line (decision E4), idempotent issue and completion, returns at the run's own average, S6, and the API."""

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError
from app.core.oracle import load_oracle
from app.modules.audit.models import AuditLog
from app.modules.identity import service as identity
from app.modules.judge.replay import POSTING_DATE, Section5, post_section5_opening, setup_section5
from app.modules.ledger import service as ledger
from app.modules.ledger.models import Lot, StockJournal
from app.modules.procurement import service as procurement
from app.modules.procurement.domain import ReceiptLineIn
from app.modules.production import service as production
from app.modules.production.models import ProductionRun, RunPackLine
from app.modules.recipe import service as recipes
from app.modules.recipe.domain import RecipeLineIn
from app.modules.recipe.models import RecipeLine
from tests.db.conftest import BACKEND, Tenant, add_member, login_client, sqlstate

D = Decimal
P200, P500 = "MURUKKU-200G", "MURUKKU-500G"


@pytest.fixture(scope="module")
def oracle() -> dict[str, Any]:
    return load_oracle(BACKEND.parent / "benchmark" / "expected_results.yaml")


def section5(app_engine: Engine, oracle: dict[str, Any], label: str = "P") -> tuple[Session, Section5]:
    """A fresh BENCHMARK tenant with the section 5 master data, the BOM and the valued opening stock."""
    s = Session(app_engine, expire_on_commit=False)
    org = identity.create_scratch_tenant(s, kind="BENCHMARK", label=label)
    s5 = setup_section5(s, oracle, org)
    post_section5_opening(s, oracle, s5)
    s.commit()
    return s, s5


@pytest.fixture
def factory(app_engine: Engine, oracle: dict[str, Any]) -> Iterator[tuple[Session, Section5]]:
    s, s5 = section5(app_engine, oracle)
    yield s, s5
    s.close()


def started_run(
    s: Session,
    s5: Section5,
    packs: tuple[tuple[str, Decimal | None], ...] = ((P200, None),),
    multiplier: Decimal = Decimal(1),
    run_date: date = POSTING_DATE,
) -> uuid.UUID:
    run = production.create_run(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        recipe_version_id=s5.recipe_version_id,
        batch_multiplier=multiplier,
        run_date=run_date,
        pack_lines=[production.PackLineRequest(s5.pack_versions[code], alloc) for code, alloc in packs],
    )
    production.start_run(s, organization_id=s5.organization_id, actor_id=None, run_id=run)
    return run


def issue(
    s: Session, s5: Section5, run: uuid.UUID, flour: str = "40", oil: str = "10.5", spice: str = "1.2", **kw: Any
) -> production.IssueResult:
    ids = s5.item_ids
    return production.issue_materials(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        run_id=run,
        posting_date=POSTING_DATE,
        lines=[
            production.MaterialLineIn(ids["flour"], D(flour), "kg"),
            production.MaterialLineIn(ids["cooking_oil"], D(oil), "L"),
            production.MaterialLineIn(ids["spice_mix"], D(spice), "kg"),
        ],
        **kw,
    )


def pack_lines(s: Session, run: uuid.UUID) -> list[production.PackLineAnalysis]:
    return list(production.run_analysis(s, run).pack_lines)


def complete_200(
    s: Session, s5: Section5, run: uuid.UUID, good: int = 188, damaged: int = 6, cartons: int = 9, **kw: Any
) -> production.CompletionResult:
    ids = s5.item_ids
    line = pack_lines(s, run)[0].pack_line_id
    return production.complete_run(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        run_id=run,
        posting_date=POSTING_DATE,
        results=[
            production.PackResultIn(
                line,
                good,
                [
                    production.PackagingIn(ids["pouch_200g"], D(good + damaged), D(damaged)),
                    production.PackagingIn(ids["carton_20"], D(cartons)),
                ],
            )
        ],
        **kw,
    )


def stock(s: Session) -> dict[tuple[str, str, str | None], tuple[str, str]]:
    return {(r["item_code"], r["location"], r["lot_no"]): (r["qty"], r["value"]) for r in ledger.balances(s)}


# ---------- the NIT run ----------


def test_nit_run_lot_wip_and_analysis(factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    run = started_run(s, s5)
    issue(s, s5, run)
    done = complete_200(s, s5, run)
    s.commit()
    held = stock(s)
    # no purchase in this tenant, so flour issues at the opening 42.00/kg: 4,055.00 - 45.00 (replay: test_replay.py)
    assert held[("murukku_200g", "FG_STORE", "B-001")] == ("188", "4010.00")
    assert ("flour", "WIP", None) not in held or held[("flour", "WIP", None)] == ("0", "0.00")
    lot = s.execute(select(Lot).where(Lot.id == done.lot_ids[pack_lines(s, run)[0].pack_line_id])).scalar_one()
    assert (lot.lot_no, lot.mfg_date, lot.best_before) == ("B-001", POSTING_DATE, date(2027, 2, 19))  # +90 days
    assert production.completed_run_wip_mismatches(s) == []
    assert ledger.journal_imbalances(s) == [] and ledger.projection_diff(s) == []
    from app.cli import integrity

    ok, report = integrity.run(s)
    assert ok and any(line.startswith("PASS  S6") for line in report)
    assert production.mass_balance_gaps(s)[0]["unexplained_kg"] == "2.4"

    body = production.get_run(s, run)
    assert body["status"] == "COMPLETED" and body["issues"][0]["issue_no"] == "MI/26-27/000001"
    a = body["analysis"]
    assert a["mass_balance"]["unexplained_gap"] == "2.4"
    assert sorted(a["flags"]) == ["cooking_oil 5.00%", "pouch_200g 3.19%", "yield MURUKKU-200G -6.00%"]
    line = a["pack_lines"][0]
    assert (line["lot_no"], line["packing"]["full_cartons"], line["packing"]["loose_units"]) == ("B-001", 9, 8)
    assert _no_floats(body)  # decimals are strings, never JSON numbers
    actions = set(s.execute(select(AuditLog.action).where(AuditLog.entity_id == run)).scalars())
    assert {"run.create", "run.start", "run.complete"} <= actions


def _no_floats(node: Any) -> bool:
    if isinstance(node, dict):
        return all(_no_floats(v) for v in node.values())
    if isinstance(node, list):
        return all(_no_floats(v) for v in node)
    return not isinstance(node, float | Decimal)


# ---------- atomicity: a failure at any write of a completion persists nothing ----------


class InjectedFailure(Exception):
    pass


class FailAtWrite:
    """Raises before the n-th INSERT/UPDATE/DELETE sent to PostgreSQL (n = 0 only counts)."""

    def __init__(self, n: int) -> None:
        self.n, self.count = n, 0

    def __call__(self, _conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            self.count += 1
            if self.count == self.n:
                raise InjectedFailure(f"injected failure at write {self.n}")


def _completion_trace(s: Session, run: uuid.UUID) -> dict[str, Any]:
    return {
        "status": s.execute(select(ProductionRun.status).where(ProductionRun.id == run)).scalar_one(),
        "journals": s.execute(
            select(func.count()).select_from(StockJournal).where(StockJournal.source_id == run)
        ).scalar_one(),
        "lots": s.execute(select(func.count()).select_from(Lot).where(Lot.source_id == run)).scalar_one(),
        "pack_lines": s.execute(
            select(RunPackLine.good_units, RunPackLine.lot_id, RunPackLine.packaging_actual).where(
                RunPackLine.run_id == run
            )
        ).all(),
        "audit": s.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_id == run, AuditLog.action == "run.complete")
        ).scalar_one(),
        "samples": s.execute(
            text("SELECT count(*) FROM fill_weight_samples WHERE run_id = :r"), {"r": run}
        ).scalar_one(),
        "oil": s.execute(text("SELECT count(*) FROM oil_sessions WHERE run_id = :r"), {"r": run}).scalar_one(),
    }


def _small_run(s: Session, s5: Section5) -> uuid.UUID:
    run = started_run(s, s5, multiplier=D("0.025"))  # 1 kg flour -> 5 expected packets
    issue(s, s5, run, flour="1", oil="0.25", spice="0.03")
    s.commit()
    return run


def _complete_small(s: Session, s5: Section5, run: uuid.UUID, key: uuid.UUID | None = None) -> None:
    ids = s5.item_ids
    production.complete_run(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        run_id=run,
        posting_date=POSTING_DATE,
        results=[
            production.PackResultIn(
                pack_lines(s, run)[0].pack_line_id,
                4,
                [production.PackagingIn(ids["pouch_200g"], D(5), D(1))],
            )
        ],
        scrap_g=D(50),
        scrap_reason="DEMO broken pieces",
        samples=[production.SampleIn(D(212), D(202)), production.SampleIn(D(211), D(201))],
        oil=production.OilIn(D(250), D(25), D(10), D(18)),
        idempotency_key=key,
    )


def _inject(app_engine: Engine, s: Session, s5: Section5, run: uuid.UUID, n: int) -> FailAtWrite:
    before = stock(s)
    trace = _completion_trace(s, run)
    hook = FailAtWrite(n)
    event.listen(app_engine, "before_cursor_execute", hook)
    try:
        with pytest.raises(InjectedFailure):
            _complete_small(s, s5, run, key=uuid.uuid4())
    finally:
        event.remove(app_engine, "before_cursor_execute", hook)
    assert _completion_trace(s, run) == trace  # the savepoint rolled back; the caller's transaction is still usable
    s.rollback()
    assert _completion_trace(s, run) == trace and stock(s) == before
    return hook


def test_failure_at_the_third_write_persists_nothing(app_engine: Engine, factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    run = _small_run(s, s5)
    hook = _inject(app_engine, s, s5, run, 3)
    assert hook.count == 3
    _complete_small(s, s5, run)  # nothing left behind blocks a clean retry
    s.commit()
    assert _completion_trace(s, run)["status"] == "COMPLETED"


def test_failure_at_any_write_persists_nothing(app_engine: Engine, factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    probe = _small_run(s, s5)
    counter = FailAtWrite(0)
    event.listen(app_engine, "before_cursor_execute", counter)
    try:
        _complete_small(s, s5, probe, key=uuid.uuid4())
    finally:
        event.remove(app_engine, "before_cursor_execute", counter)
    s.commit()
    writes = counter.count
    assert writes >= 15, "a completion writes the lot, the journal, its lines, the run rows and audit rows"
    for n in range(1, writes + 1):
        _inject(app_engine, s, s5, _small_run(s, s5), n)


# ---------- versions and frozen snapshots ----------


def test_versions_activate_retire_and_freeze(factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    org, ids = s5.organization_id, s5.item_ids
    old_run = started_run(s, s5)
    s.commit()
    recipe_id = uuid.UUID(recipes.recipe_snapshot(s, s5.recipe_version_id)["recipe_id"])
    v2 = recipes.create_recipe_version(
        s,
        organization_id=org,
        actor_id=None,
        recipe_id=recipe_id,
        bulk_yield_g=D(40_000),
        effective_from=POSTING_DATE,
        lines=[RecipeLineIn(ids["flour"], D(41), "kg"), RecipeLineIn(ids["cooking_oil"], D(10), "L")],
    )
    with pytest.raises(DomainError, match="not ACTIVE"):  # a DRAFT version cannot start a run
        production.create_run(
            s,
            organization_id=org,
            actor_id=None,
            recipe_version_id=v2,
            batch_multiplier=D(1),
            run_date=POSTING_DATE,
            pack_lines=[production.PackLineRequest(s5.pack_versions[P200])],
        )
    assert recipes.activate_recipe_version(s, organization_id=org, actor_id=None, version_id=v2) == s5.recipe_version_id
    s.commit()
    assert recipes.version_status(s, recipe_version_id=s5.recipe_version_id) == "RETIRED"
    with pytest.raises(DomainError, match="RETIRED"):
        started_run(s, s5)
    s.rollback()

    # the run started on v1 keeps its frozen standard
    snap = production.run_analysis(s, old_run)
    assert snap.ingredient("flour").standard == 40 and snap.tolerance_pct == 3

    # used versions are immutable: the database refuses to change their lines or the run's snapshot
    for stmt in (
        update(RecipeLine).where(RecipeLine.recipe_version_id == s5.recipe_version_id).values(qty_base=D(1)),
        update(ProductionRun).where(ProductionRun.id == old_run).values(recipe_snapshot={}),
    ):
        with pytest.raises(DBAPIError) as err:
            s.execute(stmt)
        assert sqlstate(err.value) == "AH002"
        s.rollback()


# ---------- the 500 g pack: seed data only, no code change ----------


def test_a_500g_run_from_seed_data(factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    ids = s5.item_ids
    procurement.post_receipt(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        supplier_id=s5.supplier_id,
        supplier_invoice_ref="DEMO-500",
        received_on=POSTING_DATE,
        lines=[ReceiptLineIn(ids["pouch_500g"], D(100), "piece", D("4.00"))],
    )
    run = started_run(s, s5, packs=((P500, None),))
    issue(s, s5, run)
    line = pack_lines(s, run)[0]
    assert line.expected_units == 80
    production.complete_run(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        run_id=run,
        posting_date=POSTING_DATE,
        results=[
            production.PackResultIn(
                line.pack_line_id,
                78,
                [
                    production.PackagingIn(ids["pouch_500g"], D(80), D(2)),
                    production.PackagingIn(ids["carton_20"], D(7)),
                ],
            )
        ],
    )
    s.commit()
    a = production.run_analysis(s, run)
    pl = a.pack_lines[0]
    assert (
        pl.yield_variance is not None and pl.yield_variance.pct_display == D("-2.50") and not pl.yield_variance.flagged
    )
    assert (pl.packing.full_cartons, pl.packing.loose) == (7, 8)  # type: ignore[union-attr]
    assert pl.flexible("pouch_500g").standard == 78 and pl.flexible("carton_20").standard == D("7.8")
    assert stock(s)[("murukku_500g", "FG_STORE", "B-001")][0] == "78"
    assert a.mass_balance is not None and a.mass_balance.unexplained_g == D(1_000)  # 40 kg - 78 x 0.5 kg
    assert production.completed_run_wip_mismatches(s) == []


# ---------- a mixed split with a zero-good pack line (decision E4) ----------


def test_mixed_split_writes_a_burnt_line_off_to_scrap(factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    ids = s5.item_ids
    run = started_run(s, s5, packs=((P200, D(20_000)), (P500, D(20_000))))
    issue(s, s5, run)
    lines = {p.pack.code: p for p in pack_lines(s, run)}
    assert (lines[P200].expected_units, lines[P500].expected_units) == (D(100), D(40))
    results = [
        production.PackResultIn(
            lines[P200].pack_line_id,
            97,
            [production.PackagingIn(ids["pouch_200g"], D(100), D(3)), production.PackagingIn(ids["carton_20"], D(4))],
        ),
        production.PackResultIn(lines[P500].pack_line_id, 0, []),
    ]
    kw: dict[str, Any] = {"organization_id": s5.organization_id, "actor_id": None, "run_id": run, "results": results}
    with pytest.raises(DomainError) as err:
        production.complete_run(s, posting_date=POSTING_DATE, **kw)
    assert err.value.code == "scrap_reason_required"
    assert _completion_trace(s, run)["status"] == "IN_PROGRESS"
    done = production.complete_run(s, posting_date=POSTING_DATE, scrap_reason="DEMO batch burnt in the fryer", **kw)
    s.commit()
    assert set(done.lot_ids) == {lines[P200].pack_line_id}
    assert ledger.lot_no(s, done.lot_ids[lines[P200].pack_line_id]) == "B-001-A"
    journal = s.execute(text("SELECT id FROM stock_journals WHERE source_id = :r"), {"r": run}).scalar_one()
    scrap = s.execute(
        text(
            "SELECT i.code, sl.qty_base, sl.value FROM stock_lines sl JOIN items i ON i.id = sl.item_id"
            " JOIN locations l ON l.id = sl.location_id WHERE sl.journal_id = :j AND l.code = 'SCRAP' ORDER BY i.code"
        ),
        {"j": journal},
    ).all()
    assert [(c, q, v) for c, q, v in scrap] == [("murukku_bulk", D(20_000), D("1695.00")), ("pouch_200g", D(3), D(0))]
    fg = stock(s)[("murukku_200g", "FG_STORE", "B-001-A")]
    # half the ingredients (flour at the opening 42.00/kg: 3,390.00 / 2) + its own pouches and cartons
    assert fg == ("97", str(D("1695.00") + D("250.00") + D("60.00")))
    assert production.completed_run_wip_mismatches(s) == []


# ---------- idempotency and returns ----------


def test_issue_and_completion_are_idempotent(factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    run = started_run(s, s5)
    s.commit()
    key = uuid.uuid4()
    first = issue(s, s5, run, idempotency_key=key)
    again = issue(s, s5, run, idempotency_key=key)
    assert again.replayed and (again.issue_id, again.journal_id) == (first.issue_id, first.journal_id)
    with pytest.raises(ConflictError):
        issue(s, s5, run, flour="39", idempotency_key=key)  # same key, different issue: refused, nothing posted
    s.commit()
    assert production.net_issued(s, run)[s5.item_ids["flour"]] == (D(40_000), D("1680.00"))
    done_key = uuid.uuid4()
    done = complete_200(s, s5, run, idempotency_key=done_key)
    replay = complete_200(s, s5, run, idempotency_key=done_key)
    assert replay.replayed and replay.journal_id == done.journal_id and replay.lot_ids == done.lot_ids
    s.commit()
    assert stock(s)[("murukku_200g", "FG_STORE", "B-001")] == ("188", "4010.00")
    with pytest.raises(DomainError, match="COMPLETED"):
        complete_200(s, s5, run)


def test_a_return_comes_back_at_the_runs_own_average(factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    ids = s5.item_ids
    run_a = started_run(s, s5)
    issue(s, s5, run_a, flour="10", oil="1", spice="0.1")  # flour at the opening 42.00/kg -> 420.00
    procurement.post_receipt(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        supplier_id=s5.supplier_id,
        supplier_invoice_ref="DEMO-DEAR",
        received_on=POSTING_DATE,
        lines=[ReceiptLineIn(ids["flour"], D(90), "kg", D("60.00"))],  # pool 180 kg / 9,180.00 -> 51.00/kg
    )
    run_b = started_run(s, s5)
    issue(s, s5, run_b, flour="10", oil="1", spice="0.1")  # 510.00
    ret = production.issue_materials(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        run_id=run_a,
        direction="RETURN",
        posting_date=POSTING_DATE,
        lines=[production.MaterialLineIn(ids["flour"], D(5), "kg")],
    )
    s.commit()
    assert ret.issue_no == "MI/26-27/000003"
    assert production.net_issued(s, run_a)[ids["flour"]] == (D(5_000), D("210.00"))  # A's own average, not WIP's 232.50
    assert stock(s)[("flour", "WIP", None)] == ("15", "720.00")
    with pytest.raises(DomainError) as err:
        production.issue_materials(
            s,
            organization_id=s5.organization_id,
            actor_id=None,
            run_id=run_a,
            direction="RETURN",
            lines=[production.MaterialLineIn(ids["flour"], D(6), "kg")],
        )
    assert err.value.code == "return_exceeds_issued"


def test_refusals(factory: tuple[Session, Section5]) -> None:
    s, s5 = factory
    org, ids = s5.organization_id, s5.item_ids
    with pytest.raises(DomainError) as err:
        started_run(s, s5, packs=((P200, D(30_000)), (P500, D(10_001))))
    assert err.value.code == "over_allocated"
    with pytest.raises(DomainError) as err:
        started_run(s, s5, run_date=date(2026, 1, 1))  # before the tolerance setting is in force
    assert err.value.code == "no_tolerance_configured"
    s.rollback()
    draft = production.create_run(
        s,
        organization_id=org,
        actor_id=None,
        recipe_version_id=s5.recipe_version_id,
        batch_multiplier=D(1),
        run_date=POSTING_DATE,
        pack_lines=[production.PackLineRequest(s5.pack_versions[P200])],
    )
    with pytest.raises(DomainError, match="IN_PROGRESS"):
        issue(s, s5, draft)
    run = started_run(s, s5)
    with pytest.raises(DomainError) as err:
        production.issue_materials(
            s,
            organization_id=org,
            actor_id=None,
            run_id=run,
            lines=[production.MaterialLineIn(ids["pouch_200g"], D(1), "piece")],
        )
    assert err.value.code == "not_raw_material"
    with pytest.raises(DomainError) as err:
        complete_200(s, s5, run)
    assert err.value.code == "nothing_issued"
    issue(s, s5, run)
    line = pack_lines(s, run)[0].pack_line_id
    with pytest.raises(DomainError) as err:
        production.complete_run(
            s,
            organization_id=org,
            actor_id=None,
            run_id=run,
            results=[production.PackResultIn(line, 10, [production.PackagingIn(ids["pouch_500g"], D(10))])],
        )
    assert err.value.code == "not_in_pack_spec"
    with pytest.raises(DomainError) as err:
        complete_200(s, s5, run, good=600)  # more pouches than the store holds
    assert err.value.code == "pool_short"
    assert err.value.message.startswith("Not enough ") and "piece available" in err.value.message  # words, not 6 dp
    assert _completion_trace(s, run)["status"] == "IN_PROGRESS"


# ---------- the API ----------


def test_run_through_the_api(api_app: Any, owner_engine: Engine, app_engine: Engine, oracle: dict[str, Any]) -> None:
    s, s5 = section5(app_engine, oracle, "API")
    s.close()
    tenant = Tenant(org=s5.organization_id, items={}, locations={}, customer=uuid.uuid4())
    emails = {role: add_member(owner_engine, tenant, role)[1] for role in ("PRODUCTION", "AUDITOR", "ADMIN")}
    floor: TestClient = login_client(api_app, emails["PRODUCTION"])
    ids = {k: str(v) for k, v in s5.item_ids.items()}

    r = floor.post(
        "/api/runs",
        json={
            "recipe_version_id": str(s5.recipe_version_id),
            "run_date": "2026-11-21",
            "pack_lines": [{"pack_spec_version_id": str(s5.pack_versions[P200])}],
        },
    )
    assert r.status_code == 201, r.text
    run = r.json()
    assert (run["run_no"], run["status"], run["pack_lines"][0]["expected_units"]) == ("B-001", "DRAFT", "200")
    assert floor.post(f"/api/runs/{run['id']}/start").json()["status"] == "IN_PROGRESS"

    numeric = {"lines": [{"item_id": ids["flour"], "qty": 40, "unit": "kg"}]}
    assert floor.post(f"/api/runs/{run['id']}/issues", json=numeric).status_code == 422  # a JSON number is refused
    key = {"Idempotency-Key": str(uuid.uuid4())}
    body = {
        "posting_date": "2026-11-21",
        "lines": [
            {"item_id": ids["flour"], "qty": "40", "unit": "kg"},
            {"item_id": ids["cooking_oil"], "qty": "10.5", "unit": "L"},
            {"item_id": ids["spice_mix"], "qty": "1.2", "unit": "kg"},
        ],
    }
    first = floor.post(f"/api/runs/{run['id']}/issues", json=body, headers=key)
    again = floor.post(f"/api/runs/{run['id']}/issues", json=body, headers=key)
    assert (first.status_code, again.status_code) == (201, 200) and again.json()["replayed"]
    assert first.json()["issue_no"] == again.json()["issue_no"] == "MI/26-27/000001"

    line = first.json()["run"]["analysis"]["pack_lines"][0]["pack_line_id"]
    complete = {
        "posting_date": "2026-11-21",
        "pack_lines": [
            {
                "pack_line_id": line,
                "good_units": "188",
                "packaging": [
                    {"item_id": ids["pouch_200g"], "used": "194", "damaged": "6"},
                    {"item_id": ids["carton_20"], "used": "9"},
                ],
            }
        ],
        "oil_session": {"fresh_ml": "10500", "topup_ml": "500", "tpc_pct": "19.5"},
    }
    admin = login_client(api_app, emails["ADMIN"])
    assert admin.post(f"/api/runs/{run['id']}/complete", json=complete).status_code == 403  # ADMIN cannot complete runs
    done = floor.post(f"/api/runs/{run['id']}/complete", json=complete)
    assert done.status_code == 201, done.text

    auditor = login_client(api_app, emails["AUDITOR"])
    got = auditor.get(f"/api/runs/{run['id']}").json()
    assert got["status"] == "COMPLETED" and got["oil_sessions"][0]["tpc_pct"] == "19.5"
    oil = next(v for v in got["analysis"]["ingredients"] if v["label"] == "cooking_oil")
    assert (oil["variance_pct"], oil["flagged"], oil["explained"]["unit"]) == ("5.00", True, "%")
    assert [r["run_no"] for r in auditor.get("/api/runs").json()["runs"]] == ["B-001"]
    recipes_list = auditor.get("/api/recipes").json()["recipes"]
    assert recipes_list[0]["versions"][0]["status"] == "ACTIVE"
    assert {p["code"] for p in auditor.get("/api/pack-specs").json()["pack_specs"]} == {P200, P500}
