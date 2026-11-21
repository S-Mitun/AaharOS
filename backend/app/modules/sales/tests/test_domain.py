"""Pure order-taking rules (MP08, ADR-0015): price resolution, the order plan, exact totals, staleness, the
request hash and SO numbers."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.idempotency import request_hash
from app.modules.sales.domain import (
    OrderError,
    OrderLineIn,
    PriceListVersion,
    check_new_price_list,
    is_stale,
    order_no,
    order_total,
    plan_order,
    price_list_in_force,
    request_doc,
)

D = Decimal
RET_A, DIST_B = uuid.uuid4(), uuid.uuid4()
M200, M500 = uuid.uuid4(), uuid.uuid4()
APR = date(2026, 4, 1)
DAY = date(2026, 11, 21)


def version(v: int, frm: date = APR, customer: uuid.UUID | None = None, to: date | None = None) -> PriceListVersion:
    return PriceListVersion(uuid.uuid4(), "GENERAL" if customer is None else "RET-A", v, customer, frm, to)


def test_general_list_highest_version_in_force() -> None:
    v1, v2, future = version(1), version(2), version(3, frm=date(2027, 1, 1))
    assert price_list_in_force([v1, v2, future], RET_A, DAY) == v2


def test_customer_list_wins_over_general() -> None:
    general, own = version(5), version(1, customer=RET_A)
    assert price_list_in_force([general, own], RET_A, DAY) == own
    assert price_list_in_force([general, own], DIST_B, DAY) == general


def test_expired_list_is_not_in_force() -> None:
    v1 = version(1, to=date(2026, 10, 31))
    assert price_list_in_force([v1], RET_A, DAY) is None


def test_versions_published_after_receipt_are_ignored() -> None:
    received = datetime(2026, 11, 21, 10, tzinfo=UTC)
    v1 = PriceListVersion(uuid.uuid4(), "GENERAL", 1, None, APR, None, datetime(2026, 4, 1, tzinfo=UTC))
    v2 = PriceListVersion(uuid.uuid4(), "GENERAL", 2, None, APR, None, datetime(2026, 11, 21, 11, tzinfo=UTC))
    assert price_list_in_force([v1, v2], RET_A, DAY, known_at=received) == v1
    assert price_list_in_force([v1, v2], RET_A, DAY) == v2


def test_stale_rule() -> None:
    v1, v2 = version(1), version(2)
    assert not is_stale(v2.id, v2)
    assert is_stale(v1.id, v2)
    assert is_stale(v1.id, None)


def test_plan_takes_the_list_price() -> None:
    (line,) = plan_order([OrderLineIn(M200, 150, D("50"))], {M200: D("50.00")})
    assert (line.qty, line.price, line.value) == (150, D("50.00"), D("7500.00"))


def test_tampered_price_refused() -> None:
    with pytest.raises(OrderError) as e:
        plan_order([OrderLineIn(M200, 150, D("1.00"))], {M200: D("50.00")})
    assert e.value.code == "price_mismatch"


@pytest.mark.parametrize(
    ("lines", "code"),
    [
        ([], "empty_order"),
        ([OrderLineIn(M200, 0, D(50))], "qty_not_positive"),
        ([OrderLineIn(M200, -3, D(50))], "qty_not_positive"),
        ([OrderLineIn(M200, 1, D(50)), OrderLineIn(M200, 2, D(50))], "duplicate_item"),
        ([OrderLineIn(M500, 1, D(90))], "item_not_on_price_list"),
    ],
)
def test_plan_refusals(lines: list[OrderLineIn], code: str) -> None:
    with pytest.raises(OrderError) as e:
        plan_order(lines, {M200: D("50.00")})
    assert e.value.code == code


def test_fractional_packets_refused() -> None:
    with pytest.raises(OrderError) as e:
        plan_order([OrderLineIn(M200, D("1.5"), D(50))], {M200: D(50)})  # type: ignore[arg-type]
    assert e.value.code == "whole_packets_only"


@given(
    st.lists(
        st.tuples(st.integers(1, 100_000), st.decimals(min_value=0, max_value=100_000, places=2)),
        min_size=1,
        max_size=20,
    )
)
def test_total_is_exactly_sum_of_qty_times_price(rows: list[tuple[int, Decimal]]) -> None:
    total = order_total([(f"p{i}", q, p) for i, (q, p) in enumerate(rows)])
    assert total.value == sum((q * p for q, p in rows), D(0))
    assert total.unit == "INR" and len(total.inputs) == 2 * len(rows)


def test_request_hash_ignores_line_order_and_trailing_zeros() -> None:
    prices = {M200: D("50.00"), M500: D("90.00")}
    pl = uuid.uuid4()
    a = plan_order([OrderLineIn(M200, 10, D("50")), OrderLineIn(M500, 2, D("90.0"))], prices)
    b = plan_order([OrderLineIn(M500, 2, D("90")), OrderLineIn(M200, 10, D("50.00"))], prices)
    c = plan_order([OrderLineIn(M200, 11, D("50")), OrderLineIn(M500, 2, D("90"))], prices)
    assert request_hash(request_doc(RET_A, pl, a, None)) == request_hash(request_doc(RET_A, pl, b, None))
    assert request_hash(request_doc(RET_A, pl, a, None)) != request_hash(request_doc(RET_A, pl, c, None))


def test_order_numbers() -> None:
    assert order_no("26-27", 1) == "SO/26-27/000001"
    with pytest.raises(ValueError):
        order_no("26-27", 0)


def test_new_price_list_rules() -> None:
    check_new_price_list({M200: D("50.00")}, {M200})
    for items, fg, code in (
        ({}, {M200}, "empty_price_list"),
        ({M200: D("50.00")}, set(), "not_a_finished_good"),
        ({M200: D("-1")}, {M200}, "bad_price"),
        ({M200: D("50.005")}, {M200}, "bad_price"),
    ):
        with pytest.raises(OrderError) as e:
            check_new_price_list(items, fg)
        assert e.value.code == code
