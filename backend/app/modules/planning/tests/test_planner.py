"""The batch planner (MP12, ADR-0019 L4): pure CP-SAT, no database. NIT figures after the benchmark run."""

from decimal import Decimal

import pytest

from app.modules.planning.domain import PlanningError
from app.modules.planning.planner import Demand, ItemParams, PackOption, plan

D = Decimal

PER_BATCH = {
    "flour": D(40_000),
    "cooking_oil": D(10_000),
    "spice_mix": D(1_200),
    "pouch_200g": D(200),
    "carton_20": D(10),
}
AFTER_RUN = {
    "flour": D(120_000),
    "cooking_oil": D(19_500),
    "spice_mix": D(3_800),
    "pouch_200g": D(306),
    "carton_20": D(21),
}
MURUKKU = PackOption("MUR-200", "v1", "murukku_200g", 200, PER_BATCH)
DEMO_PARAMS = {
    "flour": ItemParams(D(50_000), D(20_000), D(25_000), 3),
    "cooking_oil": ItemParams(D(20_000), D(10_000), D(15_000), 2),
    "spice_mix": ItemParams(D(2_000), D(1_000), D(1_000), 5),
    "pouch_200g": ItemParams(D(300), D(200), D(500), 7),
    "carton_20": ItemParams(D(20), D(10), D(50), 7),
}


def test_materials_bind_before_capacity() -> None:
    """500 packets short and room for 2 batches, but oil (1.95) and pouches (1.53) allow only 1."""
    p = plan([MURUKKU], [Demand("murukku_200g", 500, 0, D("25.00"))], AFTER_RUN, 2, DEMO_PARAMS)
    assert p.status == "OPTIMAL"
    assert p.batches == {"MUR-200": 1} and p.met == {"murukku_200g": 200}
    assert p.value_met == D("5000.00")
    assert p.materials_used["pouch_200g"] == 200
    # a full plan is 3 batches: oil, pouches and cartons are short, flour exactly enough
    assert p.short == {"cooking_oil": D(10_500), "pouch_200g": D(294), "carton_20": D(9)}
    assert p.explained["MUR-200"].value == 1 and p.explained["MUR-200"].unit == "batches"


def test_purchases_follow_safety_reorder_and_minimum_order() -> None:
    p = plan([MURUKKU], [Demand("murukku_200g", 500, 0, D("25.00"))], AFTER_RUN, 2, DEMO_PARAMS)
    buy = {pu.item: pu.qty for pu in p.purchases}
    assert buy == {
        "cooking_oil": D(20_500),  # 30,000 needed + 10,000 safety - 19,500 on hand
        "pouch_200g": D(500),  # 494 rounded up to the minimum order
        "carton_20": D(50),  # 19 rounded up to the minimum order
        "flour": D(25_000),  # 20,000 (safety only) rounded up to the minimum order
        "spice_mix": D(1_000),  # 800 rounded up to the minimum order
    }
    oil = next(pu for pu in p.purchases if pu.item == "cooking_oil")
    assert oil.lead_time_days == 2 and oil.explained.method == "Suggested purchase"


def test_the_benchmark_shortfall_of_32_needs_one_batch() -> None:
    p = plan([MURUKKU], [Demand("murukku_200g", 300, 268, D("25.00"))], AFTER_RUN, 2, {})
    assert p.batches == {"MUR-200": 1} and p.met == {"murukku_200g": 32}
    assert p.short == {} and p.purchases == []  # no planning settings: nothing beyond the need


def test_scarce_capacity_goes_to_the_more_valuable_demand() -> None:
    plenty = {m: q * 10 for m, q in AFTER_RUN.items()}
    cheap = PackOption("CHEAP", "v2", "mixture_200g", 200, PER_BATCH)
    p = plan(
        [cheap, MURUKKU],
        [Demand("mixture_200g", 200, 0, D("20.00")), Demand("murukku_200g", 200, 0, D("25.00"))],
        plenty,
        1,
        {},
    )
    assert p.batches == {"CHEAP": 0, "MUR-200": 1} and p.value_met == D("5000.00")


def test_no_batch_beyond_what_is_short() -> None:
    plenty = {m: q * 10 for m, q in AFTER_RUN.items()}
    p = plan([MURUKKU], [Demand("murukku_200g", 210, 0, D("25.00"))], plenty, 5, {})
    assert p.batches == {"MUR-200": 2} and p.met == {"murukku_200g": 210}


def test_nothing_to_plan_and_refusals() -> None:
    p = plan([MURUKKU], [Demand("murukku_200g", 100, 238, D("25.00"))], AFTER_RUN, 2, {})
    assert p.status == "NOTHING_TO_PLAN" and p.batches == {} and p.purchases == []
    with pytest.raises(PlanningError):
        plan([MURUKKU], [], AFTER_RUN, -1, {})


def test_low_stock_triggers_a_reorder_even_without_demand() -> None:
    p = plan([MURUKKU], [], {"pouch_200g": D(100)}, 2, {"pouch_200g": ItemParams(D(300), D(200), D(0), 7)})
    assert [(pu.item, pu.qty) for pu in p.purchases] == [("pouch_200g", D(400))]  # back to 300 + 200
