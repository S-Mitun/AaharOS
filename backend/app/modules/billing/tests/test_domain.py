"""Pure billing rules (MP10): numbers, packets to invoice, MSME due dates, credit note limits and tax."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.modules.billing.domain import (
    BillingError,
    CreditLineIn,
    InvoiceLineTaxes,
    credit_note_no,
    due_date,
    invoice_no,
    plan_credit_note,
    to_invoice,
)

D = Decimal
ITEM = uuid.uuid4()


def test_numbers() -> None:
    assert invoice_no("26-27", 1) == "AHR/26-27/000001"
    assert len(invoice_no("26-27", 999999)) == 16
    assert credit_note_no("26-27", 7) == "CN/26-27/000007"
    with pytest.raises(ValueError):
        invoice_no("26-27", 0)


def test_packets_to_invoice() -> None:
    assert to_invoice({ITEM: 150}, {}) == {ITEM: 150}
    assert to_invoice({ITEM: 238}, {ITEM: 200}) == {ITEM: 38}
    with pytest.raises(BillingError) as e:
        to_invoice({ITEM: 150}, {ITEM: 150})
    assert e.value.code == "nothing_to_invoice"


def test_msme_due_dates() -> None:
    day = date(2026, 11, 21)
    assert due_date(day, 30, msme=False) == date(2026, 12, 21)
    assert due_date(day, 60, msme=True) == date(2027, 1, 5)  # capped at 45 days
    assert due_date(day, 0, msme=True) == date(2026, 12, 6)  # 15 days when no term is agreed
    assert due_date(day, 0, msme=False) == day


INVOICE_LINE = {1: InvoiceLineTaxes(1, D("7500.00"), D(0), (("CGST", D("2.5")), ("SGST", D("2.5"))))}


def test_credit_note_tax_follows_the_invoice_line() -> None:
    (line,) = plan_credit_note([CreditLineIn(1, 150, D("2.00"))], INVOICE_LINE)
    assert line.taxable == D("300.00")
    assert line.taxes == (("CGST", D("2.5"), D("7.50")), ("SGST", D("2.5"), D("7.50")))


def test_credit_note_cannot_exceed_what_is_left() -> None:
    credited = {1: InvoiceLineTaxes(1, D("7500.00"), D("7300.00"), (("IGST", D(5)),))}
    with pytest.raises(BillingError) as e:
        plan_credit_note([CreditLineIn(1, 5, D("50.00"))], credited)
    assert e.value.code == "credit_exceeds_invoice_line"
    for lines, code in (
        ([], "empty_credit_note"),
        ([CreditLineIn(9, 1, D(1))], "unknown_invoice_line"),
        ([CreditLineIn(1, 0, D(1))], "qty_not_positive"),
        ([CreditLineIn(1, 1, D("0.001"))], "bad_rate"),
        ([CreditLineIn(1, 1, D(1)), CreditLineIn(1, 1, D(1))], "duplicate_line"),
    ):
        with pytest.raises(BillingError) as e2:
            plan_credit_note(lines, INVOICE_LINE)
        assert e2.value.code == code
