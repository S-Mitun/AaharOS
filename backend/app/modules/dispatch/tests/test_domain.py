"""Pure dispatch rules (MP10): FEFO picking, lot value shares, chosen lots, the consignment value."""

import uuid
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.dispatch.domain import (
    DispatchError,
    LotAvailable,
    consignment_value,
    is_fefo,
    lot_share,
    pick_chosen,
    pick_fefo,
)

D = Decimal
OPEN = LotAvailable(uuid.uuid4(), "OPEN-LOT", 50, D("1442.50"))
B001 = LotAvailable(uuid.uuid4(), "B-001", 188, D("4055.00"))


def test_nit_dispatch_a() -> None:
    picks = pick_fefo([OPEN, B001], 150)
    assert [(p.lot_no, p.qty, p.value) for p in picks] == [("OPEN-LOT", 50, D("1442.50")), ("B-001", 100, D("2156.91"))]
    assert is_fefo([OPEN, B001], picks)


def test_the_last_packets_take_all_the_value() -> None:
    lot = LotAvailable(uuid.uuid4(), "L", 3, D("10.00"))
    first = lot_share(lot, 1)
    rest = lot_share(LotAvailable(lot.lot_id, "L", 2, lot.value - first), 2)
    assert (first, first + rest) == (D("3.33"), D("10.00"))


def test_not_enough_unexpired_stock() -> None:
    with pytest.raises(DispatchError) as e:
        pick_fefo([OPEN], 51)
    assert e.value.code == "insufficient_lot_stock"
    with pytest.raises(DispatchError):
        pick_fefo([OPEN], 0)


def test_chosen_lots() -> None:
    picks = pick_chosen([OPEN, B001], {B001.lot_id: 20}, 20, "customer asked for the fresh batch")
    assert [(p.lot_no, p.qty) for p in picks] == [("B-001", 20)]
    assert not is_fefo([OPEN, B001], picks)
    for chosen, qty, reason, code in (
        ({B001.lot_id: 20}, 20, "", "override_reason_required"),
        ({B001.lot_id: 20}, 21, "reason", "chosen_lots_mismatch"),
        ({uuid.uuid4(): 5}, 5, "reason", "lot_not_available"),
        ({OPEN.lot_id: 51}, 51, "reason", "lot_too_small"),
    ):
        with pytest.raises(DispatchError) as e:
            pick_chosen([OPEN, B001], chosen, qty, reason)
        assert e.value.code == code


def test_consignment_value_is_the_dispatched_share_with_tax() -> None:
    assert consignment_value([(150, D("7875.00"), 150)]) == D("7875.00")
    assert consignment_value([(150, D("7875.00"), 60)]) == D("3150.00")


@given(
    st.lists(
        st.tuples(st.integers(1, 500), st.decimals(min_value=0, max_value=50000, places=2)), min_size=1, max_size=6
    ),
    st.integers(1, 3000),
)
def test_picks_conserve_quantity_and_never_exceed_a_lot(rows: list[tuple[int, Decimal]], qty: int) -> None:
    lots = [LotAvailable(uuid.uuid4(), f"L{n}", q, v) for n, (q, v) in enumerate(rows)]
    if qty > sum(lot.qty for lot in lots):
        with pytest.raises(DispatchError):
            pick_fefo(lots, qty)
        return
    picks = pick_fefo(lots, qty)
    assert sum(p.qty for p in picks) == qty
    for p, lot in zip(picks, lots, strict=False):
        assert p.lot_id == lot.lot_id and 0 < p.qty <= lot.qty and 0 <= p.value <= lot.value
