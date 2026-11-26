"""Traceability rules without a database (MP13, ADR-0020): the "may contain" window (T2), exposure and the notice."""

import random
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.traceability import domain
from app.modules.traceability.domain import NoticeFacts, Shipment, StoreEvent

D = Decimal


def ev(key: str, at: int, qty: str, brings: tuple[str, ...] = (), carries: tuple[str, ...] = ()) -> StoreEvent:
    return StoreEvent(key, at, D(qty), frozenset(brings), carries)


def test_a_lot_is_in_every_issue_until_the_store_runs_out() -> None:
    r = domain.may_contain(
        [
            ev("open", 1, "10", ("opening",)),
            ev("rcv1", 2, "50", ("FL-1",)),
            ev("i1", 3, "-30"),
            ev("i2", 4, "-30"),  # the store is empty now: opening stock and FL-1 are used up
            ev("rcv2", 5, "40", ("FL-2",)),
            ev("i3", 6, "-25"),
        ]
    )
    assert r.candidates["i1"] == {"opening", "FL-1"}
    assert r.candidates["i2"] == {"opening", "FL-1"}
    assert r.candidates["i3"] == {"FL-2"}  # FL-1 cannot be in a batch made after the store ran out
    assert r.still_present == {"FL-2"}


def test_without_running_out_every_lot_stays_possible() -> None:
    r = domain.may_contain(
        [ev("rcv1", 1, "50", ("FL-1",)), ev("i1", 2, "-40"), ev("rcv2", 3, "50", ("FL-2",)), ev("i2", 4, "-40")]
    )
    assert r.candidates["i2"] == {"FL-1", "FL-2"}  # 10 g of FL-1 may still have been in the store


def test_a_return_brings_back_what_its_issue_may_have_held() -> None:
    r = domain.may_contain(
        [
            ev("rcv1", 1, "20", ("FL-1",)),
            ev("i1", 2, "-20"),  # empty
            ev("ret", 3, "5", carries=("i1",)),  # 5 g of the FL-1 issue come back
            ev("rcv2", 4, "20", ("FL-2",)),
            ev("i2", 5, "-25"),
        ]
    )
    assert r.candidates["i2"] == {"FL-1", "FL-2"}


def test_moves_at_the_same_instant_are_read_conservatively() -> None:
    # the order inside one instant is unknown: the receipt may have come before the issue
    r = domain.may_contain([ev("rcv1", 1, "10", ("FL-1",)), ev("i1", 2, "-10"), ev("rcv2", 2, "10", ("FL-2",))])
    assert r.candidates["i1"] == {"FL-1", "FL-2"}


def test_nothing_received_means_nothing_contained() -> None:
    r = domain.may_contain([ev("i1", 1, "-5")])
    assert r.candidates["i1"] == frozenset() and r.still_present == frozenset()


# ---------- the window never misses a batch, whatever order the floor used the sacks in ----------

op = st.one_of(
    st.tuples(st.just("receive"), st.integers(1, 30)),
    st.tuples(st.just("issue"), st.integers(1, 40)),
    st.tuples(st.just("return"), st.integers(1, 10)),
)


@settings(max_examples=300, deadline=None)
@given(ops=st.lists(op, min_size=1, max_size=25), picks=st.randoms(use_true_random=False), ties=st.booleans())
def test_the_window_never_misses_a_lot_that_was_used(
    ops: list[tuple[str, int]], picks: random.Random, ties: bool
) -> None:
    store: dict[str, int] = {}  # what is physically in the store: lot -> grams
    taken: dict[str, dict[str, int]] = {}  # issue key -> lot -> grams it actually took (any order the floor likes)
    events: list[StoreEvent] = []
    clock = 0
    for n, (kind, qty) in enumerate(ops):
        clock += 0 if ties and picks.random() < 0.3 else 1
        if kind == "receive":
            store[f"L{n}"] = qty
            events.append(StoreEvent(f"r{n}", clock, D(qty), frozenset({f"L{n}"})))
        elif kind == "issue":
            want = min(qty, sum(store.values()))
            if want == 0:
                continue
            got: dict[str, int] = {}
            left = want
            while left:
                lot = picks.choice(sorted(lot for lot, g in store.items() if g > 0))
                take = min(left, store[lot], picks.randint(1, left))
                store[lot] -= take
                got[lot] = got.get(lot, 0) + take
                left -= take
            taken[f"i{n}"] = got
            events.append(StoreEvent(f"i{n}", clock, D(-want)))
        elif taken:
            src = picks.choice(sorted(taken))
            lot = picks.choice(sorted(taken[src]))
            back = min(qty, taken[src][lot])
            if back == 0:
                continue
            taken[src][lot] -= back
            store[lot] = store.get(lot, 0) + back
            events.append(StoreEvent(f"b{n}", clock, D(back), carries_from=(src,)))
    result = domain.may_contain(events)
    for key, got in taken.items():
        assert set(got) <= result.candidates[key], (key, got, result.candidates[key])
    assert {lot for lot, g in store.items() if g > 0} <= result.still_present


