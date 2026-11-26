"""Pure planning rules (MP12, ADR-0019): runway and shortage attribution."""

from decimal import Decimal

import pytest

from app.core.explained import Explained
from app.modules.planning.domain import (
    Action,
    MaterialNeed,
    PlanningError,
    YieldLoss,
    rank_actions,
    runway,
    shortage_attribution,
)

D = Decimal

NIT_AFTER_RUN = [
    MaterialNeed("flour", "kg", D(120), D(40)),
    MaterialNeed("cooking_oil", "L", D("19.5"), D(10)),
    MaterialNeed("spice_mix", "kg", D("3.8"), D("1.2")),
    MaterialNeed("pouch_200g", "piece", D(306), D(200)),
    MaterialNeed("carton_20", "piece", D(21), D(10)),
]


def test_nit_runway_after_the_run() -> None:
    r = runway(NIT_AFTER_RUN)
    assert {ln.item_code: ln.batches_display for ln in r.lines} == {
        "flour": D("3.00"),
        "cooking_oil": D("1.95"),
        "spice_mix": D("3.17"),
        "pouch_200g": D("1.53"),
        "carton_20": D("2.10"),
    }
    assert (r.binding, r.full_batches) == (("pouch_200g",), 1)
    assert r.lines[1].explained.formula == "available / needed per standard batch"


def test_no_stock_means_no_batches_and_negative_is_not_hidden_as_positive() -> None:
    r = runway([MaterialNeed("flour", "kg", D(0), D(40)), MaterialNeed("oil", "L", D(-1), D(10))])
    assert r.full_batches == 0 and set(r.binding) == {"flour", "oil"}


def test_runway_refusals() -> None:
    with pytest.raises(PlanningError):
        runway([])
    with pytest.raises(PlanningError):
        runway([MaterialNeed("flour", "kg", D(10), D(0))])


def test_nit_shortage_attribution() -> None:
    e = shortage_attribution(32, [YieldLoss("B-001", D(200), 188)])
    assert e.value == 12 and e.unit == "packets"


def test_attribution_never_exceeds_the_shortage_and_ignores_good_surprises() -> None:
    assert shortage_attribution(5, [YieldLoss("B-001", D(200), 150)]).value == 5
    assert shortage_attribution(32, [YieldLoss("B-002", D(200), 205)]).value == 0
    assert shortage_attribution(0, [YieldLoss("B-001", D(200), 188)]).value == 0


def _action(kind: str, rupees: str) -> Action:
    return Action(kind, kind, D(rupees), "/", Explained(D(rupees), "INR", "test"))


def test_actions_rank_by_rupees_keep_three_and_drop_zero() -> None:
    ranked = rank_actions(
        [
            _action("leak", "120.00"),
            _action("collect", "3875.00"),
            _action("make", "5000.00"),
            _action("buy", "0.00"),
            _action("decide", "3875.00"),
        ]
    )
    assert [a.kind for a in ranked] == ["make", "decide", "collect"]  # a tie goes to the fixed order
    assert rank_actions([_action("buy", "0")]) == []
