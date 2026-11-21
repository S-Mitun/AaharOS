"""Costing against PostgreSQL (MP07): run costs as value-only true-ups in NIT's order (100 sold first: 3,114.36 sold
+ 2,740.64 on hand), cost status, idempotency, append-only cards, sensitivity as of the issue, a mixed split with a
burnt line (law 2 per run), and the API."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.oracle import load_oracle
from app.modules.costing import service as costing
from app.modules.ledger import service as ledger
from app.modules.ledger.domain import LineSpec
from app.modules.procurement import service as procurement
from app.modules.procurement.domain import ReceiptLineIn
from app.modules.production import service as production
from app.modules.valuation import service as valuation
from tests.db.conftest import BACKEND, Tenant, add_member, login_client, sqlstate
from tests.db.test_production import P200, P500, complete_200, issue, pack_lines, section5, started_run, stock

D = Decimal
DAY = date(2026, 11, 21)


@pytest.fixture(scope="module")
def oracle() -> dict[str, Any]:
    return load_oracle(BACKEND.parent / "benchmark" / "expected_results.yaml")


def _buy(s: Session, s5: Any, item: str, qty: str, rate: str, unit: str = "kg") -> None:
    procurement.post_receipt(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        supplier_id=s5.supplier_id,
        supplier_invoice_ref=f"DEMO-{uuid.uuid4().hex[:6]}",
        received_on=DAY,
        lines=[ReceiptLineIn(s5.item_ids[item], D(qty), unit, D(rate))],
    )


def _cost(s: Session, s5: Any, run: uuid.UUID, kind: str, amount: str, **kw: Any) -> production.RunCostResult:
    return production.record_run_cost(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        run_id=run,
        kind=kind,
        amount=D(amount),
        incurred_on=DAY,
        **kw,
    )


def _nit_run(s: Session, s5: Any) -> uuid.UUID:
    _buy(s, s5, "flour", "60", "45.00")  # step 1, so flour issues at 43.125/kg = 1,725.00
    run = started_run(s, s5)
    issue(s, s5, run)
    complete_200(s, s5, run)
    return run


def _dispatch(s: Session, s5: Any, lot_no: str, qty: int) -> None:
    """A stand-in DISPATCH journal (MP10 builds the real dispatch): FG_STORE -> CUSTOMER at the lot's value."""
    item = s5.item_ids["murukku_200g"]
    lot = ledger.lot_id_by_no(s, item, lot_no)
    value = valuation.issue_value(
        s, organization_id=s5.organization_id, item_id=item, qty_base=D(qty), from_location="FG_STORE", lot_id=lot
    )
    ledger.post(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        kind="DISPATCH",
        source_type="dispatch",
        source_id=uuid.uuid4(),
        posting_date=DAY,
        lines=[
            LineSpec(item, "CUSTOMER", D(qty), "packet", value, lot),
            LineSpec(item, "FG_STORE", -D(qty), "packet", -value, lot),
        ],
    )


def _lot_values(s: Session, s5: Any, lot_no: str) -> dict[str, tuple[Decimal, Decimal]]:
    item = s5.item_ids["murukku_200g"]
    lot = ledger.lot_id_by_no(s, item, lot_no)
    assert lot is not None
    return {code: (q, v) for code, q, v in ledger.lot_positions(s, item, lot) if code in ("FG_STORE", "CUSTOMER")}


def test_run_costs_in_nit_order_after_a_sale(app_engine: Engine, oracle: dict[str, Any]) -> None:
    s, s5 = section5(app_engine, oracle, "C1")
    run = _nit_run(s, s5)
    _dispatch(s, s5, "B-001", 100)  # step 5 before step 8, as NIT orders them
    assert _lot_values(s, s5, "B-001")["CUSTOMER"] == (D(100), D("2156.91"))
    _cost(s, s5, run, "LABOUR", "1200.00")
    _cost(s, s5, run, "GAS_POWER", "600.00")
    s.commit()
    held = _lot_values(s, s5, "B-001")
    assert (held["CUSTOMER"][1], held["FG_STORE"][1]) == (D("3114.36"), D("2740.64"))  # ledger.md J8, assertion 22
    assert ledger.journal_imbalances(s) == [] and ledger.projection_diff(s) == []
    assert production.run_value_mismatches(s) == []

    _buy(s, s5, "flour", "100", "60.00")  # a later purchase must not change the as-of-issue sensitivity
    production.finalise_costs(s, organization_id=s5.organization_id, actor_id=None, run_id=run)
    s.commit()
    c = costing.run_costing(s, run)
    assert (c.cost.total.value, c.facts.cost_status) == (D("5855.00"), "FINAL")
    assert c.cost.to_json()["per_good_unit_display"] == "31.14"
    assert [c.sensitivity[m]["total"]["value"] for m in ("WAC", "FIFO", "LAST")] == ["5855.00", "5810.00", "5930.00"]
    assert c.sensitivity["LAST"]["book_value_used_for"] == ["carton_20", "cooking_oil", "pouch_200g", "spice_mix"]
    assert c.waterfall is not None and c.waterfall.total.value == D("431.20")
    assert c.facts.packs[0].lot_value == D("5855.00")  # the lot wherever it is: sold + on hand


