"""ledger.service against PostgreSQL (MP04): posting, refusals that leave no trace, idempotency, reversals,
reservations under concurrency, integrity queries, and the read-only stock API."""

import threading
import time
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.modules.audit.models import AuditLog
from app.modules.ledger import service as ledger
from app.modules.ledger.domain import LineSpec
from app.modules.ledger.models import StockJournal
from tests.db.conftest import (
    Staff,
    Tenant,
    login_client,
    make_order_line,
    make_user,
    scoped_session,
)

D = Decimal
DAY = date(2026, 11, 21)


@pytest.fixture
def s(app_engine: Engine, tenant: Tenant) -> Any:
    session = scoped_session(app_engine, tenant)
    ledger.ensure_locations(session, tenant.org)
    session.commit()
    yield session
    session.close()


def move(
    s: Session,
    t: Tenant,
    kind: str,
    item: str,
    src: str,
    dst: str,
    qty: str,
    unit: str,
    value: str = "0",
    lot: uuid.UUID | None = None,
    **kw: Any,
) -> ledger.Posted:
    source_type = {"RECEIPT": "purchase_receipt", "ISSUE": "material_issue", "OPENING": "opening"}.get(kind, "dispatch")
    return ledger.post(
        s,
        organization_id=t.org,
        actor_id=None,
        kind=kind,
        source_type=kw.pop("source_type", source_type),
        source_id=kw.pop("source_id", uuid.uuid4()),
        posting_date=kw.pop("posting_date", DAY),
        lines=[
            LineSpec(t.items[item], src, -D(qty), unit, -D(value), lot_id=lot),
            LineSpec(t.items[item], dst, D(qty), unit, D(value), lot_id=lot),
        ],
        **kw,
    )


def journals(s: Session) -> int:
    return int(s.execute(select(func.count()).select_from(StockJournal)).scalar_one())


def test_post_projects_balance_and_writes_audit(s: Session, tenant: Tenant) -> None:
    posted = move(s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "60", "kg", "2700.00")
    s.commit()
    assert not posted.replayed
    assert ledger.balance(s, tenant.items["flour"], "RAW_STORE") == (D(60000), D("2700.00"))
    assert ledger.balance(s, tenant.items["flour"], "SUPPLIER") == (D(-60000), D("-2700.00"))
    row = s.execute(select(AuditLog).where(AuditLog.entity_id == posted.journal_id)).scalar_one()
    assert row.action == "stock.post"
    assert row.summary["after"]["lines"][0]["role"] == "IN"  # incoming line stored first


def test_refused_post_leaves_no_trace_and_the_session_stays_usable(s: Session, tenant: Tenant) -> None:
    move(s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "10", "kg")
    before = journals(s)
    with pytest.raises(DomainError) as err:
        move(s, tenant, "ISSUE", "flour", "RAW_STORE", "WIP", "10.001", "kg")
    assert err.value.code == "negative_stock"
    assert journals(s) == before  # the savepoint rolled the journal back
    move(s, tenant, "ISSUE", "flour", "RAW_STORE", "WIP", "4", "kg")  # same transaction, still usable
    s.commit()
    assert ledger.balance(s, tenant.items["flour"], "RAW_STORE") == (D(6000), D(0))
    assert ledger.balance(s, tenant.items["flour"], "WIP") == (D(4000), D(0))


def test_float_is_refused_before_the_database(s: Session, tenant: Tenant) -> None:
    bad: Any = 1.5
    with pytest.raises(DomainError) as err:
        ledger.post(
            s,
            organization_id=tenant.org,
            actor_id=None,
            kind="RECEIPT",
            source_type="purchase_receipt",
            source_id=uuid.uuid4(),
            posting_date=DAY,
            lines=[
                LineSpec(tenant.items["flour"], "SUPPLIER", bad, "kg"),
                LineSpec(tenant.items["flour"], "RAW_STORE", D("1.5"), "kg"),
            ],
        )
    assert err.value.code == "not_decimal"


