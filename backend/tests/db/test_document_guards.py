"""Guards on posted documents, period locks, payment allocation and numbering (invariants D1-D5, P1)."""

import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from tests.db.conftest import Tenant, as_org, post_journal, sqlstate

FLOUR_RECEIPT = [
    ("flour", "SUPPLIER", None, "-60000", "-2700.00", "OUT"),
    ("flour", "RAW_STORE", None, "60000", "2700.00", "IN"),
]


def _invoice(c: Connection, t: Tenant, no: str = "AHR/26-27/000001", day: str = "2026-11-21") -> uuid.UUID:
    """Retailer A's benchmark invoice: 150 x ₹50 + 5% GST split CGST/SGST = ₹7,875.00."""
    return c.execute(
        text(
            "INSERT INTO invoices (organization_id, invoice_no, invoice_date, customer_id, supplier_state,"
            " place_of_supply, regime, taxable, tax_total, total)"
            " VALUES (:o, :no, :d, :cust, '33', '33', 'INTRA', 7500.00, 375.00, 7875.00) RETURNING id"
        ),
        {"o": t.org, "no": no, "d": day, "cust": t.customer},
    ).scalar_one()


def _payment(c: Connection, t: Tenant, no: str, amount: str) -> uuid.UUID:
    return c.execute(
        text(
            "INSERT INTO payments (organization_id, payment_no, customer_id, received_on, amount, mode)"
            " VALUES (:o, :no, :cust, '2026-11-21', :amt, 'UPI') RETURNING id"
        ),
        {"o": t.org, "no": no, "cust": t.customer, "amt": amount},
    ).scalar_one()


def _allocate(c: Connection, t: Tenant, payment: uuid.UUID, invoice: uuid.UUID, amount: str) -> None:
    c.execute(
        text(
            "INSERT INTO payment_allocations (organization_id, payment_id, invoice_id, amount)"
            " VALUES (:o, :p, :i, :a)"
        ),
        {"o": t.org, "p": payment, "i": invoice, "a": amount},
    )


# ---------- invoices (D1) ----------


def test_posted_invoice_update_rejected(owner_engine: Engine, app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        invoice = _invoice(as_org(c, tenant.org), tenant)
    # first wall: the app role may only touch the cancellation columns
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org).execute(text("UPDATE invoices SET taxable = 1 WHERE id = :i"), {"i": invoice})
    assert sqlstate(err.value) == "42501"
    # second wall: not even the owner can change a posted amount
    with pytest.raises(DBAPIError) as err, owner_engine.begin() as c:
        c.execute(text("UPDATE invoices SET taxable = 1, total = 376.00 WHERE id = :i"), {"i": invoice})
    assert sqlstate(err.value) == "AH002"
    with pytest.raises(DBAPIError) as err, owner_engine.begin() as c:
        c.execute(text("DELETE FROM invoices WHERE id = :i"), {"i": invoice})
    assert sqlstate(err.value) == "AH002"


def test_invoice_cancel_needs_reason_and_is_final(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        invoice = _invoice(as_org(c, tenant.org), tenant)
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org).execute(
            text("UPDATE invoices SET status = 'CANCELLED', cancelled_at = now() WHERE id = :i"), {"i": invoice}
        )
    assert sqlstate(err.value) == "23514"

    with app_engine.begin() as c:
        as_org(c, tenant.org).execute(
            text(
                "UPDATE invoices SET status = 'CANCELLED', cancelled_at = now(), cancel_reason = 'duplicate'"
                " WHERE id = :i"
            ),
            {"i": invoice},
        )
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org).execute(text("UPDATE invoices SET status = 'POSTED' WHERE id = :i"), {"i": invoice})
    assert sqlstate(err.value) == "AH002"


def test_invoice_regime_must_follow_place_of_supply(app_engine: Engine, tenant: Tenant) -> None:
    """Tamil Nadu to Tamil Nadu is CGST + SGST; calling it IGST is rejected (D6 backstop)."""
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org).execute(
            text(
                "INSERT INTO invoices (organization_id, invoice_no, invoice_date, customer_id, supplier_state,"
                " place_of_supply, regime, taxable, tax_total, total)"
                " VALUES (:o, 'X/1', '2026-11-21', :cust, '33', '33', 'INTER', 100, 5, 105)"
            ),
            {"o": tenant.org, "cust": tenant.customer},
        )
    assert sqlstate(err.value) == "23514"


