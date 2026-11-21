"""MP04 gate: a Hypothesis state machine posts random stock movements through ledger.service into PostgreSQL.

Steps: receipts, issues, returns, run completions (with scrap), dispatches (some consuming a reservation),
adjustments, reversals, reservations and releases, Idempotency-Key replays and conflicts, and floats that must be
refused. Quantities arrive in mixed units (g / kg, mL / L, piece / packet / carton of 20).

A plain-Python model predicts every outcome. After every step:
  - the outcome matches the model (a step the model says must be refused is refused, and vice versa)
  - a refused step leaves the database exactly as it was
  - quantity conservation: every journal sums to zero per item and in value (law 1 re-summed from the lines)
  - the projection equals a rebuild from `stock_lines`, and equals the model
  - available >= 0 at every store (on hand minus active reservations); no store position is negative
  - no float anywhere: every quantity and value read back is a Decimal

Examples default to 500 (the MP04 gate); set AAHAR_SM_EXAMPLES to run more or fewer.
"""

import os
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule, run_state_machine_as_test
from sqlalchemy import Engine, select, text

from app.core.errors import ConflictError, DomainError
from app.modules.ledger import service as ledger
from app.modules.ledger.domain import LineSpec
from app.modules.ledger.models import InventoryBalance, Location, Reservation
from app.modules.valuation.domain import Pool, proportional_value
from tests.db.conftest import ITEMS, LOCATIONS, Tenant, make_user, scoped_session

D = Decimal
ZERO = D(0)
DAY = date(2026, 11, 21)
EXAMPLES = int(os.environ.get("AAHAR_SM_EXAMPLES", "500"))

RAW = ("flour", "oil", "spice")
PACK = ("pouch_200g", "carton_20")
FG = "murukku_200g"
HOME = {
    "flour": "RAW_STORE",
    "oil": "RAW_STORE",
    "spice": "RAW_STORE",
    "pouch_200g": "PACK_STORE",
    "carton_20": "PACK_STORE",
    FG: "FG_STORE",
}
LARGE = {"g": ("kg", 1000), "mL": ("L", 1000)}
BASE = {"flour": "g", "oil": "mL", "spice": "g", "pouch_200g": "piece", "carton_20": "piece", FG: "piece"}
STORES = {"RAW_STORE", "PACK_STORE", "WIP", "FG_STORE", "IN_TRANSIT"}

Pos = tuple[uuid.UUID, str, uuid.UUID | None]
Deltas = dict[Pos, tuple[Decimal, Decimal]]

ENGINES: dict[str, Engine] = {}
OUTCOMES: Counter[str] = Counter()  # vacuity guard: both paths must be exercised
APPROVER: list[uuid.UUID] = []

amounts = st.integers(min_value=1, max_value=60_000)  # base units of a raw item
counts = st.integers(min_value=1, max_value=300)  # pieces / packets
paise = st.integers(min_value=0, max_value=1_000_000)
big_unit = st.booleans()  # express the quantity in kg / L (or cartons) instead of the base unit
picks = st.integers(min_value=0, max_value=10_000)
pcts = st.integers(min_value=1, max_value=120)  # outgoing qty as % of what is held: mostly fits, sometimes not