def test_idempotency_key_replays_and_refuses_a_different_payload(s: Session, tenant: Tenant) -> None:
    key, source = uuid.uuid4(), uuid.uuid4()
    first = move(
        s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "60", "kg", idempotency_key=key, source_id=source
    )
    s.commit()
    again = move(
        s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "60000", "g", idempotency_key=key, source_id=source
    )
    s.commit()
    assert again.replayed and again.journal_id == first.journal_id
    assert ledger.balance(s, tenant.items["flour"], "RAW_STORE")[0] == D(60000)  # posted once
    with pytest.raises(ConflictError) as err:
        move(s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "61", "kg", idempotency_key=key, source_id=source)
    assert err.value.code == "idempotency_key_reused"
    assert err.value.status_code == 409


def test_reversal_mirrors_once_and_is_not_itself_reversible(s: Session, tenant: Tenant) -> None:
    posted = move(s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "60", "kg", "2700.00")
    with pytest.raises(DomainError) as err:
        ledger.reverse(s, organization_id=tenant.org, actor_id=None, journal_id=posted.journal_id, reason="  ")
    assert err.value.code == "reason_required"
    rev = ledger.reverse(
        s, organization_id=tenant.org, actor_id=None, journal_id=posted.journal_id, reason="wrong supplier"
    )
    s.commit()
    assert ledger.balance(s, tenant.items["flour"], "RAW_STORE") == (D(0), D(0))
    with pytest.raises(DomainError) as err:
        ledger.reverse(s, organization_id=tenant.org, actor_id=None, journal_id=posted.journal_id, reason="again")
    assert err.value.code == "already_reversed"
    with pytest.raises(DomainError) as err:
        ledger.reverse(s, organization_id=tenant.org, actor_id=None, journal_id=rev.journal_id, reason="undo")
    assert err.value.code == "cannot_reverse_reversal"
    with pytest.raises(NotFoundError):
        ledger.reverse(s, organization_id=tenant.org, actor_id=None, journal_id=uuid.uuid4(), reason="x")
    with pytest.raises(DomainError) as err:
        ledger.post(
            s,
            organization_id=tenant.org,
            actor_id=None,
            kind="REVERSAL",
            source_type="stock_journal",
            source_id=posted.journal_id,
            posting_date=DAY,
            lines=[],
            reason="by hand",
        )
    assert err.value.code == "use_reverse"


def test_reversal_that_would_take_a_store_negative_is_refused(s: Session, tenant: Tenant) -> None:
    receipt = move(s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "10", "kg")
    move(s, tenant, "ISSUE", "flour", "RAW_STORE", "WIP", "6", "kg")
    s.commit()
    with pytest.raises(DomainError) as err:
        ledger.reverse(s, organization_id=tenant.org, actor_id=None, journal_id=receipt.journal_id, reason="returned")
    assert err.value.code == "negative_stock"


def test_adjustment_needs_an_approver(s: Session, owner_engine: Engine, tenant: Tenant) -> None:
    move(s, tenant, "RECEIPT", "spice", "SUPPLIER", "RAW_STORE", "5", "kg")
    with pytest.raises(DomainError) as err:
        move(
            s,
            tenant,
            "ADJUSTMENT",
            "spice",
            "RAW_STORE",
            "ADJUSTMENT",
            "0.2",
            "kg",
            source_type="stock_count",
            reason="count",
        )
    assert err.value.code == "approval_required"
    approver = make_user(owner_engine, "approver")
    move(
        s,
        tenant,
        "ADJUSTMENT",
        "spice",
        "RAW_STORE",
        "ADJUSTMENT",
        "0.2",
        "kg",
        source_type="stock_count",
        reason="monthly count",
        approved_by=approver,
    )
    s.commit()
    assert ledger.balance(s, tenant.items["spice"], "RAW_STORE")[0] == D(4800)


