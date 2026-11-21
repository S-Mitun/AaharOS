"""Pure valuation tests (MP05): the NIT figures, WAC pools that drain to zero, value conservation, FIFO order."""

from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.core.money import round_money
from app.modules.valuation.domain import (
    METHODS,
    Fifo,
    LastPrice,
    Movement,
    Pool,
    ValuationError,
    WeightedAverage,
    fifo_layers,
    gain_value,
    line_value,
    proportional_value,
    replay_pool,
    unit_cost,
)

D = Decimal
KG = D(1000)
# NIT flour: opening 100 kg at 42, purchase 60 kg at 45 (base unit g)
FLOUR = [
    Movement(D(100_000), D("4200.00"), "OPENING", "J0"),
    Movement(D(60_000), D("2700.00"), "RECEIPT", "J1"),
]


def test_nit_flour_wac_and_issue() -> None:
    pool = replay_pool(FLOUR)
    assert unit_cost(pool, KG) == D("43.125000")
    assert WeightedAverage().issue_value(FLOUR, D(40_000)) == D("1725.00")


def test_nit_flour_sensitivity() -> None:
    assert Fifo().issue_value(FLOUR, D(40_000)) == D("1680.00")  # 40 kg from the 42/kg opening layer
    assert LastPrice().issue_value(FLOUR, D(40_000)) == D("1800.00")  # 40 kg at the last price, 45/kg
    assert {name: m.posts for name, m in METHODS.items()} == {"WAC": True, "FIFO": False, "LAST": False}


def test_last_unit_out_takes_the_rest() -> None:
    pool = Pool(D(3), D("10.00"))  # 3.333... per unit: rounding must not leave a paisa behind
    first = proportional_value(pool, D(1))
    second = proportional_value(Pool(D(2), pool.value - first), D(1))
    third = proportional_value(Pool(D(1), pool.value - first - second), D(1))
    assert (first, second, third) == (D("3.33"), D("3.34"), D("3.33"))
    assert first + second + third == D("10.00")


@pytest.mark.parametrize(
    ("pool", "qty", "code"),
    [
        (Pool(D(0), D(0)), D(1), "pool_empty"),
        (Pool(D(5), D(5)), D(6), "pool_short"),
        (Pool(D(5), D(5)), D(0), "qty_not_positive"),
    ],
)
def test_refusals(pool: Pool, qty: Decimal, code: str) -> None:
    with pytest.raises(ValuationError) as err:
        proportional_value(pool, qty)
    assert err.value.code == code


def test_float_is_refused() -> None:
    bad: Any = 1.5
    with pytest.raises(DomainError) as err:
        proportional_value(Pool(D(5), D(5)), bad)
    assert err.value.code == "not_decimal"
    with pytest.raises(DomainError):
        line_value(D(1), bad)


def test_line_value_rounds_once_half_up() -> None:
    assert line_value(D("0.5"), D("0.01")) == D("0.01")  # 0.005 -> 0.01
    assert line_value(D("60"), D("45")) == D("2700.00")
    assert line_value(D("50"), D("28.850000")) == D("1442.50")


def test_gain_value_basis() -> None:
    assert gain_value(FLOUR, D(1000)) == (D("43.13"), "WAC")  # 43.125 rounds half up
    drained = [*FLOUR, Movement(D(-160_000), D("-6900.00"), "ISSUE", "J2")]
    assert gain_value(drained, D(1000)) == (D("45.00"), "LAST")
    assert gain_value([], D(1000)) == (D(0), "NO_COST_YET")


def test_fifo_reversal_removes_its_own_layer() -> None:
    history = [*FLOUR, Movement(D(-60_000), D("-2700.00"), "REVERSAL", "J1R", reverses="J1")]
    layers = fifo_layers(history)
    assert [(layer.key, layer.qty_base, layer.value) for layer in layers] == [("J0", D(100_000), D("4200.00"))]


# ---------- properties ----------

receipts = st.lists(
    st.tuples(st.integers(min_value=1, max_value=100_000), st.integers(min_value=0, max_value=10_000_000)),
    min_size=1,
    max_size=8,
)


@given(receipts, st.lists(st.integers(min_value=1, max_value=100), min_size=1, max_size=10))
def test_wac_pool_drains_to_exactly_zero(ins: list[tuple[int, int]], chunks: list[int]) -> None:
    """S8: issuing everything, in any chunks, takes exactly the received value and leaves (0, 0)."""
    pool = Pool(D(sum(q for q, _ in ins)), sum((D(p) / 100 for _, p in ins), D(0)))
    received = pool.value
    issued = D(0)
    total_qty = pool.qty_base
    for share in chunks:
        if pool.qty_base == 0:
            break
        qty = max(D(1), (total_qty * share // 100)).min(pool.qty_base)
        value = proportional_value(pool, qty)
        assert value == value.quantize(D("0.01"))  # always whole paise
        assert D(0) <= value <= pool.value
        issued += value
        pool = Pool(pool.qty_base - qty, pool.value - value)
        assert issued + pool.value == received  # value conservation after every issue
    if pool.qty_base:
        issued += proportional_value(pool, pool.qty_base)  # the last unit out takes the rest
        pool = Pool(D(0), D(0))
    assert issued == received
    assert pool == Pool(D(0), D(0))


@given(receipts, st.integers(min_value=1, max_value=100))
def test_fifo_consumes_the_oldest_layers_first(ins: list[tuple[int, int]], share: int) -> None:
    history = [Movement(D(q), D(p) / 100, "RECEIPT", f"R{n}") for n, (q, p) in enumerate(ins)]
    total = sum(q for q, _ in ins)
    qty = max(1, total * share // 100)
    value = Fifo().issue_value(history, D(qty))
    expected, need = D(0), D(qty)  # oldest first, by hand
    for q, p in ins:
        take = min(need, D(q))
        expected += D(p) / 100 * take / q
        need -= take
    assert value == round_money(expected)  # half up, as the books round (0.005 -> 0.01)
    remaining = fifo_layers([*history, Movement(-D(qty), -value, "ISSUE", "I")])
    assert sum((layer.qty_base for layer in remaining), D(0)) == total - qty
    assert [layer.key for layer in remaining] == [f"R{n}" for n, (q, _) in enumerate(ins)][len(ins) - len(remaining) :]
