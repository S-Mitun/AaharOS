"""Pure purchase-receipt rules (MP05), the financial year and the idempotency request hash."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.calendar import financial_year
from app.core.idempotency import request_hash
from app.modules.procurement.domain import ReceiptError, ReceiptLineIn, plan_receipt, receipt_no, request_doc
from app.modules.uom.domain import ItemUnits

D = Decimal
FLOUR, POUCH, MURUKKU = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ITEMS = {
    FLOUR: (ItemUnits("g", "kg"), "RAW"),
    POUCH: (ItemUnits("piece", "piece"), "PACK"),
    MURUKKU: (ItemUnits("piece", "packet", lot_tracked=True), "FG"),
}


def test_nit_purchase() -> None:
    (line,) = plan_receipt([ReceiptLineIn(FLOUR, D(60), "kg", D(45))], ITEMS)
    assert (line.qty_base, line.accepted_base, line.value, line.store) == (
        D(60000),
        D(60000),
        D("2700.00"),
        "RAW_STORE",
    )


def test_rejected_qty_and_freight_stay_out_of_stock_value() -> None:
    (line,) = plan_receipt(
        [ReceiptLineIn(POUCH, D(500), "piece", D("2.50"), freight=D("40.00"), rejected_qty=D(20), lot_no=" P-77 ")],
        ITEMS,
    )
    assert (line.accepted_base, line.rejected_base) == (D(480), D(20))
    assert line.value == D("1200.00")  # 480 x 2.50; the 40.00 freight is recorded, not in stock value
    assert (line.freight, line.lot_no, line.store) == (D("40.00"), "P-77", "PACK_STORE")


@pytest.mark.parametrize(
    ("line", "code"),
    [
        (ReceiptLineIn(MURUKKU, D(1), "packet", D(1)), "not_purchasable"),
        (ReceiptLineIn(FLOUR, D(0), "kg", D(45)), "qty_not_positive"),
        (ReceiptLineIn(FLOUR, D(1), "kg", D(45), rejected_qty=D(2)), "bad_rejection"),
        (ReceiptLineIn(FLOUR, D(1), "kg", D("45.0000001")), "too_precise"),
        (ReceiptLineIn(FLOUR, D(1), "kg", D(45), freight=D("0.001")), "too_precise"),
        (ReceiptLineIn(FLOUR, D(1), "kg", D(45), rejected_qty=D(1)), "nothing_accepted"),
        (
            ReceiptLineIn(FLOUR, D(1), "kg", D(45), mfg_date=date(2026, 11, 20), best_before=date(2026, 11, 1)),
            "dates_out_of_order",
        ),
    ],
)
def test_refusals(line: ReceiptLineIn, code: str) -> None:
    with pytest.raises(ReceiptError) as err:
        plan_receipt([line], ITEMS)
    assert err.value.code == code


def test_no_lines_and_cross_dimension() -> None:
    with pytest.raises(ReceiptError):
        plan_receipt([], ITEMS)
    with pytest.raises(Exception) as err:
        plan_receipt([ReceiptLineIn(FLOUR, D(1), "L", D(45))], ITEMS)
    assert getattr(err.value, "code", None) == "cross_dimension"


def test_receipt_number_and_financial_year() -> None:
    assert financial_year(date(2026, 11, 21)) == "26-27"
    assert financial_year(date(2027, 3, 31)) == "26-27"
    assert financial_year(date(2027, 4, 1)) == "27-28"
    assert receipt_no("26-27", 1) == "GRN/26-27/000001"
    assert len(receipt_no("26-27", 999999)) == 16


def test_request_hash_is_unit_independent() -> None:
    supplier = uuid.uuid4()
    kg = plan_receipt([ReceiptLineIn(FLOUR, D(60), "kg", D(45))], ITEMS)
    grams = plan_receipt([ReceiptLineIn(FLOUR, D(60000), "g", D("0.045"))], ITEMS)
    day = date(2026, 11, 21)
    assert request_hash(request_doc(supplier, "INV-1", day, kg)) == request_hash(
        request_doc(supplier, " INV-1 ", day, grams)
    )
    other = plan_receipt([ReceiptLineIn(FLOUR, D(61), "kg", D(45))], ITEMS)
    assert request_hash(request_doc(supplier, "INV-1", day, kg)) != request_hash(
        request_doc(supplier, "INV-1", day, other)
    )


def test_request_hash_refuses_floats() -> None:
    with pytest.raises(TypeError):
        request_hash({"qty": 1.5})