def fast_tenant(owner: Engine) -> tuple[Tenant, uuid.UUID]:
    """A fresh DEMO tenant (same locations and items as conftest.make_tenant) plus one order line, in 4 statements.

    One tenant per example keeps every example independent, so Hypothesis can replay and shrink a failure.
    """
    org = uuid.uuid4()
    with owner.begin() as c:
        c.execute(
            text(
                "INSERT INTO organizations (id, code, name, kind, state_code)"
                " VALUES (:id, :code, 'DEMO state machine', 'BENCHMARK', '33')"
            ),
            {"id": org, "code": f"DEMO-SM-{org.hex[:12]}"},
        )
        locations = dict(
            c.execute(
                text(
                    "INSERT INTO locations (organization_id, code, name, kind)"
                    " SELECT :o, code, code, kind FROM unnest(CAST(:codes AS text[]), CAST(:kinds AS text[]))"
                    " AS t(code, kind) RETURNING code, id"
                ),
                {"o": org, "codes": list(LOCATIONS), "kinds": list(LOCATIONS.values())},
            )
            .tuples()
            .all()
        )
        items = dict(
            c.execute(
                text(
                    "INSERT INTO items (organization_id, code, name, kind, base_uom, stock_uom, lot_tracked)"
                    " SELECT :o, code, code, kind, b, s, l FROM unnest(CAST(:codes AS text[]),"
                    " CAST(:kinds AS text[]), CAST(:bases AS text[]), CAST(:stocks AS text[]),"
                    " CAST(:lots AS boolean[])) AS t(code, kind, b, s, l)"
                    " RETURNING code, id"
                ),
                {
                    "o": org,
                    "codes": list(ITEMS),
                    "kinds": [v[0] for v in ITEMS.values()],
                    "bases": [v[1] for v in ITEMS.values()],
                    "stocks": [v[2] for v in ITEMS.values()],
                    "lots": [v[3] for v in ITEMS.values()],
                },
            )
            .tuples()
            .all()
        )
        customer, line = c.execute(
            text(
                "WITH cu AS (INSERT INTO customers (organization_id, code, name, kind, state_code)"
                "   VALUES (:o, 'RET-A', 'DEMO Retailer A', 'RETAILER', '33') RETURNING id),"
                " so AS (INSERT INTO sales_orders (organization_id, order_no, order_date, customer_id)"
                "   SELECT :o, 'SO-1', '2026-11-21', id FROM cu RETURNING id),"
                " ol AS (INSERT INTO order_lines (organization_id, order_id, line_no, item_id, qty_requested,"
                "   price_captured) SELECT :o, id, 1, :fg, 1000, 50.00 FROM so RETURNING id)"
                " SELECT (SELECT id FROM cu), (SELECT id FROM ol)"
            ),
            {"o": org, "fg": items[FG]},
        ).one()
    return Tenant(org=org, items=items, locations=locations, customer=customer), line