def test_invoice_line_is_insert_only(app_engine: Engine, owner_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        as_org(c, tenant.org)
        invoice = _invoice(c, tenant)
        c.execute(
            text(
                "INSERT INTO invoice_lines (organization_id, invoice_id, line_no, item_id, hsn, qty, rate, taxable)"
                " VALUES (:o, :i, 1, :item, '19059020', 150, 50.00, 7500.00)"
            ),
            {"o": tenant.org, "i": invoice, "item": tenant.items["murukku_200g"]},
        )
    with pytest.raises(DBAPIError) as err, owner_engine.begin() as c:
        c.execute(text("UPDATE invoice_lines SET qty = 1 WHERE invoice_id = :i"), {"i": invoice})
    assert sqlstate(err.value) == "AH002"


# ---------- payments (D5) ----------


def test_over_allocation_rejected(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        as_org(c, tenant.org)
        invoice = _invoice(c, tenant)
        pay1 = _payment(c, tenant, "RCPT-1", "4000.00")
        _allocate(c, tenant, pay1, invoice, "4000.00")  # NIT step 7: outstanding 3,875.00

    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        _allocate(as_org(c, tenant.org), tenant, pay1, invoice, "0.01")
    assert sqlstate(err.value) == "AH004"
    assert "exceed payment amount" in str(err.value)

    with app_engine.begin() as c:
        as_org(c, tenant.org)
        pay2 = _payment(c, tenant, "RCPT-2", "5000.00")
        _allocate(c, tenant, pay2, invoice, "3875.00")  # invoice now fully paid
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        _allocate(as_org(c, tenant.org), tenant, pay2, invoice, "0.01")
    assert sqlstate(err.value) == "AH004"
    assert "exceed invoice" in str(err.value)

    with app_engine.begin() as c:
        unallocated = (
            as_org(c, tenant.org)
            .execute(
                text(
                    "SELECT p.amount - coalesce(sum(a.amount), 0) FROM payments p"
                    " LEFT JOIN payment_allocations a ON a.payment_id = p.id WHERE p.id = :p GROUP BY p.amount"
                ),
                {"p": pay2},
            )
            .scalar_one()
        )
    assert unallocated == Decimal("1125.00")  # advance, computed, never stored


def test_invoice_with_payments_cannot_be_cancelled(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        as_org(c, tenant.org)
        invoice = _invoice(c, tenant)
        _allocate(c, tenant, _payment(c, tenant, "RCPT-1", "4000.00"), invoice, "4000.00")
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org).execute(
            text("UPDATE invoices SET status = 'CANCELLED', cancelled_at = now(), cancel_reason = 'x' WHERE id = :i"),
            {"i": invoice},
        )
    assert sqlstate(err.value) == "AH002"


# ---------- period lock (P1) ----------


def test_post_into_locked_period_rejected(owner_engine: Engine, app_engine: Engine, tenant: Tenant) -> None:
    with owner_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO period_locks (organization_id, period, reason) VALUES (:o, '2026-10-01', 'October closed')"
            ),
            {"o": tenant.org},
        )
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        post_journal(as_org(c, tenant.org), tenant, "RECEIPT", FLOUR_RECEIPT, posting_date="2026-10-31")
    assert sqlstate(err.value) == "AH003"
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        _invoice(as_org(c, tenant.org), tenant, day="2026-10-15")
    assert sqlstate(err.value) == "AH003"
    with app_engine.begin() as c:  # November is open
        post_journal(as_org(c, tenant.org), tenant, "RECEIPT", FLOUR_RECEIPT, posting_date="2026-11-01")


# ---------- production runs (D2) and BOM versions ----------


