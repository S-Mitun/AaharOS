"""Pure costing tests (MP07): the standard card, run cost and cost per packet, the NIT waterfall (431.20 U), the
waterfall summing exactly as a property, mixed standards refused, and sensitivity with the book-value fallback."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.costing import domain
from app.modules.costing.domain import CardLine, CostingError, MethodValue, StandardCard, StandardLine
from app.modules.production.domain import (
    ConversionFacts,
    IssueMove,
    MaterialFacts,
    PackFacts,
    PackStd,
    RecipeStd,
    RunCostingFacts,
    StdLine,
)
from app.modules.uom.domain import ItemUnits

D = Decimal
FLOUR, OIL, SPICE, POUCH, CARTON, FG, BULK = (uuid.uuid4() for _ in range(7))
RUN = uuid.uuid4()
RECIPE = RecipeStd(
    uuid.uuid4(),
    "R",
    1,
    BULK,
    "bulk",
    D(40_000),
    (
        StdLine(FLOUR, "flour", "g", "kg", D(40_000), None),
        StdLine(OIL, "cooking_oil", "mL", "L", D(10_000), None),
        StdLine(SPICE, "spice_mix", "g", "kg", D(1_200), None),
    ),
)
PACK = PackStd(
    uuid.uuid4(),
    "P-200",
    "pack",
    1,
    uuid.uuid4(),
    FG,
    "fg",
    "packet",
    D(200),
    20,
    90,
    (
        StdLine(CARTON, "carton_20", "piece", "piece", D("0.05"), None),
        StdLine(POUCH, "pouch_200g", "piece", "piece", D(1), None),
    ),
)
RATES = {FLOUR: D("0.042"), OIL: D("0.14"), SPICE: D("0.2"), POUCH: D("2.5"), CARTON: D(15)}
CONVERSION = {"gas_power": D(600), "labour": D(1200)}
NIT_CONVERSION = (D(1200), D(600))


def _card(rates: dict[uuid.UUID, Decimal] = RATES, pack: PackStd = PACK) -> StandardCard:
    lines, per_unit = domain.card_lines(RECIPE, pack, rates, CONVERSION)
    return StandardCard(uuid.uuid4(), pack.version_id, 1, date(2026, 4, 1), per_unit, tuple(lines))


def _material(
    item: uuid.UUID, code: str, role: str, base: str, stock: str, qty: Decimal, value: Decimal
) -> MaterialFacts:
    return MaterialFacts(item, code, role, base, stock, qty, value, (IssueMove(uuid.uuid4(), "ISSUE", qty, value),))


def _facts(
    good: int = 188,
    oil: Decimal | None = None,
    flour_value: Decimal | None = None,
    pouches: Decimal | None = None,
    cartons: Decimal | None = None,
    conversion: tuple[Decimal, ...] = NIT_CONVERSION,
    packs: tuple[PackFacts, ...] | None = None,
) -> RunCostingFacts:
    oil = D(10_500) if oil is None else oil
    flour_value = D("1725.00") if flour_value is None else flour_value
    pouches = D(194) if pouches is None else pouches
    cartons = D(9) if cartons is None else cartons
    materials = (
        _material(FLOUR, "flour", "INGREDIENT", "g", "kg", D(40_000), flour_value),
        _material(OIL, "cooking_oil", "INGREDIENT", "mL", "L", oil, (oil * D("0.14")).quantize(D("0.01"))),
        _material(SPICE, "spice_mix", "INGREDIENT", "g", "kg", D(1_200), D("240.00")),
        _material(CARTON, "carton_20", "PACKAGING", "piece", "piece", cartons, cartons * 15),
        _material(POUCH, "pouch_200g", "PACKAGING", "piece", "piece", pouches, pouches * D("2.5")),
    )
    total = sum((m.value for m in materials), D(0)) + sum(conversion, D(0))
    one = PackFacts(uuid.uuid4(), PACK, D(40_000), good, {POUCH: pouches, CARTON: cartons}, {POUCH: D(6)},
                    uuid.uuid4(), "B-001", D(good), total)  # fmt: skip
    return RunCostingFacts(
        RUN,
        "B-001",
        "FINAL",
        date(2026, 11, 21),
        D(1),
        RECIPE,
        packs or (one,),
        materials,
        tuple(
            ConversionFacts(uuid.uuid4(), k, a, date(2026, 11, 21), None)
            for k, a in zip(("LABOUR", "GAS_POWER"), conversion, strict=False)
        ),
        uuid.uuid4(),
        D(0),
    )


def test_card_equals_the_mp05_standard() -> None:
    card = _card()
    assert card.per_unit == D("28.850000") and card.conversion_per_batch == D(1800)
    lines = [
        StandardLine("flour", D(40), D(42)),
        StandardLine("oil", D(10), D(140)),
        StandardLine("spice", D("1.2"), D(200)),
        StandardLine("pouch", D(200), D("2.5")),
        StandardLine("carton", D(10), D(15)),
    ]
    assert domain.standard_cost(lines, D(1800), D(200)).per_unit == card.per_unit


def test_rates_convert_to_base_units_exactly() -> None:
    assert domain.rate_per_base(D(42), ItemUnits("g", "kg")) == D("0.042")
    assert domain.rate_per_stock_unit(D("0.14"), ItemUnits("mL", "L")) == D(140)
    with pytest.raises(CostingError):
        domain.rate_per_base(D("0.0007"), ItemUnits("g", "kg"))  # 0.0000007 per g is not exact at 6 dp
    with pytest.raises(CostingError, match="rate"):
        domain.card_lines(RECIPE, PACK, {FLOUR: D("0.042")}, CONVERSION)


def test_nit_run_cost_and_cost_per_packet() -> None:
    cost = domain.run_cost(_facts())
    assert (cost.materials.value, cost.conversion.value, cost.total.value) == (D("4055.00"), D(1800), D("5855.00"))
    assert cost.per_good_unit is not None and cost.per_good_unit.value == D("31.143617")
    assert cost.to_json()["per_good_unit_display"] == "31.14"
    assert cost.lots[0].value == D("31.143617") and cost.per_good_unit.unit == "INR/packet"


def test_nit_waterfall() -> None:
    wf = domain.waterfall(_facts(), [_card()])
    assert (wf.actual.value, wf.standard.value, wf.total.value) == (D("5855.00"), D("5423.80"), D("431.20"))
    parts = {(c.kind, c.item_code): c.value for c in wf.components}
    assert parts == {
        ("YIELD", "fg"): D("307.20"),
        ("USAGE", "cooking_oil"): D("70.00"),
        ("PRICE", "flour"): D("45.00"),
        ("USAGE", "pouch_200g"): D("15.00"),
        ("USAGE", "carton_20"): D("-6.00"),
        ("CONVERSION", None): D(0),
    }
    assert wf.component("USAGE", "pouch_200g").note == "6 damaged"
    ranked = wf.to_json()["components"]
    assert ranked[0]["kind"] == "YIELD" and ranked[-1]["direction"] == "FAVOURABLE"


def test_waterfall_refuses_mixed_standards_and_missing_cards() -> None:
    other = _card({**RATES, FLOUR: D("0.043")})
    two = _facts().packs[0]
    facts = _facts(packs=(two, two))
    with pytest.raises(CostingError) as err:
        domain.waterfall(facts, [_card(), other])
    assert err.value.code == "mixed_standards"
    with pytest.raises(CostingError):
        domain.waterfall(_facts(), [])


@given(
    good=st.integers(min_value=0, max_value=260),
    oil=st.integers(min_value=0, max_value=20_000),
    flour_value=st.decimals(min_value=0, max_value=5_000, places=2),
    pouches=st.integers(min_value=0, max_value=400),
    cartons=st.integers(min_value=0, max_value=20),
    labour=st.decimals(min_value=0, max_value=5_000, places=2),
)
def test_waterfall_sums_exactly(
    good: int, oil: int, flour_value: Decimal, pouches: int, cartons: int, labour: Decimal
) -> None:
    facts = _facts(good, D(oil), flour_value, D(pouches), D(cartons), (labour, D(600)))
    wf = domain.waterfall(facts, [_card()])
    assert sum(c.value for c in wf.components) == wf.total.value == wf.actual.value - wf.standard.value
    assert all(c.value == c.value.quantize(D("0.01")) for c in wf.components)
    rounding = [c for c in wf.components if c.kind == "ROUNDING"]
    assert not rounding or abs(rounding[0].value) <= D("0.01") * len(wf.components)  # explicit, and only paise


def test_sensitivity_uses_the_book_value_when_a_method_has_no_answer() -> None:
    values = {
        "WAC": [MethodValue("flour", D(1725), D(1725), False), MethodValue("cooking_oil", D(1470), D(1470), False)],
        "FIFO": [MethodValue("flour", D(1725), D(1680), False), MethodValue("cooking_oil", D(1470), D(1470), False)],
        "LAST": [MethodValue("flour", D(1725), D(1800), False), MethodValue("cooking_oil", D(1470), D(1470), True)],
    }
    out = domain.sensitivity(D("5855.00"), 188, values, "packet")
    assert (out["WAC"]["per_good_unit_display"], out["FIFO"]["total"]["value"]) == ("31.14", "5810.00")
    assert (out["FIFO"]["per_good_unit_display"], out["LAST"]["per_good_unit_display"]) == ("30.90", "31.54")
    assert out["LAST"]["book_value_used_for"] == ["cooking_oil"] and [m for m, s in out.items() if s["posts"]] == [
        "WAC"
    ]


def test_card_lines_are_kinds_with_rates() -> None:
    card = _card()
    assert {ln.cost_kind for ln in card.lines} == {"MATERIAL", "PACKAGING", "CONVERSION"}
    assert card.rate(CARTON) == 15 and card.rate(uuid.uuid4()) is None
    assert CardLine("CONVERSION", None, "labour", D(1), D(1200)) in card.lines