# ---------- exposure and the draft notice ----------


def ship(cust: str, no: str, lot: str, n: int, on: date = date(2026, 11, 20)) -> Shipment:
    return Shipment(f"id-{cust}", cust, f"DEMO {cust}", f"d-{no}", no, on, f"AHR/{no}", lot, n)


def test_exposure_groups_packets_per_customer_with_invoices() -> None:
    rows = domain.exposure(
        [ship("RET-A", "1", "B-001-1", 100), ship("RET-A", "2", "B-002-1", 20), ship("RET-C", "3", "B-001-1", 30)]
    )
    assert [(e.customer_code, e.packets.value) for e in rows] == [("RET-A", D(120)), ("RET-C", D(30))]
    assert rows[0].invoice_nos == ("AHR/1", "AHR/2") and rows[0].lot_nos == ("B-001-1", "B-002-1")
    assert [i.source.type for i in rows[0].packets.inputs if i.source] == ["dispatch", "dispatch"]


def test_the_notice_is_marked_as_a_demo_and_names_every_customer() -> None:
    customers = domain.exposure([ship("RET-A", "1", "B-001-1", 100)])
    text = domain.draft_notice(
        NoticeFacts(
            factory="DEMO Snacks",
            fssai_no="10000000000000 (DEMO)",
            subject="supplier lot FL-1 of flour",
            lot_nos=["B-001-1"],
            best_before=[date(2027, 2, 19)],
            reason="DEMO test",
            customers=customers,
            on_hand=D(88),
        )
    )
    assert text.startswith(domain.DEMO_BANNER) and text.endswith(domain.DEMO_BANNER)
    assert "DEMO Retailer RET-A (RET-A): 100 packets, invoices AHR/1" not in text
    assert "DEMO RET-A (RET-A): 100 packets, invoices AHR/1, lots B-001-1" in text
    assert "2027-02-19" in text and "88 packets" in text


def test_a_notice_with_no_dispatches_says_so() -> None:
    text = domain.draft_notice(NoticeFacts("DEMO", None, "batch lot X", [], [], "DEMO"))
    assert "no packets of these lots have been dispatched" in text and "FSSAI licence: not set" in text


# ---------- T6: oil and fill weights ----------


def test_daily_oil_above_the_threshold_needs_records() -> None:
    uses = [domain.OilUse("r1", "B-001", D(30000), D(5000)), domain.OilUse("r2", "B-002", D(20000), D(0))]
    day = domain.oil_day(date(2026, 11, 21), uses, D(50))
    assert day.litres.value == D(55) and day.above_threshold is True
    assert [i.label for i in day.litres.inputs] == ["B-001 fresh oil", "B-001 top-ups", "B-002 fresh oil"]
    exactly = domain.oil_day(date(2026, 11, 21), [domain.OilUse("r1", "B-001", D(50000), D(0))], D(50))
    assert exactly.above_threshold is False  # "above", not "at"


def test_tpc_above_the_limit_means_discard() -> None:
    assert domain.tpc_discard(D("25.1"), D(25)) and not domain.tpc_discard(D(25), D(25))
    assert not domain.tpc_discard(None, D(25))  # not measured is not a flag


