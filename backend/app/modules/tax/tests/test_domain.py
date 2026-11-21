"""Pure GST rules (MP10, ADR-0017): regimes, per-line rounding, the header = Σ lines, rules by date, words."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.tax.domain import (
    Rule,
    TaxError,
    amount_in_words,
    regime,
    rule_on,
    state_label,
    tax_line,
    totals,
)

D = Decimal
FIVE = D(5)


def test_nit_invoice_a_tamil_nadu_to_tamil_nadu() -> None:
    line = tax_line(1, 150, D("50.00"), FIVE, regime("33", "33"))
    assert line.taxable == D("7500.00")
    assert [(t.tax, t.rate_pct, t.amount) for t in line.taxes] == [
        ("CGST", D("2.5"), D("187.50")),
        ("SGST", D("2.5"), D("187.50")),
    ]
    t = totals([line])
    assert (t.taxable, t.tax_total, t.round_off, t.total) == (D("7500.00"), D("375.00"), D("0.00"), D("7875.00"))


def test_nit_distributor_b_tamil_nadu_to_karnataka() -> None:
    assert regime("33", "29") == "INTER"
    full = tax_line(1, 120, D("50.00"), FIVE, "INTER")
    part = tax_line(1, 88, D("50.00"), FIVE, "INTER")
    assert [(t.tax, t.amount) for t in full.taxes] == [("IGST", D("300.00"))]
    assert totals([full]).total == D("6300.00")
    assert (part.taxable, part.taxes[0].amount, totals([part]).total) == (D("4400.00"), D("220.00"), D("4620.00"))


def test_a_rate_change_by_date() -> None:
    old = Rule(uuid.uuid4(), "21069099", D(12), date(2017, 7, 1), date(2025, 9, 21))
    new = Rule(uuid.uuid4(), "21069099", FIVE, date(2025, 9, 22), None)
    assert rule_on([old, new], "21069099", date(2025, 9, 21)) == old
    assert rule_on([old, new], "21069099", date(2025, 9, 22)) == new
    with pytest.raises(TaxError) as e:
        rule_on([old, new], "19059090", date(2026, 1, 1))
    assert e.value.code == "no_tax_rule"
    with pytest.raises(TaxError):
        rule_on([new], None, date(2026, 1, 1))


def test_rounding_edges_half_up_per_head() -> None:
    # 1 x 0.10 at 5%: CGST/SGST 0.0025 -> 0.00 each; IGST 0.005 -> 0.01 (half up)
    intra = tax_line(1, 1, D("0.10"), FIVE, "INTRA")
    assert [t.amount for t in intra.taxes] == [D("0.00"), D("0.00")]
    assert tax_line(1, 1, D("0.10"), FIVE, "INTER").taxes[0].amount == D("0.01")
    # 3 x 33.33 = 99.99 at 5%: 2.49975 -> 2.50 each half
    assert [t.amount for t in tax_line(1, 3, D("33.33"), FIVE, "INTRA").taxes] == [D("2.50"), D("2.50")]


def test_round_off_line_is_explicit() -> None:
    line = tax_line(1, 3, D("33.33"), FIVE, "INTRA")  # 99.99 + 5.00 = 104.99
    t = totals([line], round_to_rupee=True)
    assert (t.round_off, t.total) == (D("0.01"), D("105.00"))
    assert totals([line]).round_off == D("0.00")


def test_refusals() -> None:
    for call in (
        lambda: tax_line(1, 0, D(50), FIVE, "INTRA"),
        lambda: tax_line(1, 1, D(-1), FIVE, "INTRA"),
        lambda: tax_line(1, 1, D(50), D(101), "INTRA"),
        lambda: tax_line(1, 1, D(50), FIVE, "OTHER"),
        lambda: totals([]),
    ):
        with pytest.raises(TaxError):
            call()


@given(
    st.lists(
        st.tuples(st.integers(1, 5000), st.decimals(min_value=0, max_value=10000, places=2)), min_size=1, max_size=10
    ),
    st.sampled_from([D(0), D("0.25"), D(3), FIVE, D(12), D(18), D(28)]),
    st.sampled_from(["INTRA", "INTER"]),
    st.booleans(),
)
def test_header_is_exactly_the_sum_of_lines(
    rows: list[tuple[int, Decimal]], rate: Decimal, kind: str, round_to_rupee: bool
) -> None:
    lines = [tax_line(n, q, p, rate, kind) for n, (q, p) in enumerate(rows, start=1)]
    t = totals(lines, round_to_rupee)
    assert t.taxable == sum((ln.taxable for ln in lines), D(0))
    assert t.tax_total == sum((tx.amount for ln in lines for tx in ln.taxes), D(0))
    assert t.total == t.taxable + t.tax_total + t.round_off
    assert abs(t.round_off) <= D("0.50")
    if kind == "INTRA":
        assert t.by_tax["CGST"] == t.by_tax["SGST"]


def test_amount_in_words_indian_numbering() -> None:
    assert amount_in_words(D("7875.00")) == "Rupees Seven Thousand Eight Hundred Seventy Five Only"
    assert amount_in_words(D("123456.50")) == (
        "Rupees One Lakh Twenty Three Thousand Four Hundred Fifty Six and Fifty Paise Only"
    )
    assert amount_in_words(D("10000000")) == "Rupees One Crore Only"
    assert amount_in_words(D("0.05")) == "Rupees Zero and Five Paise Only"


def test_state_labels() -> None:
    assert (state_label("33"), state_label("29")) == ("33-Tamil Nadu", "29-Karnataka")
