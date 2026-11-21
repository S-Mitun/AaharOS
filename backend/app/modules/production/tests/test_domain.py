"""Pure production tests (MP06): the variance engine on the NIT figures, the E2 flag rule, packing, mass balance,
value splits and the completion journal (laws 1 and 2 by construction, decision E4)."""

import uuid
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.ledger.domain import LineSpec
from app.modules.production import domain
from app.modules.production.domain import (
    FAVOURABLE,
    ON_STANDARD,
    UNFAVOURABLE,
    IssuedMaterial,
    PackagingUse,
    PackedMass,
    PackOutcome,
    PackStd,
    RecipeStd,
    RunError,
    StdLine,
)

D = Decimal
FLOUR, OIL, SPICE, POUCH, CARTON, FG, BULK = (uuid.uuid4() for _ in range(7))

RECIPE = RecipeStd(
    version_id=uuid.uuid4(),
    code="R",
    version=1,
    bulk_item_id=BULK,
    bulk_item_code="bulk",
    bulk_yield_g=D(40_000),
    lines=(
        StdLine(FLOUR, "flour", "g", "kg", D(40_000), None),
        StdLine(OIL, "cooking_oil", "mL", "L", D(10_000), None),
        StdLine(SPICE, "spice_mix", "g", "kg", D(1_200), None),
    ),
)
PACK = PackStd(
    version_id=uuid.uuid4(),
    code="P-200",
    name="pack 200",
    version=1,
    recipe_id=uuid.uuid4(),
    fg_item_id=FG,
    fg_item_code="fg",
    fg_stock_uom="packet",
    net_g=D(200),
    units_per_carton=20,
    shelf_life_days=90,
    lines=(
        StdLine(CARTON, "carton_20", "piece", "piece", D("0.05"), None),
        StdLine(POUCH, "pouch_200g", "piece", "piece", D(1), None),
    ),
)
TOL = D(3)


def test_nit_ingredient_variances() -> None:
    issued = {FLOUR: D(40_000), OIL: D(10_500), SPICE: D(1_200)}
    by = {v.label: v for v in domain.ingredient_variances(RECIPE, D(1), issued, TOL)}
    oil = by["cooking_oil"]
    assert (oil.standard, oil.actual, oil.pct_display, oil.flagged) == (D(10), D("10.5"), D("5.00"), True)
    assert oil.direction == UNFAVOURABLE and oil.unit == "L" and oil.explained.value == D("5.00")
    assert by["flour"].pct == 0 and by["flour"].direction == ON_STANDARD and not by["flour"].flagged
    assert not by["spice_mix"].flagged


def test_nit_yield_and_flexible_packaging() -> None:
    y = domain.yield_variance(PACK, D(40_000), 188, TOL)
    assert (y.standard, y.actual, y.pct_display, y.flagged, y.direction) == (
        D(200),
        D(188),
        D("-6.00"),
        True,
        UNFAVOURABLE,
    )
    pairs = {
        f.label: (f, b) for f, b in domain.packaging_variances(PACK, D(40_000), 188, {POUCH: D(194), CARTON: D(9)}, TOL)
    }
    pouch, pouch_batch = pairs["pouch_200g"]
    assert (pouch.standard, pouch.pct_display, pouch.flagged) == (D(188), D("3.19"), True)
    assert (pouch_batch.standard, pouch_batch.pct_display, pouch_batch.flagged) == (D(200), D("-3.00"), False)
    assert not pouch_batch.drives_alert
    carton, _ = pairs["carton_20"]
    assert (carton.standard, carton.pct_display, carton.direction) == (D("9.4"), D("-4.26"), FAVOURABLE)
    assert carton.beyond_tolerance and not carton.flagged  # E2: favourable beyond tolerance is information
    assert carton.note == "8 loose packets not cartoned"


def _usage(standard: Decimal, actual: Decimal, tol: Decimal = TOL) -> domain.Variance:
    return domain.variance(
        label="x",
        view="PER_BATCH",
        item_id=None,
        unit="kg",
        standard=standard,
        actual=actual,
        tolerance_pct=tol,
        higher_is_worse=True,
        formula="f",
    )


