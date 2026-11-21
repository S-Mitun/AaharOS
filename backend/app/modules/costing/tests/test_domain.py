"""The standard cost per unit, pulled forward from MP07 for the opening FG lot (MP05, decision D3)."""

from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.modules.costing.domain import StandardLine, standard_cost

D = Decimal


def test_nit_standard_cost_is_derived_not_copied() -> None:
    lines = [
        StandardLine("flour", D(40), D(42)),
        StandardLine("cooking_oil", D(10), D(140)),
        StandardLine("spice_mix", D("1.2"), D(200)),
        StandardLine("pouch_200g", D(200), D("2.50")),
        StandardLine("carton_20", D(10), D(15)),
    ]
    std = standard_cost(lines, D(1200) + D(600), D(200))
    assert (std.materials_per_batch, std.total_per_batch, std.per_unit) == (D("3970.00"), D("5770.00"), D("28.850000"))


def test_expected_output_must_be_positive() -> None:
    with pytest.raises(DomainError):
        standard_cost([], D(0), D(0))