def test_fill_check_giveaway_and_short_fills() -> None:
    c = domain.fill_check(
        run_id="r1",
        run_no="B-001",
        declared_g=D(200),
        nets=[D(204), D(206), D(190)],
        good_units=100,
        ingredient_value=D("3430.00"),
        expected_bulk_g=D(40000),
        tolerance_g=D(9),
    )
    assert c.mean_net.value == D("200") and c.over_per_packet.value == D(0)
    assert c.giveaway.value == D("0.00") and c.short == (D(190),) and c.short_limit_g == D(191)
    over = domain.fill_check(
        run_id="r1",
        run_no="B-001",
        declared_g=D(200),
        nets=[D(205)],
        good_units=188,
        ingredient_value=D("3435.00"),
        expected_bulk_g=D(40000),
        tolerance_g=None,
    )
    assert over.cost_per_kg.value == D("85.875") and over.giveaway.value == D("80.72")  # 5 x 188 / 1000 x 85.875
    assert over.short == () and over.short_limit_g is None  # no tolerance configured for this size


def test_fill_check_needs_samples() -> None:
    with pytest.raises(ValueError):
        domain.fill_check(
            run_id="r",
            run_no="B",
            declared_g=D(200),
            nets=[],
            good_units=1,
            ingredient_value=D(1),
            expected_bulk_g=D(1),
            tolerance_g=None,
        )


# ---------- T5: the freshness radar ----------


def od(day: int, n: int) -> domain.OrderDay:
    return domain.OrderDay(date(2026, 11, day), n)


def ld(lot: str, bb: date | None, day: int, n: int) -> domain.LotDelivery:
    return domain.LotDelivery(lot, lot, bb, date(2026, 11, day), n, f"d-{lot}-{day}", f"DSP-{day}")


def test_selling_rates_from_the_order_rhythm() -> None:
    assert domain.selling_rates([od(1, 30)]) is None  # one order: not enough history
    assert domain.selling_rates([od(1, 30), od(1, 10)]) is None  # one order day
    r = domain.selling_rates([od(1, 30), od(2, 30), od(5, 30)])
    assert r is not None and (r.central, r.slow, r.fast) == (D(15), D(10), D(30))  # 60 / 4 days; 30 / 3; 30 / 1
    assert (r.orders, r.span_days) == (3, 4)


def test_the_oldest_best_before_is_counted_as_sold_first() -> None:
    sent = [ld("NEW", date(2027, 3, 1), 3, 50), ld("OLD", date(2027, 1, 1), 1, 50), ld("OPEN", None, 1, 10)]
    left = domain.on_shelf(sent, D(10), date(2026, 11, 7))  # 6 days x 10 = 60 sold: OPEN 10, then OLD 50
    assert left == {"OPEN": D(0), "OLD": D(0), "NEW": D(50)}
    assert domain.on_shelf(sent, None, date(2026, 11, 7)) == {"OPEN": D(10), "OLD": D(50), "NEW": D(50)}
    assert sum(domain.on_shelf(sent, D(100), date(2026, 11, 30)).values()) == 0  # never below zero


def test_a_lot_near_best_before_is_flagged_only_if_it_may_be_on_the_shelf() -> None:
    bb = date(2026, 11, 20)
    rates, est = domain.shelf_estimates([ld("B-1", bb, 1, 80)], [od(1, 80)], date(2026, 11, 10), 15)
    assert rates is None and est[0].flagged and est[0].high.value == D(80) and est[0].low == 0
    assert est[0].central is None and "not enough history" in est[0].high.formula
    assert est[0].days_to_best_before == 10
    sold = domain.shelf_estimates([ld("B-1", bb, 1, 40)], [od(1, 40), od(3, 40), od(5, 40)], date(2026, 11, 10), 15)[1][
        0
    ]
    assert sold.high.value == D(0) and not sold.flagged  # 20 a day at the slowest: sold out long before
    far = domain.shelf_estimates([ld("B-1", date(2027, 2, 1), 1, 80)], [od(1, 80)], date(2026, 11, 10), 15)[1][0]
    assert far.high.value == D(80) and not far.flagged  # on the shelf, but nowhere near its best-before
    ranged = domain.shelf_estimates(
        [ld("B-1", bb, 1, 30), ld("B-2", bb, 2, 30), ld("B-3", bb, 5, 30)],
        [od(1, 30), od(2, 30), od(5, 30)],
        date(2026, 11, 7),
        15,
    )[1]
    total = {e.lot_no: (e.low, e.central, int(e.high.value)) for e in ranged}
    assert sum(h for _, _, h in total.values()) == 30 and sum(c or 0 for _, c, _ in total.values()) == 0
    assert all(lo <= (c or 0) <= h for lo, c, h in total.values())