def test_flag_is_strict_and_uses_the_unrounded_percentage() -> None:
    assert not _usage(D(100), D(103)).flagged  # exactly 3.00% is within tolerance
    v = _usage(D(100_000), D(103_001))  # 3.001% shows as 3.00 but is beyond
    assert v.pct_display == D("3.00") and v.flagged
    assert not _usage(D(100), D(97)).flagged  # favourable
    assert _usage(D(100), D(103), tol=D("2.5")).flagged  # a line override changes the decision


def test_zero_standard_has_no_percentage() -> None:
    v = _usage(D(0), D(6))
    assert v.pct is None and v.flagged and v.to_json()["variance_pct"] is None
    assert not _usage(D(0), D(0)).flagged


def test_packing_breakdown_is_divmod() -> None:
    p = domain.packing(188, 20)
    assert (p.full_cartons, p.loose) == (9, 8)
    assert domain.packing(80, 10).loose == 0


def test_nit_mass_balance_shows_the_gap() -> None:
    mb = domain.mass_balance(D(40_000), D(0), [PackedMass("P", 188, D(200), None)], D(0), D(0))
    j = mb.to_json()
    assert (j["expected_bulk"], j["good_packed"], j["unexplained_gap"]) == ("40", "37.6", "2.4")
    assert mb.explained.unit == "kg" and mb.explained.value == D("2.4")
    assert j["giveaway"] is None


def test_giveaway_is_part_of_the_gap() -> None:
    give = domain.giveaway_g([D(203), D(205), D(204)], D(200), 188)  # mean 204 g: 4 g over per packet
    assert give == D(752)
    mb = domain.mass_balance(D(40_000), D(0), [PackedMass("P", 188, D(200), give)], D(500), D(0))
    assert mb.unexplained_g == D(1_900) and mb.gap_after_giveaway_g == D(1_148)
    assert domain.giveaway_g([], D(200), 188) is None


def test_allocation_and_expected_units() -> None:
    assert domain.check_allocation(D(40_000), [D(20_000), D(20_000)]) == 0
    assert domain.check_allocation(D(40_000), [D(30_000)]) == D(10_000)  # unallocated bulk is shown
    with pytest.raises(RunError) as err:
        domain.check_allocation(D(40_000), [D(20_000), D(20_001)])
    assert err.value.code == "over_allocated"
    with pytest.raises(RunError):
        domain.check_allocation(D(40_000), [D(0)])
    assert domain.expected_units(D(40_000), D(500)) == 80
    assert domain.stored_expected_units(D(40_000), D(300)) == D("133.333333")


def test_numbering_and_lots() -> None:
    assert domain.run_no(1) == "B-001" and domain.run_no(1234) == "B-1234"
    assert domain.issue_no("26-27", 1) == "MI/26-27/000001"
    assert domain.lot_numbers("B-001", 1) == ["B-001"]
    assert domain.lot_numbers("B-002", 2) == ["B-002-A", "B-002-B"]
    with pytest.raises(RunError):
        domain.lot_numbers("B-003", 27)


def test_returns_come_back_at_the_runs_own_average() -> None:
    assert domain.returned_value(D(40_000), D("1725.00"), D(10_000)) == D("431.25")
    assert domain.returned_value(D(40_000), D("1725.00"), D(40_000)) == D("1725.00")  # the last unit takes the rest
    with pytest.raises(RunError, match="issued"):
        domain.returned_value(D(40_000), D("1725.00"), D(40_001))


@given(
    st.decimals(min_value=0, max_value=100_000, places=2),
    st.lists(st.integers(min_value=1, max_value=50_000), min_size=1, max_size=6),
)
def test_split_value_is_exact(total: Decimal, weights: list[int]) -> None:
    shares = domain.split_value(total, [D(w) for w in weights])
    assert sum(shares) == total and all(s == s.quantize(D("0.01")) for s in shares)


FULL_BATCH = D(40_000)