def test_locked_period_is_refused(s: Session, owner_engine: Engine, tenant: Tenant) -> None:
    with owner_engine.begin() as c:
        c.execute(
            text("INSERT INTO period_locks (organization_id, period, reason) VALUES (:o, '2026-10-01', 'closed')"),
            {"o": tenant.org},
        )
    with pytest.raises(DomainError) as err:
        move(s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "1", "kg", posting_date=date(2026, 10, 15))
    assert err.value.code == "period_locked"


def test_lot_of_another_item_is_refused(s: Session, app_engine: Engine, tenant: Tenant) -> None:
    lot = ledger.create_lot(
        s,
        organization_id=tenant.org,
        actor_id=None,
        item_id=tenant.items["murukku_200g"],
        lot_no="B-X",
        source_type="production_run",
    )
    with pytest.raises(DomainError) as err:
        move(s, tenant, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "1", "kg", lot=lot)
    assert err.value.code == "invalid_reference"


# ---------- reservations and available to promise ----------


def stock_fg(s: Session, t: Tenant, packets: str = "238") -> uuid.UUID:
    lot = ledger.create_lot(
        s,
        organization_id=t.org,
        actor_id=None,
        item_id=t.items["murukku_200g"],
        lot_no=f"L-{uuid.uuid4().hex[:6]}",
        source_type="opening",
    )
    move(s, t, "OPENING", "murukku_200g", "OPENING", "FG_STORE", packets, "packet", lot=lot)
    s.commit()
    return lot


def test_reservation_holds_stock_until_consumed(s: Session, owner_engine: Engine, tenant: Tenant) -> None:
    lot = stock_fg(s, tenant)
    fg = tenant.items["murukku_200g"]
    line_a = make_order_line(owner_engine, tenant, qty=150)
    line_b = make_order_line(owner_engine, tenant, qty=120)
    reservation = ledger.reserve(
        s, organization_id=tenant.org, actor_id=None, order_line_id=line_a, item_id=fg, qty_base=D(150)
    )
    s.commit()
    assert ledger.available_to_promise(s, fg)["available"] == D(88)

    with pytest.raises(DomainError) as err:  # Distributor B: 120 requested, 88 available
        ledger.reserve(s, organization_id=tenant.org, actor_id=None, order_line_id=line_b, item_id=fg, qty_base=D(120))
    assert err.value.code == "insufficient_available"
    assert err.value.details["shortage"] == "32"

    with pytest.raises(DomainError) as err:  # dispatching 100 to someone else would eat into A's reservation
        move(s, tenant, "DISPATCH", "murukku_200g", "FG_STORE", "CUSTOMER", "100", "packet", lot=lot)
    assert err.value.code == "insufficient_available"

    move(
        s,
        tenant,
        "DISPATCH",
        "murukku_200g",
        "FG_STORE",
        "CUSTOMER",
        "150",
        "packet",
        lot=lot,
        consume_reservation_ids=[reservation],
    )
    s.commit()
    assert ledger.available_to_promise(s, fg) == {"on_hand": D(88), "reserved": D(0), "available": D(88)}
    with pytest.raises(DomainError) as err:
        ledger.release(s, organization_id=tenant.org, actor_id=None, reservation_id=reservation, reason="late")
    assert err.value.code == "reservation_not_active"


def test_released_reservation_returns_to_available(s: Session, owner_engine: Engine, tenant: Tenant) -> None:
    stock_fg(s, tenant, "50")
    fg = tenant.items["murukku_200g"]
    r = ledger.reserve(
        s,
        organization_id=tenant.org,
        actor_id=None,
        order_line_id=make_order_line(owner_engine, tenant),
        item_id=fg,
        qty_base=D(50),
    )
    s.commit()
    assert ledger.available_to_promise(s, fg)["available"] == D(0)
    ledger.release(s, organization_id=tenant.org, actor_id=None, reservation_id=r, reason="order rejected")
    s.commit()
    assert ledger.available_to_promise(s, fg)["available"] == D(50)


