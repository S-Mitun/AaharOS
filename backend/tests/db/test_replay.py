"""The valued benchmark replay against PostgreSQL (MP05). Every figure must equal docs/architecture/ledger.md, which
was replayed by hand with Decimal in MP01. These values are checked here, not as benchmark rows: the rows that own
them (17-22) belong to MP06/MP07/MP10."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core.db import org_scope
from app.core.oracle import load_oracle
from app.modules.judge.replay import replay_stock
from app.modules.ledger import service as ledger
from app.modules.procurement import service as procurement
from tests.db.conftest import BACKEND

D = Decimal


@pytest.fixture(scope="module")
def replay(app_engine: Engine) -> Any:
    oracle = load_oracle(BACKEND.parent / "benchmark" / "expected_results.yaml")
    with Session(app_engine, expire_on_commit=False) as s:
        return replay_stock(s, oracle)


def test_closing_values_equal_the_ledger_design(replay: Any) -> None:
    v = replay.closing_value
    assert v[("flour", "RAW_STORE")] == D("5175.00")
    assert v[("cooking_oil", "RAW_STORE")] == D("2730.00")
    assert v[("spice_mix", "RAW_STORE")] == D("760.00")
    assert v[("pouch_200g", "PACK_STORE")] == D("765.00")  # 1,250.00 - 485.00 (194 at 2.50)
    assert v[("carton_20", "PACK_STORE")] == D("315.00")  # 450.00 - 135.00
    assert v.get(("flour", "WIP"), D(0)) == 0 and replay.closing.get(("flour", "WIP"), D(0)) == 0
    assert v[("murukku_200g", "FG_STORE")] == D("1442.50") + D("5855.00")  # OPEN-LOT at standard + B-001 after J8
    assert replay.closing[("murukku_200g", "FG_STORE")] == 238


def test_lots_carry_their_own_value(replay: Any, app_engine: Engine) -> None:
    with Session(app_engine) as s:
        org_scope(s, replay.organization_id)
        rows = {
            r["lot_no"]: (r["qty"], r["value"]) for r in ledger.balances(s, item_id=replay.item_ids["murukku_200g"])
        }
    assert rows == {"OPEN-LOT": ("50", "1442.50"), "B-001": ("188", "5855.00")}  # materials 4,055 + run costs 1,800


def test_standard_cost_and_sensitivity(replay: Any) -> None:
    assert replay.standard.per_unit == D("28.850000")  # derived from the inputs (A1, A2), not copied
    s = replay.flour_issue_sensitivity
    assert (s["WAC"]["value"], s["FIFO"]["value"], s["LAST"]["value"]) == (D("1725.00"), D("1680.00"), D("1800.00"))
    assert [name for name, m in s.items() if m["posts"]] == ["WAC"]
    assert replay.receipt_no == "GRN/26-27/000001"
    assert replay.flour_wac_after_purchase.value == D("43.125000")


def test_integrity_holds_for_the_replay(replay: Any, app_engine: Engine) -> None:
    with Session(app_engine) as s:
        org_scope(s, replay.organization_id)
        assert ledger.journal_imbalances(s) == []
        assert ledger.projection_diff(s) == []
        assert procurement.receipt_value_mismatches(s) == []


def test_seed_demo_master_data_is_added_once(owner_engine: Engine, app_engine: Engine) -> None:
    from app.cli.seed_demo import ASSIGNMENTS, seed_master_data
    from app.modules.identity.models import SalesmanCustomerAssignment
    from tests.db.conftest import make_user

    org = uuid.uuid4()
    with owner_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO organizations (id, code, name, kind, state_code) VALUES (:i, :c, 'DEMO seed', 'SIM', '33')"
            ),
            {"i": org, "c": f"DEMO-SEED-{org.hex[:8]}"},
        )
    users = {email: make_user(owner_engine, "salesman") for email, _ in ASSIGNMENTS}
    with Session(app_engine, expire_on_commit=False) as s:
        assert seed_master_data(s, org, users) is True
        s.commit()
    with Session(app_engine, expire_on_commit=False) as s:
        assert seed_master_data(s, org, users) is False  # a second run leaves everything unchanged
        stock = {(r["item_code"], r["location"]): (r["qty"], r["value"]) for r in ledger.balances(s)}
        assigned = s.execute(select(SalesmanCustomerAssignment.user_id)).scalars().all()
    assert stock[("flour", "RAW_STORE")] == ("100", "4200.00")
    assert stock[("murukku_200g", "FG_STORE")] == ("50", "1442.50")
    assert sorted(assigned) == sorted(users.values())
