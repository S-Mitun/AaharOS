"""MP16: the simulator is deterministic, the pipeline removes every injected fault, and each method recovers its
planted truth and passes (or honestly fails) its ship gate."""

from typing import Any

import pytest

from analytics.eval.run import evaluate
from analytics.models import methods as m
from analytics.simulator import generate as sim


@pytest.fixture(scope="module")
def result() -> dict[str, Any]:
    return evaluate()


def test_the_simulator_is_deterministic() -> None:
    a, b = sim.simulate(1), sim.simulate(1)
    assert [o.packets for o in a.orders[:500]] == [o.packets for o in b.orders[:500]]
    assert sim.simulate(2).orders[0].packets != a.orders[0].packets or len(sim.simulate(2).orders) != len(a.orders)


def test_faults_are_caught(result: dict[str, Any]) -> None:
    f = result["faults"]
    assert f["duplicate_recall"] >= 0.99 and f["unit_recall"] >= 0.95
    assert f["duplicate_precision"] >= 0.99 and f["unit_precision"] >= 0.95


def test_planted_truths_are_recovered(result: dict[str, Any]) -> None:
    for name, planted in sim.PLANTED["festival_uplift"].items():
        assert abs(result["festival_uplift"][name] / planted - 1) < 0.1, name
    lot = result["supplier_lot"]
    assert lot["flagged"] and abs(lot["S-05_effect"] + 0.05) < 0.01
    assert abs(result["spc"]["o3_oil_effect"] - 0.04) < 0.01
    assert result["spc"]["o3_first_signal_run"] <= 30 and result["spc"]["false_alarms_per_50_runs"] < 1
    assert abs(result["payment"]["R-7_mean_days"] - 60) < 3
    assert abs(result["cannibalisation"] + 0.15) < 0.03


def test_models_ship_only_when_they_beat_their_baseline(result: dict[str, Any]) -> None:
    f = result["forecast"]
    assert f["ships"] == (f["wape_festival_model"] <= 0.9 * f["wape_seasonal_naive"])
    p = result["payment"]
    assert p["ships"] == (p["brier_model"] < p["brier_last_time_rule"])


def test_methods_on_small_known_cases() -> None:
    assert m.wape([10, 10], [9, 11]) == pytest.approx(0.1)
    assert m.seasonal_naive(list(range(60)), 55) == 3
    assert m.moving_average([1, 2, 3, 4, 5], 5) == 3.5
    ew = m.ewma_by_operator([10.0] * 20 + [10.0, 12.0, 12.0, 12.0], ["a"] * 20 + ["b"] * 4)
    assert "b" in ew.signals and "a" not in ew.signals
    point, lo, hi = m.bootstrap_diff([90.0, 91.0, 89.0] * 10, [95.0, 96.0, 94.0] * 10)
    assert point < 0 and hi < 0