def test_expired_lots_are_not_available_to_promise(s: Session, app_engine: Engine, tenant: Tenant) -> None:
    fg = tenant.items["murukku_200g"]
    lot = ledger.create_lot(
        s,
        organization_id=tenant.org,
        actor_id=None,
        item_id=fg,
        lot_no="OLD",
        source_type="opening",
        best_before=date(2026, 11, 1),
    )
    move(s, tenant, "OPENING", "murukku_200g", "OPENING", "FG_STORE", "40", "packet", lot=lot)
    s.commit()
    assert ledger.available_to_promise(s, fg, as_of=date(2026, 10, 31))["available"] == D(40)
    assert ledger.available_to_promise(s, fg, as_of=DAY)["available"] == D(0)


def test_parallel_approvals_cannot_over_reserve(app_engine: Engine, owner_engine: Engine, tenant: Tenant) -> None:
    """Two approvals of 150 against 238 packets at the same instant: exactly one wins (per-item lock)."""
    setup = scoped_session(app_engine, tenant)
    ledger.ensure_locations(setup, tenant.org)
    stock_fg(setup, tenant)
    setup.close()
    lines = [make_order_line(owner_engine, tenant) for _ in range(2)]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def approve(order_line: uuid.UUID) -> None:
        session = scoped_session(app_engine, tenant)
        try:
            barrier.wait()
            ledger.reserve(
                session,
                organization_id=tenant.org,
                actor_id=None,
                order_line_id=order_line,
                item_id=tenant.items["murukku_200g"],
                qty_base=D(150),
            )
            time.sleep(0.3)  # hold the lock so the other approval has to wait for this commit
            session.commit()
            outcomes.append("reserved")
        except DomainError as exc:
            session.rollback()
            outcomes.append(exc.code)
        finally:
            session.close()

    threads = [threading.Thread(target=approve, args=(line,)) for line in lines]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert sorted(outcomes) == ["insufficient_available", "reserved"]


# ---------- integrity ----------


def test_integrity_queries_are_clean_after_postings(s: Session, tenant: Tenant) -> None:
    move(s, tenant, "RECEIPT", "oil", "SUPPLIER", "RAW_STORE", "30", "L", "4200.00")
    move(s, tenant, "ISSUE", "oil", "RAW_STORE", "WIP", "10.5", "L", "1470.00")
    s.commit()
    assert ledger.journal_imbalances(s) == []
    assert ledger.projection_diff(s) == []


def test_projection_diff_catches_a_tampered_balance(owner_engine: Engine, app_engine: Engine, tenant: Tenant) -> None:
    s = scoped_session(app_engine, tenant)
    ledger.ensure_locations(s, tenant.org)
    move(s, tenant, "RECEIPT", "oil", "SUPPLIER", "RAW_STORE", "30", "L")
    s.commit()
    s.close()
    with owner_engine.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("UPDATE inventory_balances SET qty_base = qty_base + 1 WHERE organization_id = :o AND qty_base > 0"),
            {"o": tenant.org},
        )
        diff = [d for d in ledger.projection_diff(Session(bind=conn)) if d["organization_id"] == str(tenant.org)]
        tx.rollback()  # never repair by hand: the test undoes its own tampering
    assert len(diff) == 1
    assert diff[0]["rebuilt_qty"] == "30000.000000" and diff[0]["projected_qty"] == "30001.000000"


# ---------- read-only stock API ----------