def test_cost_refusals_and_status(factory: Any) -> None:
    s, s5 = factory
    run = started_run(s, s5)
    issue(s, s5, run)
    with pytest.raises(DomainError) as err:
        _cost(s, s5, run, "LABOUR", "100.00")  # IN_PROGRESS: record costs once the output is posted (F1)
    assert err.value.code == "bad_run_status"
    complete_200(s, s5, run)
    with pytest.raises(DomainError) as err:
        _cost(s, s5, run, "RENT", "100.00")
    assert err.value.code == "bad_cost_kind"
    key = uuid.uuid4()
    first = _cost(s, s5, run, "LABOUR", "1200.00", idempotency_key=key)
    again = _cost(s, s5, run, "LABOUR", "1200.00", idempotency_key=key)
    assert again.replayed and again.run_cost_id == first.run_cost_id
    production.finalise_costs(s, organization_id=s5.organization_id, actor_id=None, run_id=run)
    with pytest.raises(DomainError) as err:
        _cost(s, s5, run, "GAS_POWER", "600.00")
    assert err.value.code == "costs_final"
    with pytest.raises(DomainError) as err:
        production.finalise_costs(s, organization_id=s5.organization_id, actor_id=None, run_id=run)
    assert err.value.code == "costs_final"
    s.commit()
    assert stock(s)[("murukku_200g", "FG_STORE", "B-001")] == ("188", "5210.00")  # 4,010.00 + 1,200.00, one cost
    n = s.execute(text("SELECT count(*) FROM run_costs WHERE run_id = :r"), {"r": run}).scalar_one()
    assert n == 1


@pytest.fixture
def factory(app_engine: Engine, oracle: dict[str, Any]) -> Any:
    s, s5 = section5(app_engine, oracle, "C2")
    yield s, s5
    s.close()


def test_standard_cards_are_append_only(factory: Any, owner_engine: Engine) -> None:
    s, s5 = factory
    for stmt in ("UPDATE standard_cost_cards SET per_unit = 1", "DELETE FROM standard_cost_lines"):
        with pytest.raises(DBAPIError) as err:
            s.execute(text(stmt))
        assert sqlstate(err.value) == "42501"  # the app role holds SELECT and INSERT only
        s.rollback()
    with owner_engine.connect() as c, pytest.raises(DBAPIError) as err:
        c.execute(text("UPDATE standard_cost_cards SET per_unit = 1"))
    assert sqlstate(err.value) == "AH002"  # even the owner cannot revalue a card


def test_a_newer_card_does_not_revalue_an_older_run(factory: Any) -> None:
    s, s5 = factory
    run = started_run(s, s5)
    issue(s, s5, run)
    complete_200(s, s5, run)
    before = costing.run_costing(s, run).waterfall
    ids = s5.item_ids
    costing.create_card(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        pack_spec_version_id=s5.pack_versions[P200],
        effective_from=date(2026, 12, 1),
        rates={
            ids["flour"]: D(50),
            ids["cooking_oil"]: D(140),
            ids["spice_mix"]: D(200),
            ids["pouch_200g"]: D("2.5"),
            ids["carton_20"]: D(15),
        },  # fmt: skip
        conversion={"labour": D(1200), "gas_power": D(600)},
    )
    s.commit()
    assert [c["version"] for c in costing.list_cards(s)] == [1, 2]
    after = costing.run_costing(s, run).waterfall
    assert before is not None and after is not None and before.total.value == after.total.value
    assert before.standard.value == D("5423.80")


