"""Pure recipe tests (MP06): lines in base units, item kinds, tolerances, activation rules, snapshot shape."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.modules.recipe import domain
from app.modules.recipe.domain import PackLineIn, RecipeError, RecipeLineIn, SnapshotLine
from app.modules.uom.domain import ItemUnits, UomError

D = Decimal
FLOUR, OIL, POUCH = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ITEMS = {
    FLOUR: (ItemUnits("g", "kg"), "RAW"),
    OIL: (ItemUnits("mL", "L"), "RAW"),
    POUCH: (ItemUnits("piece", "piece"), "PACK"),
}


def test_recipe_lines_go_to_base_units() -> None:
    plan = domain.plan_recipe_lines([RecipeLineIn(FLOUR, D(40), "kg"), RecipeLineIn(OIL, D(10), "L", D("2.5"))], ITEMS)
    assert [(p.qty_base, p.tolerance_pct) for p in plan] == [(D(40_000), None), (D(10_000), D("2.5"))]


@pytest.mark.parametrize(
    ("lines", "code"),
    [
        ([], "no_lines"),
        ([RecipeLineIn(FLOUR, D(1), "kg"), RecipeLineIn(FLOUR, D(2), "kg")], "duplicate_item"),
        ([RecipeLineIn(POUCH, D(1), "piece")], "not_an_ingredient"),
        ([RecipeLineIn(FLOUR, D(0), "kg")], "qty_not_positive"),
        ([RecipeLineIn(FLOUR, D(1), "kg", D(101))], "bad_tolerance"),
        ([RecipeLineIn(uuid.uuid4(), D(1), "kg")], "unknown_item"),
    ],
)
def test_recipe_refusals(lines: list[RecipeLineIn], code: str) -> None:
    with pytest.raises(RecipeError) as err:
        domain.plan_recipe_lines(lines, ITEMS)
    assert err.value.code == code


def test_recipe_line_unit_must_match_the_item() -> None:
    with pytest.raises(UomError):
        domain.plan_recipe_lines([RecipeLineIn(FLOUR, D(1), "L")], ITEMS)


def test_pack_lines() -> None:
    kinds = {i: k for i, (_, k) in ITEMS.items()}
    assert domain.plan_pack_lines([PackLineIn(POUCH, D("0.05"))], kinds)[0].qty_per_good_unit == D("0.05")
    with pytest.raises(RecipeError, match="packaging"):
        domain.plan_pack_lines([PackLineIn(FLOUR, D(1))], kinds)
    with pytest.raises(RecipeError, match="decimal places"):
        domain.plan_pack_lines([PackLineIn(POUCH, D(1) / D(24))], kinds)  # 1/24 is not exact at 6 dp


def test_pack_header_and_activation() -> None:
    domain.check_pack_header(D(500), 10, 90)
    for bad in ((D(0), 10, 90), (D(500), 0, 90), (D(500), 10, True)):
        with pytest.raises(RecipeError):
            domain.check_pack_header(*bad)
    domain.check_activation("DRAFT", 3)
    with pytest.raises(RecipeError, match="DRAFT"):
        domain.check_activation("ACTIVE", 3)
    with pytest.raises(RecipeError, match="no lines"):
        domain.check_activation("DRAFT", 0)


def test_snapshot_is_plain_json_with_decimal_strings() -> None:
    line = SnapshotLine(FLOUR, "flour", "g", "kg", D("40000.000000"), "PER_BATCH", None)
    snap = domain.recipe_snapshot(
        recipe_id=uuid.uuid4(),
        code="R",
        name="Recipe",
        version_id=uuid.uuid4(),
        version=1,
        effective_from=date(2026, 4, 1),
        bulk_item_id=uuid.uuid4(),
        bulk_item_code="bulk",
        bulk_yield_g=D("40000.000000"),
        lines=[line],
    )
    assert snap["bulk_yield_g"] == "40000" and snap["lines"][0]["qty_base"] == "40000"
    assert snap["lines"][0]["tolerance_pct"] is None and snap["effective_from"] == "2026-04-01"
