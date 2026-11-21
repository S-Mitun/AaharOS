"""Pure tests of the run-cost true-up (MP07, decisions F1, F2): ledger.md J8 in NIT's order, all on hand, two true-ups
equal to one, a zero-good line to SCRAP, and conservation as a property."""

import uuid
from collections import defaultdict
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.ledger.domain import LineSpec
from app.modules.production import domain
from app.modules.production.domain import LotPosition, LotState, RunError

D = Decimal
FG, BULK = uuid.uuid4(), uuid.uuid4()


FULL = D(40_000)


def _lot(positions: tuple[LotPosition, ...], alloc: Decimal = FULL, lot: bool = True) -> LotState:
    return LotState(uuid.uuid4(), alloc, FG, "piece", uuid.uuid4() if lot else None, positions)


def _deltas(lines: tuple[LineSpec, ...]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for ln in lines:
        assert ln.qty == 0  # value only: quantities are never touched
        out[ln.location] += ln.value
    return dict(out)


def _apply(lot: LotState, lines: tuple[LineSpec, ...]) -> LotState:
    d = _deltas(lines)
    return LotState(
        lot.pack_line_id,
        lot.bulk_allocated_g,
        lot.item_id,
        lot.base_uom,
        lot.lot_id,
        tuple(LotPosition(p.location, p.qty_base, p.value + d.get(p.location, D(0))) for p in lot.positions),
    )


def test_nit_j8_after_the_dispatch() -> None:
    """ledger.md J8: 100 of B-001 already sold at 2,156.91; labour + gas 1,800 arrive afterwards."""
    lot = _lot((LotPosition("CUSTOMER", D(100), D("2156.91")), LotPosition("FG_STORE", D(88), D("1898.09"))))
    plan = domain.plan_true_up(D("1800.00"), [lot], bulk_item_id=BULK)
    assert _deltas(plan.lines) == {"CUSTOMER": D("957.45"), "FG_STORE": D("842.55"), "CONVERSION_COST": D("-1800.00")}
    after = _apply(lot, plan.lines)
    assert {p.location: p.value for p in after.positions} == {"CUSTOMER": D("3114.36"), "FG_STORE": D("2740.64")}


def test_all_on_hand_goes_to_the_store() -> None:
    lot = _lot((LotPosition("FG_STORE", D(188), D("4055.00")),))
    plan = domain.plan_true_up(D("1800.00"), [lot], bulk_item_id=BULK)
    assert _deltas(plan.lines) == {"FG_STORE": D("1800.00"), "CONVERSION_COST": D("-1800.00")}


def test_two_true_ups_end_where_one_would() -> None:
    lot = _lot((LotPosition("CUSTOMER", D(100), D("2156.91")), LotPosition("FG_STORE", D(88), D("1898.09"))))
    once = _apply(lot, domain.plan_true_up(D("1800.00"), [lot], bulk_item_id=BULK).lines)
    labour = _apply(lot, domain.plan_true_up(D("1200.00"), [lot], bulk_item_id=BULK).lines)
    twice = _apply(labour, domain.plan_true_up(D("600.00"), [labour], bulk_item_id=BULK).lines)
    assert once.positions == twice.positions


def test_split_by_bulk_and_a_zero_good_line_goes_to_scrap() -> None:
    good = _lot((LotPosition("FG_STORE", D(97), D("2005.00")),), D(20_000))
    burnt = _lot((), D(20_000), lot=False)
    plan = domain.plan_true_up(D("1800.01"), [good, burnt], bulk_item_id=BULK)
    assert plan.share == {good.pack_line_id: D("900.01"), burnt.pack_line_id: D("900.00")}
    assert plan.written_off == {good.pack_line_id: 0, burnt.pack_line_id: D("900.00")}
    bulk = [ln for ln in plan.lines if ln.item_id == BULK]
    assert sorted((ln.location, ln.value) for ln in bulk) == [("CONVERSION_COST", D("-900.00")), ("SCRAP", D("900.00"))]


def test_run_cost_refusals() -> None:
    assert domain.check_run_cost("LABOUR", D("1200.00")) == D("1200.00")
    for kind, amount in (("RENT", D(1)), ("LABOUR", D(0)), ("LABOUR", D("1.005"))):
        with pytest.raises(RunError):
            domain.check_run_cost(kind, amount)


@given(
    st.decimals(min_value="0.01", max_value=100_000, places=2),
    st.lists(
        st.tuples(st.integers(min_value=0, max_value=300), st.integers(min_value=0, max_value=300)),
        min_size=1,
        max_size=3,
    ),
)
def test_true_up_conserves_value(amount: Decimal, lots: list[tuple[int, int]]) -> None:
    states = []
    for sold, on_hand in lots:
        held = tuple(
            p
            for p in (
                LotPosition("CUSTOMER", D(sold), D(sold) * 3),
                LotPosition("FG_STORE", D(on_hand), D(on_hand) * 3),
            )
            if p.qty_base > 0
        )
        states.append(_lot(held, D(10_000), lot=bool(held)))
    plan = domain.plan_true_up(amount, states, bulk_item_id=BULK)
    assert sum(ln.value for ln in plan.lines) == 0  # law 2: every rupee leaves CONVERSION_COST and lands somewhere
    assert sum(plan.share.values()) == amount
    for state in states:
        after = _apply(state, tuple(ln for ln in plan.lines if ln.lot_id == state.lot_id and state.lot_id))
        assert after.value == state.value + plan.share[state.pack_line_id] - plan.written_off[state.pack_line_id]