def test_mixed_split_costs_and_law_2(factory: Any) -> None:
    s, s5 = factory
    ids = s5.item_ids
    run = started_run(s, s5, packs=((P200, D(20_000)), (P500, D(20_000))))
    issue(s, s5, run)
    lines = {p.pack.code: p for p in pack_lines(s, run)}
    production.complete_run(
        s,
        organization_id=s5.organization_id,
        actor_id=None,
        run_id=run,
        posting_date=DAY,
        scrap_reason="DEMO batch burnt",
        results=[
            production.PackResultIn(
                lines[P200].pack_line_id,
                97,
                [
                    production.PackagingIn(ids["pouch_200g"], D(100), D(3)),
                    production.PackagingIn(ids["carton_20"], D(4)),
                ],
            ),
            production.PackResultIn(lines[P500].pack_line_id, 0, []),
        ],
    )
    _cost(s, s5, run, "LABOUR", "1000.01")
    s.commit()
    c = costing.run_costing(s, run)
    assert c.waterfall is None and c.waterfall_reason is not None and "card" in c.waterfall_reason  # no 500 g card
    assert c.cost.per_good_unit is None and len(c.cost.lots) == 1  # two pack lines: per-lot unit cost only
    assert c.cost.written_off == D("1695.00") + D("500.00")  # E4 at completion + the burnt line's half of 1,000.01
    lot = c.facts.packs[0] if c.facts.packs[0].pack.code == P200 else c.facts.packs[1]
    assert lot.lot_value == D("2005.00") + D("500.01")  # 1,000.01 split by bulk: the first share rounds up, the last
    assert production.run_value_mismatches(s) == []


def test_costs_through_the_api(api_app: Any, owner_engine: Engine, app_engine: Engine, oracle: dict[str, Any]) -> None:
    s, s5 = section5(app_engine, oracle, "CAPI")
    run = _nit_run(s, s5)
    s.commit()
    s.close()
    tenant = Tenant(org=s5.organization_id, items={}, locations={}, customer=uuid.uuid4())
    emails = {role: add_member(owner_engine, tenant, role)[1] for role in ("ADMIN", "AUDITOR", "PRODUCTION")}
    admin: TestClient = login_client(api_app, emails["ADMIN"])
    assert admin.post(f"/api/runs/{run}/costs", json={"kind": "LABOUR", "amount": 1200}).status_code == 422
    key = {"Idempotency-Key": str(uuid.uuid4())}
    body = {"kind": "LABOUR", "amount": "1200.00", "incurred_on": "2026-11-21"}
    first, again = (admin.post(f"/api/runs/{run}/costs", json=body, headers=key) for _ in range(2))
    assert (first.status_code, again.status_code) == (201, 200) and again.json()["replayed"]
    assert admin.post(f"/api/runs/{run}/costs", json={**body, "kind": "GAS_POWER", "amount": "600"}).status_code == 201
    assert admin.post(f"/api/runs/{run}/costs/finalise").json()["cost_status"] == "FINAL"

    auditor = login_client(api_app, emails["AUDITOR"])
    got = auditor.get(f"/api/runs/{run}/costing").json()
    assert (got["cost"]["total"]["value"], got["cost"]["per_good_unit_display"]) == ("5855.00", "31.14")
    assert got["waterfall"]["total"]["value"] == "431.20" and got["waterfall"]["components"][0]["kind"] == "YIELD"
    assert got["sensitivity"]["FIFO"]["per_good_unit_display"] == "30.90"
    assert len(auditor.get("/api/standard-cost-cards").json()["cards"]) == 1

    floor = login_client(api_app, emails["PRODUCTION"])
    card = {
        "pack_spec_version_id": str(s5.pack_versions[P200]),
        "effective_from": "2027-01-01",
        "rates": [
            {"item_id": str(v), "rate": r}
            for v, r in zip(
                (s5.item_ids[k] for k in ("flour", "cooking_oil", "spice_mix", "pouch_200g", "carton_20")),
                ("43", "140", "200", "2.5", "15"),
                strict=True,
            )
        ],  # fmt: skip
        "conversion": [{"label": "labour", "amount": "1200"}, {"label": "gas_power", "amount": "600"}],
    }
    made = floor.post("/api/standard-cost-cards", json=card)
    assert made.status_code == 201, made.text
    assert (made.json()["version"], made.json()["per_unit_display"]) == (2, "29.05")  # (5,770 + 40) / 200