def _outcome(good: int, alloc: Decimal = FULL_BATCH, lot: bool = True, damaged: int = 6) -> PackOutcome:
    return PackOutcome(
        pack_line_id=uuid.uuid4(),
        bulk_allocated_g=alloc,
        good_units=good,
        fg_item_id=FG,
        fg_base_uom="piece",
        lot_id=uuid.uuid4() if lot and good else None,
        packaging=(
            PackagingUse(POUCH, "piece", D(good + damaged), D(damaged), D("2.50") * (good + damaged)),
            PackagingUse(CARTON, "piece", D(good // 20), D(0), D(15) * (good // 20)),
        ),
    )


ISSUED = (
    IssuedMaterial(FLOUR, "g", D(40_000), D("1725.00")),
    IssuedMaterial(OIL, "mL", D(10_500), D("1470.00")),
    IssuedMaterial(SPICE, "g", D(1_200), D("240.00")),
)


def _sums(lines: tuple[LineSpec, ...]) -> tuple[dict[uuid.UUID, Decimal], Decimal]:
    qty: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for ln in lines:
        qty[ln.item_id] += ln.qty
    return qty, sum((ln.value for ln in lines), D(0))


def test_nit_completion_journal() -> None:
    o = _outcome(188)
    plan = domain.plan_completion(ISSUED, [o], bulk_item_id=BULK, scrap_g=D(0))
    qty, value = _sums(plan.lines)
    assert all(q == 0 for q in qty.values()) and value == 0
    assert plan.lot_value[o.pack_line_id] == D("4055.00")  # 3,435 ingredients + 485 pouches + 135 cartons
    scrap = [ln for ln in plan.lines if ln.location == "SCRAP"]
    assert [(ln.item_id, ln.qty, ln.value) for ln in scrap] == [(POUCH, D(6), D(0))]  # damaged: quantity, no value
    assert plan.written_off[o.pack_line_id] == 0


def test_zero_good_line_writes_its_share_off_to_scrap() -> None:
    good, burnt = _outcome(97, D(20_000)), _outcome(0, D(20_000), damaged=3)
    plan = domain.plan_completion(ISSUED, [good, burnt], bulk_item_id=BULK, scrap_g=D(500))
    qty, value = _sums(plan.lines)
    assert all(q == 0 for q in qty.values()) and value == 0
    assert plan.lot_value[burnt.pack_line_id] == 0
    assert plan.written_off[burnt.pack_line_id] == D("1717.50") + D("7.50")  # half the ingredients + 3 pouches
    assert plan.lot_value[good.pack_line_id] + plan.written_off[burnt.pack_line_id] == D("3435.00") + sum(
        u.value for o in (good, burnt) for u in o.packaging
    )
    bulk_scrap = [ln for ln in plan.lines if ln.item_id == BULK and ln.location == "SCRAP"]
    assert sorted((ln.qty, ln.value) for ln in bulk_scrap) == [(D(500), D(0)), (D(20_000), D("1717.50"))]


def test_completion_refusals() -> None:
    with pytest.raises(RunError, match="nothing"):
        domain.plan_completion((), [_outcome(188)], bulk_item_id=BULK, scrap_g=D(0))
    with pytest.raises(RunError, match="reason"):
        domain.check_completion([_outcome(0)], D(0), D(0), None)
    with pytest.raises(RunError, match="reason"):
        domain.check_completion([_outcome(188)], D(100), D(0), " ")
    bad = PackOutcome(uuid.uuid4(), D(1), 1, FG, "piece", None, (PackagingUse(POUCH, "piece", D(1), D(2), D(0)),))
    with pytest.raises(RunError, match="damaged"):
        domain.check_completion([bad], D(0), D(0), None)


@given(
    st.lists(
        st.tuples(st.integers(min_value=0, max_value=400), st.integers(min_value=1, max_value=40_000)),
        min_size=1,
        max_size=4,
    ),
    st.integers(min_value=0, max_value=5_000),
    st.decimals(min_value=0, max_value=5_000, places=2),
)
def test_completion_conserves_quantity_and_value(lines: list[tuple[int, int]], scrap: int, ingredient: Decimal) -> None:
    issued = (IssuedMaterial(FLOUR, "g", D(40_000), ingredient),)
    outcomes = [_outcome(good, D(alloc), damaged=good % 3) for good, alloc in lines]
    plan = domain.plan_completion(issued, outcomes, bulk_item_id=BULK, scrap_g=D(scrap))
    qty, value = _sums(plan.lines)
    assert all(q == 0 for q in qty.values()) and value == 0  # laws 1 and 2
    packaging = sum((u.value for o in outcomes for u in o.packaging), D(0))
    assert sum(plan.lot_value.values()) + sum(plan.written_off.values()) == ingredient + packaging


def test_domain_knows_no_product() -> None:
    """bom.md section 4: every number comes from the snapshot, so the 500 g change needs no code."""
    source = Path(domain.__file__).read_text(encoding="utf-8").lower()
    assert "murukku" not in source
    for literal in ("200", "20 ", "(20)", "= 20"):
        assert literal not in source
