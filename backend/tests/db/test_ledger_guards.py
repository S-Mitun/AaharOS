"""Ledger guards enforced by PostgreSQL itself (MP02 gate: an unbalanced journal is rejected by the database).

Writes go through `aahar_app` with the org GUC set, exactly as the API will. Quantities are base units
(g, mL, piece); values are rupees.
"""

from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.db.conftest import Tenant, as_org, make_lot, make_tenant, make_user, post_journal, sqlstate


def _balance(app_engine: Engine, t: Tenant, item: str, location: str) -> tuple[Decimal, Decimal]:
    with app_engine.begin() as c:
        as_org(c, t.org)
        row = c.execute(
            text(
                "SELECT coalesce(sum(qty_base), 0), coalesce(sum(value), 0) FROM inventory_balances"
                " WHERE item_id = :i AND location_id = :l"
            ),
            {"i": t.items[item], "l": t.locations[location]},
        ).one()
    return row[0], row[1]


# ---------- law 1 and law 2 ----------


def test_unbalanced_journal_rejected(app_engine: Engine, tenant: Tenant) -> None:
    """60 kg leave the supplier but only 59 kg arrive: Postgres refuses the journal at commit."""
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "RECEIPT",
            [
                ("flour", "SUPPLIER", None, "-60000", "-2700.00", "OUT"),
                ("flour", "RAW_STORE", None, "59000", "2700.00", "IN"),
            ],
        )
    assert sqlstate(err.value) == "AH001"
    assert "quantity of item" in str(err.value)
    assert _balance(app_engine, tenant, "flour", "RAW_STORE") == (0, 0)  # nothing was posted


def test_unbalanced_value_rejected(app_engine: Engine, tenant: Tenant) -> None:
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "RECEIPT",
            [
                ("flour", "SUPPLIER", None, "-60000", "-2700.00", "OUT"),
                ("flour", "RAW_STORE", None, "60000", "2700.01", "IN"),
            ],
        )
    assert sqlstate(err.value) == "AH001"
    assert "value sums to 0.01" in str(err.value)


def test_balanced_journal_posts_and_projects(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "RECEIPT",
            [
                ("flour", "SUPPLIER", None, "-60000", "-2700.00", "OUT"),
                ("flour", "RAW_STORE", None, "60000", "2700.00", "IN"),
            ],
        )
    assert _balance(app_engine, tenant, "flour", "RAW_STORE") == (Decimal("60000"), Decimal("2700.00"))
    assert _balance(app_engine, tenant, "flour", "SUPPLIER") == (Decimal("-60000"), Decimal("-2700.00"))


def test_journal_without_lines_rejected(app_engine: Engine, tenant: Tenant) -> None:
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(c, tenant, "RECEIPT", [])
    assert sqlstate(err.value) == "AH001"


def test_line_sign_must_match_role(app_engine: Engine, tenant: Tenant) -> None:
    """An IN line with a negative quantity is a CHECK violation, before any balancing."""
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "RECEIPT",
            [
                ("flour", "SUPPLIER", None, "60000", "2700.00", "OUT"),
                ("flour", "RAW_STORE", None, "-60000", "-2700.00", "IN"),
            ],
        )
    assert sqlstate(err.value) == "23514"
    assert "sign_matches_role" in str(err.value)


def test_value_only_line_outside_true_up_rejected(app_engine: Engine, tenant: Tenant) -> None:
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "RECEIPT",
            [
                ("flour", "SUPPLIER", None, "0", "-10.00", "VALUE_ONLY"),
                ("flour", "SUPPLIER", None, "0", "10.00", "VALUE_ONLY"),
            ],
        )
    assert sqlstate(err.value) == "AH005"


def test_adjustment_needs_reason(owner_engine: Engine, app_engine: Engine, tenant: Tenant) -> None:
    approver = make_user(owner_engine, "approver")
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "ADJUSTMENT",
            [
                ("flour", "RAW_STORE", None, "-300", "0", "OUT"),
                ("flour", "ADJUSTMENT", None, "300", "0", "IN"),
            ],
            reason="  ",
            approved_by=approver,
        )
    assert sqlstate(err.value) == "23514"
    assert "reason_required" in str(err.value)


# ---------- S1: stores never go negative ----------


def test_store_cannot_go_negative(app_engine: Engine, tenant: Tenant) -> None:
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "ISSUE",
            [
                ("flour", "RAW_STORE", None, "-10", "0", "OUT"),
                ("flour", "WIP", None, "10", "0", "IN"),
            ],
        )
    assert sqlstate(err.value) == "23514"
    assert "store_not_negative" in str(err.value)


def test_lot_must_belong_to_the_lines_item(app_engine: Engine, tenant: Tenant) -> None:
    """A flour line cannot carry the murukku lot B-001 (composite FK lot + item + org)."""
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        lot = make_lot(c, tenant, "murukku_200g", "B-001")
        post_journal(
            c,
            tenant,
            "OPENING",
            [
                ("flour", "OPENING", lot, "-100", "-4.20", "OUT"),
                ("flour", "RAW_STORE", lot, "100", "4.20", "IN"),
            ],
        )
    assert sqlstate(err.value) == "23503"


