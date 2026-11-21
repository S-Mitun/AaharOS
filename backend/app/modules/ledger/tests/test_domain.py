"""Pure journal-rule tests (MP04): balance per item and in value, derived roles, ordering, refusals, mirrors."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.modules.ledger.domain import (
    SOURCE_FOR_KIND,
    STANDARD_LOCATIONS,
    JournalDraft,
    JournalError,
    LedgerRow,
    LineSpec,
    build_journal,
    mirror_lines,
    position_deltas,
    with_running_balance,
)
from app.modules.uom.domain import ItemUnits

FLOUR, OIL, POUCH, MURUKKU = (uuid.uuid4() for _ in range(4))
ITEMS = {
    FLOUR: ItemUnits("g", "kg"),
    OIL: ItemUnits("mL", "L"),
    POUCH: ItemUnits("piece", "piece"),
    MURUKKU: ItemUnits("piece", "packet", lot_tracked=True),
}
LOCS = tuple(STANDARD_LOCATIONS)
DAY = date(2026, 11, 21)
LOT = uuid.uuid4()
D = Decimal


def journal(kind: str, lines: list[LineSpec], **kw: Any) -> JournalDraft:
    return build_journal(
        kind=kind,
        source_type=kw.pop("source_type", SOURCE_FOR_KIND.get(kind, "opening")),
        source_id=kw.pop("source_id", uuid.uuid4()),
        posting_date=DAY,
        lines=lines,
        items=ITEMS,
        locations=LOCS,
        **kw,
    )


def receipt(qty: str = "60", unit: str = "kg", value: str = "2700.00") -> list[LineSpec]:
    return [
        LineSpec(FLOUR, "SUPPLIER", -D(qty), unit, -D(value)),
        LineSpec(FLOUR, "RAW_STORE", D(qty), unit, D(value)),
    ]


def test_receipt_converts_to_base_and_orders_incoming_first() -> None:
    draft = journal("RECEIPT", receipt())
    assert [(ln.location, ln.qty_base, ln.value, ln.role) for ln in draft.lines] == [
        ("RAW_STORE", D(60000), D("2700.00"), "IN"),
        ("SUPPLIER", D(-60000), D("-2700.00"), "OUT"),
    ]
    assert [ln.line_no for ln in draft.lines] == [1, 2]


def test_nit_run_completion_balances_with_scrap() -> None:
    draft = journal(
        "RUN_COMPLETION",
        [
            LineSpec(POUCH, "PACK_STORE", D(-194), "piece", D("-485.00")),
            LineSpec(POUCH, "PRODUCTION", D(188), "piece", D("485.00")),
            LineSpec(POUCH, "SCRAP", D(6), "piece"),
            LineSpec(MURUKKU, "PRODUCTION", D(-188), "packet", D("-485.00"), lot_id=LOT),
            LineSpec(MURUKKU, "FG_STORE", D(188), "packet", D("485.00"), lot_id=LOT),
        ],
    )
    roles = {(ln.item_id, ln.location): ln.role for ln in draft.lines}
    assert roles[(POUCH, "SCRAP")] == "SCRAP_IN"
    assert roles[(POUCH, "PACK_STORE")] == "OUT"
    assert [ln.qty_base > 0 for ln in draft.lines] == [True, True, True, False, False]


def test_unbalanced_quantity_is_refused() -> None:
    lines = receipt()
    lines[1] = LineSpec(FLOUR, "RAW_STORE", D(59), "kg", D("2700.00"))
    with pytest.raises(JournalError) as err:
        journal("RECEIPT", lines)
    assert err.value.code == "unbalanced_quantity"


def test_mixed_units_balance_after_conversion() -> None:
    draft = journal(
        "RECEIPT",
        [LineSpec(FLOUR, "SUPPLIER", D(-60), "kg", D("-1.00")), LineSpec(FLOUR, "RAW_STORE", D(60000), "g", D("1.00"))],
    )
    assert sum(ln.qty_base for ln in draft.lines) == 0


def test_unbalanced_value_is_refused() -> None:
    with pytest.raises(JournalError) as err:
        journal("RECEIPT", receipt()[:1] + [LineSpec(FLOUR, "RAW_STORE", D(60), "kg", D("2700.01"))])
    assert err.value.code == "unbalanced_value"


def test_value_must_already_be_rounded_to_paise() -> None:
    with pytest.raises(JournalError) as err:
        journal("RECEIPT", receipt(value="2700.005"))
    assert err.value.code == "value_not_rounded"


@pytest.mark.parametrize("bad", [60.0, "60"])
def test_float_or_text_quantity_is_refused(bad: Any) -> None:
    lines = [LineSpec(FLOUR, "SUPPLIER", bad, "kg"), LineSpec(FLOUR, "RAW_STORE", D(60), "kg")]
    with pytest.raises(DomainError) as err:
        journal("RECEIPT", lines)
    assert err.value.code == "not_decimal"


def test_float_value_is_refused() -> None:
    minus: Any = -2.5
    plus: Any = 2.5
    lines = [LineSpec(FLOUR, "SUPPLIER", D(-1), "kg", minus), LineSpec(FLOUR, "RAW_STORE", D(1), "kg", plus)]
    with pytest.raises(DomainError) as err:
        journal("RECEIPT", lines)
    assert err.value.code == "not_decimal"


def test_sign_mismatch_is_refused() -> None:
    lines = [LineSpec(FLOUR, "SUPPLIER", D(-1), "kg", D(1)), LineSpec(FLOUR, "RAW_STORE", D(1), "kg", D(-1))]
    with pytest.raises(JournalError) as err:
        journal("RECEIPT", lines)
    assert err.value.code == "sign_mismatch"


def test_value_only_lines_only_in_true_ups_and_reversals() -> None:
    lines = [
        LineSpec(MURUKKU, "CONVERSION_COST", D(0), "packet", D("-1800.00"), lot_id=LOT),
        LineSpec(MURUKKU, "FG_STORE", D(0), "packet", D("1800.00"), lot_id=LOT),
    ]
    assert {ln.role for ln in journal("COST_TRUE_UP", lines).lines} == {"VALUE_ONLY"}
    with pytest.raises(JournalError) as err:
        journal("RUN_COMPLETION", lines)
    assert err.value.code == "value_only_not_allowed"


def test_wrong_source_document_is_refused() -> None:
    with pytest.raises(JournalError) as err:
        journal("RECEIPT", receipt(), source_type="dispatch")
    assert err.value.code == "wrong_source"


def test_adjustment_needs_reason_and_approver() -> None:
    lines = [LineSpec(FLOUR, "RAW_STORE", D(-1), "kg"), LineSpec(FLOUR, "ADJUSTMENT", D(1), "kg")]
    with pytest.raises(JournalError) as err:
        journal("ADJUSTMENT", lines, approved_by=uuid.uuid4())
    assert err.value.code == "reason_required"
    with pytest.raises(JournalError) as err:
        journal("ADJUSTMENT", lines, reason="count difference")
    assert err.value.code == "approval_required"
    assert journal("ADJUSTMENT", lines, reason=" count ", approved_by=uuid.uuid4()).reason == "count"


def test_reversal_must_name_its_original() -> None:
    with pytest.raises(JournalError) as err:
        journal("REVERSAL", receipt(), reason="wrong supplier")
    assert err.value.code == "reversal_link"


def test_lot_tracked_item_needs_a_lot_and_unknowns_are_refused() -> None:
    no_lot = [LineSpec(MURUKKU, "OPENING", D(-5), "packet"), LineSpec(MURUKKU, "FG_STORE", D(5), "packet")]
    with pytest.raises(JournalError) as err:
        journal("OPENING", no_lot)
    assert err.value.code == "lot_required"
    with pytest.raises(JournalError) as err:
        journal("RECEIPT", [LineSpec(FLOUR, "MOON", D(-1), "kg"), LineSpec(FLOUR, "RAW_STORE", D(1), "kg")])
    assert err.value.code == "unknown_location"
    with pytest.raises(JournalError) as err:
        journal("RECEIPT", [])
    assert err.value.code == "no_lines"
    with pytest.raises(JournalError) as err:
        journal("SHRINKAGE", receipt(), source_type="opening")
    assert err.value.code == "unknown_kind"


def test_request_hash_ignores_the_unit_used() -> None:
    source = uuid.uuid4()
    a = journal("RECEIPT", receipt("60", "kg"), source_id=source)
    b = journal("RECEIPT", receipt("60000", "g"), source_id=source)
    assert a.request_hash() == b.request_hash()
    c = journal("RECEIPT", receipt("61", "kg", "2745.00"), source_id=source)
    assert c.request_hash() != a.request_hash()


def test_mirror_reverses_every_delta_exactly() -> None:
    draft = journal("RECEIPT", receipt())
    mirrored = journal(
        "REVERSAL",
        mirror_lines(draft.lines, ITEMS),
        reason="supplier sent the wrong grade",
        reverses_journal_id=uuid.uuid4(),
    )
    before = position_deltas(draft.lines)
    after = position_deltas(mirrored.lines)
    assert {k: (q + after[k][0], v + after[k][1]) for k, (q, v) in before.items()} == {k: (D(0), D(0)) for k in before}


def test_running_balance_starts_from_opening() -> None:
    j = uuid.uuid4()
    rows = [
        LedgerRow(j, n, FLOUR, "RAW_STORE", None, DAY, "ISSUE", "material_issue", j, D(q), D(v))
        for n, (q, v) in enumerate([("60000", "2700"), ("-40000", "-1725")], start=1)
    ]
    out = with_running_balance(rows, {FLOUR: (D(100000), D(4200))})
    assert [(r.running_qty_base, r.running_value) for r in out] == [(D(160000), D(6900)), (D(120000), D(5175))]


# Any set of moves built as (from, to) pairs balances; breaking one line's quantity always fails.
moves = st.lists(
    st.tuples(
        st.sampled_from([FLOUR, OIL, POUCH]),
        st.sampled_from(["RAW_STORE", "PACK_STORE", "WIP", "SUPPLIER", "ADJUSTMENT"]),
        st.sampled_from(["RAW_STORE", "PACK_STORE", "WIP", "PRODUCTION", "CUSTOMER"]),
        st.integers(min_value=1, max_value=10**7),
        st.integers(min_value=0, max_value=10**7),
    ),
    min_size=1,
    max_size=8,
)


@given(moves, st.integers(min_value=0, max_value=15))
def test_paired_moves_always_balance_and_a_broken_line_never_does(
    pairs: list[tuple[uuid.UUID, str, str, int, int]], which: int
) -> None:
    lines: list[LineSpec] = []
    for item, src, dst, qty, paise in pairs:
        unit = ITEMS[item].base_uom
        value = D(paise) / 100
        lines += [LineSpec(item, src, -D(qty), unit, -value), LineSpec(item, dst, D(qty), unit, value)]
    approver = uuid.uuid4()
    draft = journal("ADJUSTMENT", lines, reason="property test", approved_by=approver)
    by_item: dict[uuid.UUID, Decimal] = {}
    for ln in draft.lines:
        by_item[ln.item_id] = by_item.get(ln.item_id, D(0)) + ln.qty_base
    assert set(by_item.values()) == {D(0)}
    assert sum(ln.value for ln in draft.lines) == 0
    i = which % len(lines)
    broken = list(lines)
    broken[i] = LineSpec(lines[i].item_id, lines[i].location, lines[i].qty + 1, lines[i].unit, lines[i].value)
    with pytest.raises(JournalError):
        journal("ADJUSTMENT", broken, reason="property test", approved_by=approver)
