"""Traceability rules without a database (MP13, ADR-0020): the "may contain" window (T2), exposure and the notice."""

import random
from datetime import date
from decimal import Decimal

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