# ---------- D1 and S3: insert-only ledger, read-only projection ----------


def _posted_receipt(app_engine: Engine, t: Tenant) -> None:
    with app_engine.begin() as c:
        as_org(c, t.org)
        post_journal(
            c,
            t,
            "RECEIPT",
            [
                ("flour", "SUPPLIER", None, "-60000", "-2700.00", "OUT"),
                ("flour", "RAW_STORE", None, "60000", "2700.00", "IN"),
            ],
        )


@pytest.mark.parametrize("statement", ["UPDATE stock_lines SET qty_base = qty_base", "DELETE FROM stock_lines"])
def test_app_role_cannot_update_or_delete_stock_lines(app_engine: Engine, tenant: Tenant, statement: str) -> None:
    _posted_receipt(app_engine, tenant)
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        c.execute(text(statement))
    assert sqlstate(err.value) == "42501"  # no privilege: the first wall


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE stock_lines SET value = value + 1 WHERE organization_id = :o",
        "DELETE FROM stock_lines WHERE organization_id = :o",
        "UPDATE stock_journals SET posting_date = '2026-01-01' WHERE organization_id = :o",
        "DELETE FROM stock_journals WHERE organization_id = :o",
    ],
)
def test_stock_line_update_or_delete_rejected_even_for_owner(
    owner_engine: Engine, app_engine: Engine, tenant: Tenant, statement: str
) -> None:
    """The second wall: even the table owner cannot edit or delete a posted journal (trigger)."""
    _posted_receipt(app_engine, tenant)
    with pytest.raises(DBAPIError) as err, owner_engine.begin() as c:
        c.execute(text(statement), {"o": tenant.org})
    assert sqlstate(err.value) == "AH002"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE inventory_balances SET qty_base = 999999",
        "INSERT INTO inventory_balances (organization_id, item_id, location_id, location_kind, qty_base, value)"
        " SELECT organization_id, id, id, 'STORE', 1, 0 FROM items LIMIT 1",
    ],
)
def test_app_cannot_write_balances(app_engine: Engine, tenant: Tenant, statement: str) -> None:
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        c.execute(text(statement))
    assert sqlstate(err.value) == "42501"


def test_reversal_mirrors_and_restores_balance(app_engine: Engine, tenant: Tenant) -> None:
    with app_engine.begin() as c:
        as_org(c, tenant.org)
        original = post_journal(
            c,
            tenant,
            "RECEIPT",
            [
                ("flour", "SUPPLIER", None, "-60000", "-2700.00", "OUT"),
                ("flour", "RAW_STORE", None, "60000", "2700.00", "IN"),
            ],
        )
    with app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "REVERSAL",
            [
                ("flour", "SUPPLIER", None, "60000", "2700.00", "IN"),
                ("flour", "RAW_STORE", None, "-60000", "-2700.00", "OUT"),
            ],
            reason="wrong supplier invoice",
            reverses=original,
        )
    assert _balance(app_engine, tenant, "flour", "RAW_STORE") == (0, 0)
    # a journal can be reversed only once
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, tenant.org)
        post_journal(
            c,
            tenant,
            "REVERSAL",
            [
                ("flour", "SUPPLIER", None, "60000", "2700.00", "IN"),
                ("flour", "RAW_STORE", None, "-60000", "-2700.00", "OUT"),
            ],
            reason="again",
            reverses=original,
        )
    assert sqlstate(err.value) == "23505"


# ---------- the NIT benchmark's journals fit the schema (docs/architecture/ledger.md §3) ----------


