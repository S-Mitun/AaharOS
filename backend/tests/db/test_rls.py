"""Organization isolation (invariant P2, ADR-0006): the app role can never see or write another tenant's rows."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.db.conftest import as_org, make_tenant, post_journal, sqlstate


def test_cross_org_read_impossible(owner_engine: Engine, app_engine: Engine) -> None:
    a = make_tenant(owner_engine, "A")
    b = make_tenant(owner_engine, "B")
    with app_engine.begin() as c:
        as_org(c, a.org)
        orgs = set(c.execute(text("SELECT DISTINCT organization_id FROM items")).scalars())
        visible_orgs = set(c.execute(text("SELECT id FROM organizations")).scalars())
        b_rows = c.execute(text("SELECT count(*) FROM items WHERE organization_id = :b"), {"b": b.org}).scalar_one()
    assert orgs == {a.org}
    assert visible_orgs == {a.org}
    assert b_rows == 0


def test_no_org_setting_sees_nothing(owner_engine: Engine, app_engine: Engine) -> None:
    make_tenant(owner_engine, "A")
    with app_engine.begin() as c:
        assert c.execute(text("SELECT count(*) FROM items")).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 0


def test_write_into_other_org_rejected(owner_engine: Engine, app_engine: Engine) -> None:
    a = make_tenant(owner_engine, "A")
    b = make_tenant(owner_engine, "B")
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, a.org).execute(
            text("INSERT INTO suppliers (organization_id, code, name, state_code) VALUES (:b, 'X', 'X', '33')"),
            {"b": b.org},
        )
    assert sqlstate(err.value) == "42501"  # new row violates row-level security policy
    with app_engine.begin() as c:
        touched = as_org(c, a.org).execute(
            text("UPDATE customers SET name = 'hijacked' WHERE organization_id = :b"), {"b": b.org}
        )
    assert touched.rowcount == 0


def test_journal_cannot_reference_other_orgs_item(owner_engine: Engine, app_engine: Engine) -> None:
    """Even the owner (who bypasses RLS) cannot mix tenants: the composite FKs refuse it."""
    a = make_tenant(owner_engine, "A")
    b = make_tenant(owner_engine, "B")
    a.items["flour"] = b.items["flour"]  # A's journal pointing at B's flour
    with pytest.raises(DBAPIError) as err, owner_engine.begin() as c:
        post_journal(
            c,
            a,
            "RECEIPT",
            [("flour", "SUPPLIER", None, "-1", "0", "OUT"), ("flour", "RAW_STORE", None, "1", "0", "IN")],
        )
    assert sqlstate(err.value) == "23503"


def test_every_org_scoped_table_has_rls(owner_engine: Engine) -> None:
    """Guards future migrations: a new table with organization_id must also get RLS and a policy."""
    with owner_engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, count(p.polname) FROM pg_class c"
                " JOIN information_schema.columns col ON col.table_name = c.relname AND col.table_schema = 'public'"
                "  AND col.column_name = 'organization_id'"
                " LEFT JOIN pg_policy p ON p.polrelid = c.oid"
                " WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace"
                " GROUP BY c.relname, c.relrowsecurity"
            )
        ).all()
    assert len(rows) == 61
    missing = [name for name, rls, policies in rows if not rls or policies == 0]
    assert missing == []


def test_app_role_cannot_bypass_rls(owner_engine: Engine) -> None:
    with owner_engine.connect() as c:
        row = c.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'aahar_app'")
        ).one()
        owns = c.execute(
            text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = 'aahar_app'")
        ).scalar_one()
    assert tuple(row) == (False, False, True)
    assert owns == 0  # table owners skip RLS; the app role owns nothing


def test_new_tenant_can_be_created(app_engine: Engine) -> None:
    """A fresh BENCHMARK organization per replay (ADR-0006) needs no owner rights."""
    org = uuid.uuid4()
    with app_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO organizations (id, code, name, kind, state_code)"
                " VALUES (:id, :code, 'DEMO benchmark', 'BENCHMARK', '33')"
            ),
            {"id": org, "code": f"BENCHMARK-{org.hex[:8]}"},
        )
    with app_engine.begin() as c:
        assert as_org(c, org).execute(text("SELECT count(*) FROM organizations")).scalar_one() == 1