def in_unit(item: str, qty_base: int, big: bool) -> tuple[Decimal, str, int | None]:
    """The same quantity, written in a mixed unit: 1234 g -> 1.234 kg; 40 packets -> 2 cartons."""
    base = BASE[item]
    if base in LARGE and big:
        unit, factor = LARGE[base]
        return D(qty_base) / factor, unit, None
    if item == FG and big and qty_base % 20 == 0:
        return D(qty_base // 20), "carton", 20
    return D(qty_base), "packet" if item == FG else base, None


class LedgerMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        owner, app = ENGINES["owner"], ENGINES["app"]
        self.t, self.order_line = fast_tenant(owner)
        self.s = scoped_session(app, self.t)
        self.item = self.t.items
        self.pos: dict[Pos, tuple[Decimal, Decimal]] = {}
        self.reservations: dict[uuid.UUID, tuple[Decimal, str]] = {}
        self.journals: list[dict[str, Any]] = []  # id, kind, deltas, reversed, replay (kwargs + key)
        self.lots: list[uuid.UUID] = []

    def teardown(self) -> None:
        self.s.close()

    # ---------- model ----------

    def held(self, pos: Pos) -> tuple[Decimal, Decimal]:
        return self.pos.get(pos, (ZERO, ZERO))

    def portion(self, pos: Pos, pct: int) -> int:
        """A quantity relative to the holding (always whole base units here), at least 1."""
        held = int(self.held(pos)[0])
        return max(1, held * pct // 100)

    def take_value(self, pos: Pos, qty_base: Decimal) -> Decimal:
        """Value leaving a position, by the same rule the books use (valuation.domain.proportional_value)."""
        q, v = self.held(pos)
        if q <= 0:
            return ZERO
        if qty_base > q:  # refused anyway (negative stock); any value will do
            return max(v, ZERO)
        return proportional_value(Pool(q, v), qty_base)

    def active_reserved(self, consumed: tuple[uuid.UUID, ...] = ()) -> Decimal:
        return sum(
            (q for rid, (q, status) in self.reservations.items() if status == "ACTIVE" and rid not in consumed), ZERO
        )

    def predict(self, deltas: Deltas, consumed: tuple[uuid.UUID, ...] = ()) -> tuple[bool, dict[Pos, Any]]:
        new = dict(self.pos)
        for k, (dq, dv) in deltas.items():
            q, v = new.get(k, (ZERO, ZERO))
            new[k] = (q + dq, v + dv)
        for k in deltas:
            if k[1] in STORES:
                q, v = new[k]
                if q < 0 or v < 0 or (q == 0 and v != 0):
                    return False, new
        fg_out = any(k[0] == self.item[FG] and k[1] == "FG_STORE" and dq < 0 for k, (dq, _) in deltas.items())
        if fg_out:
            on_hand = sum((q for k, (q, _) in new.items() if k[0] == self.item[FG] and k[1] == "FG_STORE"), ZERO)
            if on_hand - self.active_reserved(consumed) < 0:
                return False, new
        return True, new

    # ---------- driving the service ----------

    def post(self, kind: str, source_type: str, lines: list[LineSpec], deltas: Deltas, **kw: Any) -> bool:
        consumed = tuple(kw.get("consume_reservation_ids", ()))
        ok, new = self.predict(deltas, consumed)
        key = uuid.uuid4() if len(self.journals) % 2 == 0 else None
        call = {
            "organization_id": self.t.org,
            "actor_id": None,
            "kind": kind,
            "source_type": source_type,
            "source_id": uuid.uuid4(),
            "posting_date": DAY,
            "lines": lines,
            "idempotency_key": key,
            **kw,
        }
        result = self.attempt(lambda: ledger.post(self.s, **call), ok)
        if result is None:
            return False
        self.pos = new
        for rid in consumed:
            self.reservations[rid] = (self.reservations[rid][0], "CONSUMED")
        self.journals.append(
            {
                "id": result.journal_id,
                "kind": kind,
                "deltas": deltas,
                "reversed": False,
                "replay": call if key else None,
            }
        )
        return True

    def attempt(self, call: Callable[[], Any], ok: bool) -> Any:
        before = self.snapshot()  # read inside the step's transaction
        try:
            result = call()
        except DomainError as exc:
            self.s.rollback()
            assert not ok, f"refused although the model allows it: {exc.code}: {exc.message}"
            assert self.snapshot() == before, "a refused step changed the database"
            OUTCOMES[f"refused:{exc.code}"] += 1
            return None
        self.s.commit()
        assert ok, "posted although the model says it must be refused"
        OUTCOMES["accepted"] += 1
        return result

    def lines_for(
        self, item: str, moves: list[tuple[str, int, Decimal]], big: bool, lot: uuid.UUID | None = None
    ) -> tuple[list[LineSpec], Deltas]:
        """(location, signed base qty, signed value) -> LineSpecs in a mixed unit, plus their model deltas."""
        lines, deltas = [], {}
        for loc, qty_base, value in moves:
            qty, unit, per_carton = in_unit(item, abs(qty_base), big)
            sign = 1 if qty_base > 0 else -1
            lines.append(
                LineSpec(self.item[item], loc, sign * qty, unit, value, lot_id=lot, units_per_carton=per_carton)
            )
            key = (self.item[item], loc, lot)
            dq, dv = deltas.get(key, (ZERO, ZERO))
            deltas[key] = (dq + D(qty_base), dv + value)
        return lines, deltas

    def new_lot(self) -> uuid.UUID:
        return ledger.create_lot(
            self.s,
            organization_id=self.t.org,
            actor_id=None,
            item_id=self.item[FG],
            lot_no=f"B-{uuid.uuid4().hex[:8]}",
            source_type="production_run",
        )

    # ---------- rules ----------

    @rule(item=st.sampled_from(RAW + PACK), qty=amounts, cents=paise, big=big_unit, poison=st.integers(0, 11))
    def receive(self, item: str, qty: int, cents: int, big: bool, poison: int) -> None:
        if item in PACK:
            qty = qty % 500 + 1
        value = D(cents) / 100
        lines, deltas = self.lines_for(item, [(HOME[item], qty, value), ("SUPPLIER", -qty, -value)], big)
        if poison == 0:  # now and then the same receipt arrives with a float quantity: refused, nothing changes
            bad: Any = float(lines[0].qty)  # deliberately a float: the ledger must refuse it
            lines[0] = LineSpec(lines[0].item_id, lines[0].location, bad, lines[0].unit, lines[0].value)
            self.attempt(
                lambda: ledger.post(
                    self.s,
                    organization_id=self.t.org,
                    actor_id=None,
                    kind="RECEIPT",
                    source_type="purchase_receipt",
                    source_id=uuid.uuid4(),
                    posting_date=DAY,
                    lines=lines,
                ),
                False,
            )
            return
        self.post("RECEIPT", "purchase_receipt", lines, deltas)

    @rule(qty=counts, cents=paise, big=big_unit)
    def opening_fg(self, qty: int, cents: int, big: bool) -> None:
        lot = self.new_lot()
        value = D(cents) / 100
        lines, deltas = self.lines_for(FG, [("FG_STORE", qty, value), ("OPENING", -qty, -value)], big, lot)
        if self.post("OPENING", "opening", lines, deltas):
            self.lots.append(lot)

    @rule(item=st.sampled_from(RAW), pct=pcts, big=big_unit, back=st.booleans())
    def issue_or_return(self, item: str, pct: int, big: bool, back: bool) -> None:
        src, dst = ("WIP", "RAW_STORE") if back else ("RAW_STORE", "WIP")
        qty = self.portion((self.item[item], src, None), pct)
        value = self.take_value((self.item[item], src, None), D(qty))
        lines, deltas = self.lines_for(item, [(dst, qty, value), (src, -qty, -value)], big)
        self.post("RETURN" if back else "ISSUE", "material_issue", lines, deltas)

    @rule(raw=st.sampled_from(RAW), raw_pct=pcts, pouch_pct=pcts, damaged=st.integers(0, 10), big=big_unit)
    def complete_run(self, raw: str, raw_pct: int, pouch_pct: int, damaged: int, big: bool) -> None:
        raw_qty = self.portion((self.item[raw], "WIP", None), raw_pct)
        good = max(1, self.portion((self.item["pouch_200g"], "PACK_STORE", None), pouch_pct) - damaged)
        lot = self.new_lot()
        raw_value = self.take_value((self.item[raw], "WIP", None), D(raw_qty))
        pouch_value = self.take_value((self.item["pouch_200g"], "PACK_STORE", None), D(good + damaged))
        lines, deltas = self.lines_for(raw, [("PRODUCTION", raw_qty, raw_value), ("WIP", -raw_qty, -raw_value)], big)
        pouch_moves = [("PRODUCTION", good, pouch_value), ("PACK_STORE", -(good + damaged), -pouch_value)]
        if damaged:
            pouch_moves.append(("SCRAP", damaged, ZERO))
        more, d2 = self.lines_for("pouch_200g", pouch_moves, big)
        total = raw_value + pouch_value
        fg_lines, d3 = self.lines_for(FG, [("FG_STORE", good, total), ("PRODUCTION", -good, -total)], big, lot)
        if self.post("RUN_COMPLETION", "production_run", lines + more + fg_lines, {**deltas, **d2, **d3}):
            self.lots.append(lot)

    @precondition(lambda self: self.lots)
    @rule(pick=picks, pct=pcts, big=big_unit, use_reservation=st.booleans())
    def dispatch(self, pick: int, pct: int, big: bool, use_reservation: bool) -> None:
        lot = self.lots[pick % len(self.lots)]
        qty = self.portion((self.item[FG], "FG_STORE", lot), pct)
        consume: list[uuid.UUID] = []
        if use_reservation:
            fits = [rid for rid, (q, st_) in self.reservations.items() if st_ == "ACTIVE" and q <= qty]
            consume = fits[:1]
        value = self.take_value((self.item[FG], "FG_STORE", lot), D(qty))
        lines, deltas = self.lines_for(FG, [("CUSTOMER", qty, value), ("FG_STORE", -qty, -value)], big, lot)
        self.post("DISPATCH", "dispatch", lines, deltas, consume_reservation_ids=consume)

    @rule(item=st.sampled_from((*RAW, *PACK, FG)), pct=pcts, gain=st.booleans(), pick=picks)
    def adjust(self, item: str, pct: int, gain: bool, pick: int) -> None:
        lot = None
        if item == FG:
            if not self.lots:
                return
            lot = self.lots[pick % len(self.lots)]
        store = HOME[item]
        qty = self.portion((self.item[item], store, lot), pct) if not gain else pct
        if not APPROVER:
            APPROVER.append(make_user(ENGINES["owner"], "sm-approver"))
        if gain:
            moves = [(store, qty, ZERO), ("ADJUSTMENT", -qty, ZERO)]
        else:
            value = self.take_value((self.item[item], store, lot), D(qty))
            moves = [("ADJUSTMENT", qty, value), (store, -qty, -value)]
        lines, deltas = self.lines_for(item, moves, False, lot)
        self.post("ADJUSTMENT", "stock_count", lines, deltas, reason="cycle count", approved_by=APPROVER[0])

    @precondition(lambda self: self.journals)
    @rule(pick=picks)
    def reverse(self, pick: int) -> None:
        j = self.journals[pick % len(self.journals)]
        mirror = {k: (-q, -v) for k, (q, v) in j["deltas"].items()}
        ok, new = self.predict(mirror)
        ok = ok and j["kind"] != "REVERSAL" and not j["reversed"]
        result = self.attempt(
            lambda: ledger.reverse(
                self.s,
                organization_id=self.t.org,
                actor_id=None,
                journal_id=j["id"],
                reason="posted in error",
                posting_date=DAY,
            ),
            ok,
        )
        if result is not None:
            self.pos = new
            j["reversed"] = True
            self.journals.append(
                {"id": result.journal_id, "kind": "REVERSAL", "deltas": mirror, "reversed": False, "replay": None}
            )

    @rule(pct=pcts)
    def reserve(self, pct: int) -> None:
        on_hand = sum((q for k, (q, _) in self.pos.items() if k[0] == self.item[FG] and k[1] == "FG_STORE"), ZERO)
        qty = max(1, int(on_hand - self.active_reserved()) * pct // 100)
        ok = D(qty) <= on_hand - self.active_reserved()
        rid = self.attempt(
            lambda: ledger.reserve(
                self.s,
                organization_id=self.t.org,
                actor_id=None,
                order_line_id=self.order_line,
                item_id=self.item[FG],
                qty_base=D(qty),
                as_of=DAY,
            ),
            ok,
        )
        if rid is not None:
            self.reservations[rid] = (D(qty), "ACTIVE")

    @precondition(lambda self: self.reservations)
    @rule(pick=picks)
    def release(self, pick: int) -> None:
        rid = sorted(self.reservations)[pick % len(self.reservations)]
        ok = self.reservations[rid][1] == "ACTIVE"
        done = self.attempt(
            lambda: ledger.release(
                self.s, organization_id=self.t.org, actor_id=None, reservation_id=rid, reason="order rejected"
            )
            or True,
            ok,
        )
        if done:
            self.reservations[rid] = (self.reservations[rid][0], "RELEASED")

    @precondition(lambda self: any(j["replay"] for j in self.journals))
    @rule(pick=picks, change=st.booleans())
    def replay_idempotency_key(self, pick: int, change: bool) -> None:
        keyed = [j for j in self.journals if j["replay"]]
        j = keyed[pick % len(keyed)]
        call = dict(j["replay"])
        before = self.snapshot()
        if change:  # same key, different source document: must be a 409 and change nothing
            call["source_id"] = uuid.uuid4()
            try:
                ledger.post(self.s, **call)
            except ConflictError:
                self.s.rollback()
            else:
                raise AssertionError("a reused Idempotency-Key with a different payload was accepted")
        else:
            again = ledger.post(self.s, **call)
            self.s.commit()
            assert again.replayed and again.journal_id == j["id"]
        OUTCOMES["idempotency_conflict" if change else "idempotency_replay"] += 1
        assert self.snapshot() == before

    # ---------- invariants ----------

    def snapshot(self) -> tuple[dict[Pos, tuple[Decimal, Decimal]], dict[uuid.UUID, str]]:
        rows = self.s.execute(
            select(
                InventoryBalance.item_id,
                Location.code,
                InventoryBalance.lot_id,
                InventoryBalance.qty_base,
                InventoryBalance.value,
            ).join(Location, Location.id == InventoryBalance.location_id)
        ).all()
        balances = {}
        for item_id, code, lot, q, v in rows:
            assert type(q) is Decimal and type(v) is Decimal, "a float reached the ledger"
            if q != 0 or v != 0:
                balances[(item_id, code, lot)] = (q, v)
        # No commit here: a step's pending work (e.g. the lot a refused run created) must roll back with the step.
        reservations = dict(self.s.execute(select(Reservation.id, Reservation.status)).tuples().all())
        return balances, reservations

    @invariant()
    def ledger_holds(self) -> None:
        """One invariant, so each step costs only five reads."""
        balances, reservations = self.snapshot()
        # projection == model, reservations == model
        assert balances == {k: v for k, v in self.pos.items() if v != (ZERO, ZERO)}
        assert reservations == {rid: status for rid, (_, status) in self.reservations.items()}
        # law 1 (and 2) re-summed from the lines; projection == rebuild from the lines
        assert ledger.journal_imbalances(self.s) == []
        assert ledger.projection_diff(self.s) == []
        self.s.commit()
        # no store position negative; available >= 0 (on hand minus active reservations)
        for (_, loc, _), (q, v) in balances.items():
            if loc in STORES:
                assert q >= 0 and v >= 0 and (q != 0 or v == 0)
        fg_on_hand = sum(
            (q for (i, loc, _), (q, _) in balances.items() if i == self.item[FG] and loc == "FG_STORE"), ZERO
        )
        active = sum((self.reservations[r][0] for r, status in reservations.items() if status == "ACTIVE"), ZERO)
        assert fg_on_hand - active >= 0


def test_ledger_state_machine(owner_engine: Engine, app_engine: Engine) -> None:
    ENGINES.update(owner=owner_engine, app=app_engine)
    run_state_machine_as_test(
        LedgerMachine,
        settings=settings(
            max_examples=EXAMPLES,
            stateful_step_count=12,
            deadline=None,
            suppress_health_check=list(HealthCheck),
            database=None,
        ),
    )
    print("state machine outcomes:", dict(sorted(OUTCOMES.items())))
    refused = sum(n for k, n in OUTCOMES.items() if k.startswith("refused:"))
    assert OUTCOMES["accepted"] > 0 and refused > 0, OUTCOMES
    assert OUTCOMES["refused:negative_stock"] > 0 and OUTCOMES["refused:not_decimal"] > 0, OUTCOMES