def _recipe_version(c: Connection, t: Tenant) -> uuid.UUID:
    recipe = c.execute(
        text(
            "INSERT INTO recipes (organization_id, code, name, bulk_item_id) VALUES (:o, 'MURUKKU', 'Murukku', :b)"
            " RETURNING id"
        ),
        {"o": t.org, "b": t.items["murukku_200g"]},
    ).scalar_one()
    version = c.execute(
        text(
            "INSERT INTO recipe_versions (organization_id, recipe_id, version, bulk_yield_g, effective_from)"
            " VALUES (:o, :r, 1, 40000, '2026-11-01') RETURNING id"
        ),
        {"o": t.org, "r": recipe},
    ).scalar_one()
    c.execute(
        text(
            "INSERT INTO recipe_lines (organization_id, recipe_version_id, item_id, qty_base)"
            " VALUES (:o, :v, :i, 40000)"
        ),
        {"o": t.org, "v": version, "i": t.items["flour"]},
    )
    return version


def test_recipe_lines_frozen_once_version_is_active(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        version = _recipe_version(as_org(c, tenant.org), tenant)
        c.execute(text("UPDATE recipe_lines SET qty_base = 41000 WHERE recipe_version_id = :v"), {"v": version})
        c.execute(text("UPDATE recipe_versions SET status = 'ACTIVE' WHERE id = :v"), {"v": version})
    for statement in (
        "UPDATE recipe_lines SET qty_base = 42000 WHERE recipe_version_id = :v",
        "DELETE FROM recipe_lines WHERE recipe_version_id = :v",
        "INSERT INTO recipe_lines (organization_id, recipe_version_id, item_id, qty_base)"
        " SELECT organization_id, :v, id, 1 FROM items WHERE code = 'oil'",
        "UPDATE recipe_versions SET bulk_yield_g = 1 WHERE id = :v",
        "DELETE FROM recipe_versions WHERE id = :v",
    ):
        with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
            as_org(c, tenant.org).execute(text(statement), {"v": version})
        assert sqlstate(err.value) == "AH002", statement
    with app_engine.begin() as c:  # retiring is allowed
        as_org(c, tenant.org).execute(
            text("UPDATE recipe_versions SET status = 'RETIRED' WHERE id = :v"), {"v": version}
        )


def test_run_snapshot_frozen_and_completed_run_locked(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        version = _recipe_version(as_org(c, tenant.org), tenant)
        run = c.execute(
            text(
                "INSERT INTO production_runs (organization_id, run_no, recipe_version_id, batch_multiplier, run_date)"
                " VALUES (:o, 'B-001', :v, 1, '2026-11-21') RETURNING id"
            ),
            {"o": tenant.org, "v": version},
        ).scalar_one()

    def run_sql(statement: str) -> None:
        with app_engine.begin() as c:
            as_org(c, tenant.org).execute(text(statement), {"r": run})

    with pytest.raises(DBAPIError) as err:  # a started run must carry its snapshots
        run_sql("UPDATE production_runs SET status = 'IN_PROGRESS' WHERE id = :r")
    assert sqlstate(err.value) == "23514"

    run_sql(
        "UPDATE production_runs SET status = 'IN_PROGRESS', started_at = now(),"
        " recipe_snapshot = '{\"flour_g\": 40000}', pack_snapshot = '{\"net_g\": 200}' WHERE id = :r"
    )
    with pytest.raises(DBAPIError) as err:
        run_sql("UPDATE production_runs SET recipe_snapshot = '{\"flour_g\": 1}' WHERE id = :r")
    assert sqlstate(err.value) == "AH002"

    run_sql("UPDATE production_runs SET status = 'COMPLETED', completed_at = now() WHERE id = :r")
    for statement in (
        "UPDATE production_runs SET batch_multiplier = 2 WHERE id = :r",
        "UPDATE production_runs SET status = 'IN_PROGRESS' WHERE id = :r",
        "DELETE FROM production_runs WHERE id = :r",
    ):
        with pytest.raises(DBAPIError) as err:
            run_sql(statement)
        assert sqlstate(err.value) == "AH002", statement

    run_sql("UPDATE production_runs SET cost_status = 'FINAL' WHERE id = :r")  # late costs arrived (ADR-0004)
    with pytest.raises(DBAPIError) as err:
        run_sql("UPDATE production_runs SET cost_status = 'PROVISIONAL' WHERE id = :r")
    assert sqlstate(err.value) == "AH002"


def test_receipt_lines_frozen_once_posted(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        as_org(c, tenant.org)
        supplier = c.execute(
            text(
                "INSERT INTO suppliers (organization_id, code, name, state_code) VALUES (:o, 'S1', 'DEMO Mill', '33')"
                " RETURNING id"
            ),
            {"o": tenant.org},
        ).scalar_one()
        receipt = c.execute(
            text(
                "INSERT INTO purchase_receipts (organization_id, receipt_no, supplier_id, received_on)"
                " VALUES (:o, 'GRN-1', :s, '2026-11-21') RETURNING id"
            ),
            {"o": tenant.org, "s": supplier},
        ).scalar_one()
        c.execute(
            text(
                "INSERT INTO purchase_receipt_lines (organization_id, receipt_id, line_no, item_id, qty_entered,"
                " uom_entered, qty_base, rate, value, accepted_base) VALUES (:o, :r, 1, :i, 60, 'kg', 60000, 45,"
                " 2700.00, 60000)"
            ),
            {"o": tenant.org, "r": receipt, "i": tenant.items["flour"]},
        )
        journal = post_journal(c, tenant, "RECEIPT", FLOUR_RECEIPT)
        c.execute(
            text("UPDATE purchase_receipts SET status = 'POSTED', posted_at = now(), journal_id = :j WHERE id = :r"),
            {"j": journal, "r": receipt},
        )
    for statement in (
        "UPDATE purchase_receipt_lines SET rate = 40 WHERE receipt_id = :r",
        "UPDATE purchase_receipts SET supplier_invoice_ref = 'changed' WHERE id = :r",
        "DELETE FROM purchase_receipts WHERE id = :r",
    ):
        with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
            as_org(c, tenant.org).execute(text(statement), {"r": receipt})
        assert sqlstate(err.value) == "AH002", statement


# ---------- numbering (D3) ----------


def _next(c: Connection, t: Tenant) -> int:
    return int(c.execute(text("SELECT aahar_next_doc_number(:o, 'INVOICE', '26-27')"), {"o": t.org}).scalar_one())


def test_doc_numbers_are_gapless_after_rollback(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        assert _next(as_org(c, tenant.org), tenant) == 1
    c = app_engine.connect()
    tx = c.begin()
    assert _next(as_org(c, tenant.org), tenant) == 2
    tx.rollback()  # e.g. invoice posting failed
    c.close()
    with app_engine.begin() as c:
        assert _next(as_org(c, tenant.org), tenant) == 2  # the number is reused: no gap


def test_parallel_doc_numbers_are_distinct_and_consecutive(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        _next(as_org(c, tenant.org), tenant)  # counter row exists: 1 used
    first = app_engine.connect()
    tx = first.begin()
    got_first = _next(as_org(first, tenant.org), tenant)  # holds the counter row lock

    results: list[int] = []

    def second() -> None:
        with app_engine.begin() as c:
            results.append(_next(as_org(c, tenant.org), tenant))

    worker = threading.Thread(target=second)
    worker.start()
    worker.join(timeout=1.0)
    assert worker.is_alive(), "the second caller must wait for the first transaction"
    tx.commit()
    first.close()
    worker.join(timeout=10.0)
    assert (got_first, results) == (2, [3])


# ---------- effective-dated config (D7) ----------


def test_overlapping_tax_rules_rejected(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        as_org(c, tenant.org).execute(
            text(
                "INSERT INTO tax_rules (organization_id, hsn, rate_pct, effective_from, effective_to)"
                " VALUES (:o, '19059020', 5, '2025-04-01', NULL)"
            ),
            {"o": tenant.org},
        )
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org).execute(
            text(
                "INSERT INTO tax_rules (organization_id, hsn, rate_pct, effective_from)"
                " VALUES (:o, '19059020', 12, '2026-01-01')"
            ),
            {"o": tenant.org},
        )
    assert sqlstate(err.value) == "23P01"  # exclusion_violation
    with app_engine.begin() as c:  # close the old rule first, then the new rate is accepted
        as_org(c, tenant.org)
        c.execute(text("UPDATE tax_rules SET effective_to = '2025-12-31' WHERE hsn = '19059020'"))
        c.execute(
            text(
                "INSERT INTO tax_rules (organization_id, hsn, rate_pct, effective_from)"
                " VALUES (:o, '19059020', 12, '2026-01-01')"
            ),
            {"o": tenant.org},
        )
