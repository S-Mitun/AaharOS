"""Pure approval rules (MP09, ADR-0016): full or nothing, partial with backorder, the backorder, amendments down,
status changes, shortage and credit."""

import uuid
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import ConflictError
from app.core.explained import Explained
from app.modules.sales.domain import (
    LineState,
    OrderError,
    agreed_quantities,
    approval_plan,
    backorder_plan,
    credit_check,
    reduce_line,
    require_reason,
    require_status,
    shortage,
    shortage_explained,
    status_after,
    stock_explained,
)

D = Decimal
M200, M500 = uuid.uuid4(), uuid.uuid4()
A = LineState(1, M200, 150, 0, 0)
B = LineState(1, M200, 120, 0, 0)


def test_nit_retailer_a_full_approval() -> None:
    (d,) = approval_plan([A], agreed_quantities([A], {}), {M200: 238}, partial=False)
    assert (d.target, d.reserve, d.backorder) == (150, 150, 0)
    assert status_after([(d.reserve, d.backorder)]) == "APPROVED"


def test_nit_distributor_b_full_approval_refused_with_the_shortage() -> None:
    with pytest.raises(OrderError) as e:
        approval_plan([B], agreed_quantities([B], {}), {M200: 88}, partial=False)
    assert e.value.code == "insufficient_available"
    assert e.value.details["lines"] == [
        {"line_no": 1, "item_id": str(M200), "requested": 120, "available": 88, "shortage": 32}
    ]


def test_nit_distributor_b_partial_88_backorder_32() -> None:
    (d,) = approval_plan([B], agreed_quantities([B], {}), {M200: 88}, partial=True)
    assert (d.reserve, d.backorder) == (88, 32)
    assert status_after([(d.reserve, d.backorder)]) == "PART_APPROVED"


def test_partial_with_nothing_available_is_refused() -> None:
    with pytest.raises(OrderError) as e:
        approval_plan([B], agreed_quantities([B], {}), {M200: 0}, partial=True)
    assert e.value.code == "nothing_available"


def test_agreed_quantity_can_only_go_down() -> None:
    assert agreed_quantities([B], {1: 100}) == {1: 100}
    for bad in (121, -1):
        with pytest.raises(OrderError) as e:
            agreed_quantities([B], {1: bad})
        assert e.value.code == "bad_agreed_qty"
    with pytest.raises(OrderError) as e:
        agreed_quantities([B], {1: 0})
    assert e.value.code == "nothing_to_supply"
    with pytest.raises(OrderError) as e:
        agreed_quantities([B], {9: 1})
    assert e.value.code == "unknown_line"


def test_backorder_is_covered_when_stock_arrives() -> None:
    part = LineState(1, M200, 120, 88, 32)
    (d,) = backorder_plan([part], {M200: 200})
    assert (d.reserve, d.backorder) == (32, 0)
    (d2,) = backorder_plan([part], {M200: 10})
    assert (d2.reserve, d2.backorder) == (10, 22)
    with pytest.raises(OrderError):
        backorder_plan([part], {M200: 0})


def test_amending_down_shrinks_the_backorder_first() -> None:
    assert reduce_line(88, 32, 100) == (88, 12)
    assert reduce_line(88, 32, 50) == (50, 0)
    for bad in (120, 130):
        with pytest.raises(OrderError):
            reduce_line(88, 32, bad)


def test_status_rules() -> None:
    require_status("approve", "SUBMITTED")
    with pytest.raises(ConflictError) as e:
        require_status("approve", "APPROVED")
    assert e.value.code == "order_already_decided"
    with pytest.raises(ConflictError):
        require_status("cancel", "INVOICED")
    with pytest.raises(OrderError):
        require_reason("  ", "rejecting")
    assert require_reason(" no stock ", "rejecting") == "no stock"


def test_explained_stock_and_shortage() -> None:
    atp = stock_explained(238, 150)
    assert (atp.value, atp.formula) == (D(88), "on hand - reserved")
    assert shortage_explained(120, 88).value == D(32)
    assert shortage(120, 200) == 0 and shortage(10, -5) == 10


def test_credit_check() -> None:
    owed = Explained(D("0.00"), "INR", "no invoices yet")
    within = credit_check(D("100000.00"), owed, D("6000.00"))
    assert (within.over_limit, within.exposure.value) == (False, D("6000.00"))
    assert credit_check(D("5000.00"), owed, D("6000.00")).over_limit is True
    no_limit = credit_check(D(0), owed, D("6000.00"))
    assert (no_limit.limit, no_limit.over_limit) == (None, False)


lines_st = st.lists(st.tuples(st.integers(1, 500), st.integers(0, 600)), min_size=1, max_size=6)


@given(lines_st, st.booleans())
def test_never_reserves_above_available_or_beyond_the_request(rows: list[tuple[int, int]], partial: bool) -> None:
    items = [uuid.uuid4() for _ in rows]
    lines = [LineState(n + 1, items[n], req, 0, 0) for n, (req, _) in enumerate(rows)]
    available = {items[n]: avail for n, (_, avail) in enumerate(rows)}
    try:
        plan = approval_plan(lines, agreed_quantities(lines, {}), available, partial)
    except OrderError as e:
        assert e.code in {"insufficient_available", "nothing_available"}
        return
    for d, ln in zip(plan, lines, strict=True):
        assert 0 <= d.reserve <= available[ln.item_id]
        assert d.reserve + d.backorder == d.target <= ln.requested
        if not partial:
            assert d.backorder == 0