def test_stock_api_balances_and_ledger(api_app: Any, app_engine: Engine, staff: Staff) -> None:
    t = staff.tenant
    s = scoped_session(app_engine, t)
    ledger.ensure_locations(s, t.org)
    move(
        s,
        t,
        "OPENING",
        "flour",
        "OPENING",
        "RAW_STORE",
        "100",
        "kg",
        "4200.00",
        posting_date=date(2026, 11, 1),
        source_type="opening",
    )
    receipt = move(s, t, "RECEIPT", "flour", "SUPPLIER", "RAW_STORE", "60", "kg", "2700.00")
    move(s, t, "ISSUE", "flour", "RAW_STORE", "WIP", "40", "kg", "1725.00")
    s.commit()
    raw = ledger.locations(s)["RAW_STORE"].id
    s.close()

    client = login_client(api_app, staff.emails["ADMIN"])
    r = client.get("/api/stock/balances", params={"item_id": str(t.items["flour"])})
    assert r.status_code == 200, r.text
    by_location = {b["location"]: b for b in r.json()["balances"]}
    assert set(by_location) == {"RAW_STORE", "WIP"}  # stores only by default
    assert (by_location["RAW_STORE"]["qty"], by_location["RAW_STORE"]["uom"]) == ("120", "kg")
    assert by_location["RAW_STORE"]["value"] == "5175.00"

    r = client.get(
        "/api/stock/ledger",
        params={"item_id": str(t.items["flour"]), "location_id": str(raw), "date_from": "2026-11-21"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(o["qty"], o["value"]) for o in body["opening"]] == [("100", "4200.00")]
    assert [(row["kind"], row["qty"], row["running"]["qty"], row["running"]["value"]) for row in body["rows"]] == [
        ("RECEIPT", "60", "160", "6900.00"),
        ("ISSUE", "-40", "120", "5175.00"),
    ]
    assert body["rows"][0]["source"] == {"type": "purchase_receipt", "id": body["rows"][0]["source"]["id"]}
    assert body["rows"][0]["journal_id"] == str(receipt.journal_id)

    # A salesman holds stock.read for "available today": quantities yes, rupee values (cost) never.
    salesman = login_client(api_app, staff.emails["SALESMAN"])
    for path, params in (
        ("/api/stock/balances", {"item_id": str(t.items["flour"])}),
        ("/api/stock/ledger", {"item_id": str(t.items["flour"]), "date_from": "2026-11-21"}),
    ):
        r = salesman.get(path, params=params)
        assert r.status_code == 200, r.text
        assert '"value"' not in r.text, f"{path} leaks a rupee value to a salesman"
    rows = salesman.get("/api/stock/balances", params={"item_id": str(t.items["flour"])}).json()["balances"]
    assert {b["location"]: b["qty"] for b in rows} == {"RAW_STORE": "120", "WIP": "40"}

    bad = client.get("/api/stock/ledger", params={"date_from": "2026-11-22", "date_to": "2026-11-01"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "bad_date_range"


def test_scratch_tenants_are_benchmark_or_sim_only(app_engine: Engine) -> None:
    from app.modules.identity import service as identity

    with Session(app_engine) as session:
        with pytest.raises(DomainError) as err:
            identity.create_scratch_tenant(session, kind="LIVE", label="nope")
        assert err.value.code == "not_a_scratch_tenant"
        org = identity.create_scratch_tenant(session, kind="BENCHMARK", label="t")
        locs = ledger.ensure_locations(session, org)
        session.commit()
        assert {code for code, ref in locs.items() if ref.kind == "STORE"} == {
            "RAW_STORE",
            "PACK_STORE",
            "WIP",
            "FG_STORE",
            "IN_TRANSIT",
        }


def test_duplicate_item_code_is_a_clear_error(s: Session, tenant: Tenant) -> None:
    from app.modules.catalog import service as catalog

    with pytest.raises(DomainError) as err:
        catalog.create_item(
            s,
            organization_id=tenant.org,
            actor_id=None,
            code="flour",
            name="again",
            kind="RAW",
            base_uom="g",
            stock_uom="kg",
        )
    assert err.value.code == "item_code_taken"
    assert ledger.balance(s, tenant.items["flour"], "RAW_STORE") == (D(0), D(0))  # the session is still usable
