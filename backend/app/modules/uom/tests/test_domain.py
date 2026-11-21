"""Pure unit-conversion tests (MP04): exact round trips, refused cross-dimension conversions, carton splits."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.uom.domain import (
    CARTON,
    ItemUnits,
    UomError,
    from_base,
    split_into_cartons,
    to_base,
)

FLOUR = ItemUnits(base_uom="g", stock_uom="kg")
OIL = ItemUnits(base_uom="mL", stock_uom="L")
OIL_WITH_DENSITY = ItemUnits(base_uom="mL", stock_uom="L", density=Decimal("1.098901"))  # mL per g
MURUKKU = ItemUnits(base_uom="piece", stock_uom="packet", lot_tracked=True)

# Up to 3 decimal places in kg / L is a whole number of g / mL; up to 6 dp in the base unit is what the ledger stores.
kilos = st.decimals(min_value=Decimal("-100000"), max_value=Decimal("100000"), places=3, allow_nan=False)
grams = st.decimals(min_value=Decimal("-100000000"), max_value=Decimal("100000000"), places=6, allow_nan=False)


def test_nit_quantities() -> None:
    assert to_base(Decimal("120"), "kg", FLOUR) == Decimal("120000")
    assert to_base(Decimal("19.5"), "L", OIL) == Decimal("19500")
    assert to_base(Decimal("1.2"), "kg", FLOUR) == Decimal("1200")
    assert from_base(Decimal("120000.000000"), "kg", FLOUR) == Decimal("120")
    assert str(from_base(Decimal("19500.000000"), "L", OIL)) == "19.5"
    assert str(from_base(Decimal("3800"), "kg", FLOUR)) == "3.8"


@given(kilos)
def test_kg_round_trip_is_exact(q: Decimal) -> None:
    assert from_base(to_base(q, "kg", FLOUR), "kg", FLOUR) == q


@given(kilos)
def test_litre_round_trip_is_exact(q: Decimal) -> None:
    assert from_base(to_base(q, "L", OIL), "L", OIL) == q


@given(grams)
def test_base_unit_is_identity(q: Decimal) -> None:
    assert to_base(q, "g", FLOUR) == q
    assert to_base(from_base(q, "kg", FLOUR), "kg", FLOUR) == q


@given(st.integers(min_value=0, max_value=10**9), st.integers(min_value=1, max_value=500))
def test_carton_split_recombines(packets: int, per_carton: int) -> None:
    split = split_into_cartons(packets, per_carton)
    assert split.full_cartons * per_carton + split.loose == packets
    assert 0 <= split.loose < per_carton


@given(st.integers(min_value=0, max_value=10**6), st.integers(min_value=1, max_value=500))
def test_carton_to_base_uses_the_pack_spec_factor(cartons: int, per_carton: int) -> None:
    assert to_base(Decimal(cartons), CARTON, MURUKKU, units_per_carton=per_carton) == cartons * per_carton


def test_benchmark_carton_splits() -> None:
    assert split_into_cartons(188, 20) == split_into_cartons(Decimal(188), 20)
    assert (split_into_cartons(188, 20).full_cartons, split_into_cartons(188, 20).loose) == (9, 8)
    assert (split_into_cartons(150, 20).full_cartons, split_into_cartons(150, 20).loose) == (7, 10)
    assert (split_into_cartons(88, 20).full_cartons, split_into_cartons(88, 20).loose) == (4, 8)
    # 500 g pack, 12 per carton: a different pack spec version, no code change
    assert (split_into_cartons(100, 12).full_cartons, split_into_cartons(100, 12).loose) == (8, 4)


def test_carton_without_pack_spec_is_refused() -> None:
    with pytest.raises(UomError) as err:
        to_base(Decimal(2), CARTON, MURUKKU)
    assert err.value.code == "carton_needs_pack_spec"


@pytest.mark.parametrize(
    ("qty", "unit", "item"),
    [
        (Decimal(1), "kg", OIL),  # mass into a volume item, no density
        (Decimal(1), "L", FLOUR),  # volume into a mass item
        (Decimal(1), "packet", FLOUR),  # count into mass
        (Decimal(1), "kg", MURUKKU),  # mass into count
    ],
)
def test_cross_dimension_is_refused(qty: Decimal, unit: str, item: ItemUnits) -> None:
    with pytest.raises(UomError) as err:
        to_base(qty, unit, item)
    assert err.value.code == "cross_dimension"


def test_mass_to_volume_with_an_explicit_density_multiplies() -> None:
    assert to_base(Decimal("1"), "kg", OIL_WITH_DENSITY) == Decimal("1098.901000")


def test_display_across_dimensions_is_refused() -> None:
    with pytest.raises(UomError):
        from_base(Decimal(1000), "L", FLOUR)


@pytest.mark.parametrize("bad", [1.5, "1.5", None, True])
def test_non_decimal_is_refused(bad: object) -> None:
    with pytest.raises(UomError) as err:
        to_base(bad, "kg", FLOUR)  # type: ignore[arg-type]
    assert err.value.code == "not_decimal"


def test_too_precise_is_refused_not_rounded() -> None:
    with pytest.raises(UomError) as err:
        to_base(Decimal("0.0000001"), "g", FLOUR)
    assert err.value.code == "too_precise"


def test_fractional_pieces_are_refused() -> None:
    with pytest.raises(UomError) as err:
        to_base(Decimal("1.5"), "packet", MURUKKU)
    assert err.value.code == "fractional_count"


def test_unknown_unit_and_infinity() -> None:
    with pytest.raises(UomError):
        to_base(Decimal(1), "tonne", FLOUR)
    with pytest.raises(UomError):
        to_base(Decimal("Infinity"), "kg", FLOUR)