def test_nit_journals_balance_and_project(owner_engine: Engine, app_engine: Engine) -> None:
    """J0-J8 from ledger.md posted as raw journals: every one balances and the balances match the oracle."""
    t = make_tenant(owner_engine, "NIT")
    with app_engine.begin() as c:
        as_org(c, t.org)
        open_lot = make_lot(c, t, "murukku_200g", "OPEN-LOT", source="opening")
        b001 = make_lot(c, t, "murukku_200g", "B-001")
        # J0 opening balances
        post_journal(
            c,
            t,
            "OPENING",
            [
                ("flour", "OPENING", None, "-100000", "-4200.00", "OUT"),
                ("flour", "RAW_STORE", None, "100000", "4200.00", "IN"),
                ("oil", "OPENING", None, "-30000", "-4200.00", "OUT"),
                ("oil", "RAW_STORE", None, "30000", "4200.00", "IN"),
                ("spice", "OPENING", None, "-5000", "-1000.00", "OUT"),
                ("spice", "RAW_STORE", None, "5000", "1000.00", "IN"),
                ("pouch_200g", "OPENING", None, "-500", "-1250.00", "OUT"),
                ("pouch_200g", "PACK_STORE", None, "500", "1250.00", "IN"),
                ("carton_20", "OPENING", None, "-30", "-450.00", "OUT"),
                ("carton_20", "PACK_STORE", None, "30", "450.00", "IN"),
                ("murukku_200g", "OPENING", open_lot, "-50", "-1442.50", "OUT"),
                ("murukku_200g", "FG_STORE", open_lot, "50", "1442.50", "IN"),
            ],
        )
        # J1 purchase 60 kg flour at 45
        post_journal(
            c,
            t,
            "RECEIPT",
            [
                ("flour", "SUPPLIER", None, "-60000", "-2700.00", "OUT"),
                ("flour", "RAW_STORE", None, "60000", "2700.00", "IN"),
            ],
        )
        # J2 issue to B-001 at WAC
        post_journal(
            c,
            t,
            "ISSUE",
            [
                ("flour", "RAW_STORE", None, "-40000", "-1725.00", "OUT"),
                ("flour", "WIP", None, "40000", "1725.00", "IN"),
                ("oil", "RAW_STORE", None, "-10500", "-1470.00", "OUT"),
                ("oil", "WIP", None, "10500", "1470.00", "IN"),
                ("spice", "RAW_STORE", None, "-1200", "-240.00", "OUT"),
                ("spice", "WIP", None, "1200", "240.00", "IN"),
            ],
        )
        # J3 completion: 188 good, 6 damaged pouches (quantity only), 9 cartons
        post_journal(
            c,
            t,
            "RUN_COMPLETION",
            [
                ("flour", "WIP", None, "-40000", "-1725.00", "OUT"),
                ("flour", "PRODUCTION", None, "40000", "1725.00", "IN"),
                ("oil", "WIP", None, "-10500", "-1470.00", "OUT"),
                ("oil", "PRODUCTION", None, "10500", "1470.00", "IN"),
                ("spice", "WIP", None, "-1200", "-240.00", "OUT"),
                ("spice", "PRODUCTION", None, "1200", "240.00", "IN"),
                ("pouch_200g", "PACK_STORE", None, "-194", "-485.00", "OUT"),
                ("pouch_200g", "PRODUCTION", None, "188", "485.00", "IN"),
                ("pouch_200g", "SCRAP", None, "6", "0", "SCRAP_IN"),
                ("carton_20", "PACK_STORE", None, "-9", "-135.00", "OUT"),
                ("carton_20", "PRODUCTION", None, "9", "135.00", "IN"),
                ("murukku_200g", "PRODUCTION", b001, "-188", "-4055.00", "OUT"),
                ("murukku_200g", "FG_STORE", b001, "188", "4055.00", "IN"),
            ],
        )
        # J5 dispatch FEFO: 50 OPEN-LOT + 100 B-001 (provisional value)
        post_journal(
            c,
            t,
            "DISPATCH",
            [
                ("murukku_200g", "FG_STORE", open_lot, "-50", "-1442.50", "OUT"),
                ("murukku_200g", "CUSTOMER", open_lot, "50", "1442.50", "IN"),
                ("murukku_200g", "FG_STORE", b001, "-100", "-2156.91", "OUT"),
                ("murukku_200g", "CUSTOMER", b001, "100", "2156.91", "IN"),
            ],
        )
        # J8 late labour + gas 1,800 as a value-only true-up
        post_journal(
            c,
            t,
            "COST_TRUE_UP",
            [
                ("murukku_200g", "CONVERSION_COST", b001, "0", "-1800.00", "VALUE_ONLY"),
                ("murukku_200g", "CUSTOMER", b001, "0", "957.45", "VALUE_ONLY"),
                ("murukku_200g", "FG_STORE", b001, "0", "842.55", "VALUE_ONLY"),
            ],
        )

    assert _balance(app_engine, t, "flour", "RAW_STORE") == (Decimal("120000"), Decimal("5175.00"))  # a01
    assert _balance(app_engine, t, "oil", "RAW_STORE") == (Decimal("19500"), Decimal("2730.00"))  # a02
    assert _balance(app_engine, t, "spice", "RAW_STORE") == (Decimal("3800"), Decimal("760.00"))
    assert _balance(app_engine, t, "pouch_200g", "PACK_STORE")[0] == Decimal("306")  # a03
    assert _balance(app_engine, t, "carton_20", "PACK_STORE")[0] == Decimal("21")
    assert _balance(app_engine, t, "murukku_200g", "FG_STORE") == (Decimal("88"), Decimal("2740.64"))  # a05, a22
    assert _balance(app_engine, t, "murukku_200g", "CUSTOMER") == (Decimal("150"), Decimal("4556.86"))  # COGS A
    for item in ("flour", "oil", "spice"):
        assert _balance(app_engine, t, item, "WIP") == (0, 0)  # S6
    with app_engine.begin() as c:
        as_org(c, t.org)
        b001_total = c.execute(
            text("SELECT sum(value) FROM stock_lines WHERE lot_id = :l AND location_id IN (:fg, :cust)"),
            {"l": b001, "fg": t.locations["FG_STORE"], "cust": t.locations["CUSTOMER"]},
        ).scalar_one()
    assert b001_total == Decimal("5855.00")  # law 2: lot value = run cost
