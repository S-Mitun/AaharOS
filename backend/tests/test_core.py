from decimal import Decimal

import pytest

from app.core.explained import Explained, ExplainedInput, SourceRef
from app.core.money import round_money, round_unit_cost, to_paise


def test_round_money_half_up_to_paise() -> None:
    assert round_money(Decimal("187.505")) == Decimal("187.51")
    assert round_money(Decimal("187.504")) == Decimal("187.50")
    assert round_money(Decimal("-0.005")) == Decimal("-0.01")


def test_unit_cost_keeps_six_places() -> None:
    assert round_unit_cost(Decimal(5855) / Decimal(188)) == Decimal("31.143617")


def test_to_paise() -> None:
    assert to_paise(Decimal("7875")) == 787500


def test_float_is_rejected() -> None:
    with pytest.raises(TypeError):
        round_money(187.5)  # type: ignore[arg-type]


def test_explained_serialises_decimals_as_strings() -> None:
    e = Explained(
        value=Decimal("31.14"),
        unit="INR/packet",
        formula="run_cost / good_packets",
        inputs=(ExplainedInput("run cost", Decimal("5855.00"), "INR", SourceRef("production_run", "B-001")),),
        method="WAC",
    )
    out = e.to_json()
    assert out["value"] == "31.14"
    assert out["inputs"][0]["value"] == "5855.00"
    assert out["inputs"][0]["source"] == {"type": "production_run", "id": "B-001"}


def test_sacred_digest_detects_any_edit() -> None:
    from app.core.config import get_settings
    from app.core.oracle import load_oracle, sacred_digest

    oracle = load_oracle(get_settings().oracle_path)
    before = sacred_digest(oracle)
    oracle["nit_expected"]["outstanding_A"] = Decimal("3875.01")
    assert sacred_digest(oracle) != before
