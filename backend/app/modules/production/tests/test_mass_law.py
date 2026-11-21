"""Law 3 (MP11, ADR-0018 K4): mass reconciles with the gap disclosed; good output backed by the ledger; flagged."""

from decimal import Decimal

from app.modules.production.domain import MassBalance, PackedMass, mass_balance, mass_law

D = Decimal


def nit_b001() -> MassBalance:
    # 40 kg expected bulk; 188 good x 200 g = 37.6 kg; no scrap or loss recorded -> 2.4 kg unexplained
    return mass_balance(D(40000), D(0), [PackedMass("MURUKKU-200G", 188, D(200), None)], D(0), D(0))


def test_nit_b001_holds_and_is_flagged() -> None:
    v = mass_law(nit_b001(), ledger_good_g=D(37600), tolerance_pct=D(3))
    assert (v.reconciles, v.backed_by_ledger, v.holds) == (True, True, True)
    assert (v.gap_g, v.gap_pct, v.flagged) == (D(2400), D(6), True)


def test_good_output_must_match_the_ledger() -> None:
    v = mass_law(nit_b001(), ledger_good_g=D(37400), tolerance_pct=D(3))
    assert v.backed_by_ledger is False and v.holds is False


def test_a_small_gap_is_not_flagged() -> None:
    small = mass_balance(D(40000), D(0), [PackedMass("P", 199, D(200), None)], D(100), D(50))
    v = mass_law(small, ledger_good_g=D(39800), tolerance_pct=D(3))
    assert (v.holds, v.gap_g, v.flagged) == (True, D(50), False)
