"""Fixtures for tests that need PostgreSQL.

They run against a throwaway database (`aaharos_test` by default) on the server named by AAHAR_TEST_DATABASE_URL,
connecting as the owner to migrate and set up, and as `aahar_app` (row-level security applies) to act like the API.
If the server is unreachable the tests are skipped, unless AAHAR_REQUIRE_DB=1 (Docker and CI), where they fail.
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[2]


def owner_url(database: str | None = None) -> str:
    raw = os.environ.get("AAHAR_TEST_DATABASE_URL")
    url = make_url(raw) if raw else make_url(get_settings().migration_database_url).set(database="aaharos_test")
    if database:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)


def app_url(database: str) -> str:
    url = make_url(owner_url(database)).set(username="aahar_app", password=get_settings().app_db_password)
    return url.render_as_string(hide_password=False)


def recreate_database(name: str) -> None:
    admin = create_engine(owner_url("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                    " WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
            c.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()


def alembic_config(database: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", owner_url(database).replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def database_available() -> None:
    try:
        engine = create_engine(owner_url("postgres"))
        with engine.connect():
            pass
        engine.dispose()
    except Exception as exc:  # pragma: no cover - depends on the environment
        if os.environ.get("AAHAR_REQUIRE_DB") == "1":
            pytest.fail(f"PostgreSQL is required (AAHAR_REQUIRE_DB=1) but unreachable: {exc}")
        pytest.skip(f"PostgreSQL unreachable, database tests skipped: {exc}")


TEST_DB = "aaharos_test"


@pytest.fixture(scope="session")
def migrated(database_available: None) -> str:
    recreate_database(TEST_DB)
    command.upgrade(alembic_config(TEST_DB), "head")
    return TEST_DB


@pytest.fixture(scope="session")
def owner_engine(migrated: str) -> Iterator[Engine]:
    engine = create_engine(owner_url(migrated))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(migrated: str) -> Iterator[Engine]:
    engine = create_engine(app_url(migrated))
    yield engine
    engine.dispose()


def as_org(conn: Connection, org_id: uuid.UUID) -> Connection:
    """Bind this transaction to one organization, exactly as `app.core.db.org_scope` does."""
    conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_id)})
    return conn


@dataclass
class Tenant:
    org: uuid.UUID
    items: dict[str, uuid.UUID]
    locations: dict[str, uuid.UUID]
    customer: uuid.UUID


LOCATIONS = {
    "RAW_STORE": "STORE",
    "PACK_STORE": "STORE",
    "WIP": "STORE",
    "FG_STORE": "STORE",
    "OPENING": "VIRTUAL",
    "SUPPLIER": "VIRTUAL",
    "PRODUCTION": "VIRTUAL",
    "CONVERSION_COST": "VIRTUAL",
    "SCRAP": "VIRTUAL",
    "CUSTOMER": "VIRTUAL",
    "ADJUSTMENT": "VIRTUAL",
}

# code: (kind, base uom, stock uom, lot tracked)
ITEMS = {
    "flour": ("RAW", "g", "kg", False),
    "oil": ("RAW", "mL", "L", False),
    "spice": ("RAW", "g", "kg", False),
    "pouch_200g": ("PACK", "piece", "piece", False),
    "carton_20": ("PACK", "piece", "piece", False),
    "murukku_200g": ("FG", "piece", "packet", True),
}


def make_tenant(owner: Engine, label: str = "T") -> Tenant:
    """A fresh DEMO organization with the benchmark's locations and items (set up as the owner)."""
    org = uuid.uuid4()
    with owner.begin() as c:
        c.execute(
            text(
                "INSERT INTO organizations (id, code, name, kind, state_code)"
                " VALUES (:id, :code, :name, 'BENCHMARK', '33')"
            ),
            {"id": org, "code": f"DEMO-{label}-{org.hex[:8]}", "name": f"DEMO factory {label}"},
        )
        locations = {}
        for code, kind in LOCATIONS.items():
            locations[code] = c.execute(
                text("INSERT INTO locations (organization_id, code, name, kind) VALUES (:o, :c, :c, :k) RETURNING id"),
                {"o": org, "c": code, "k": kind},
            ).scalar_one()
        items = {}
        for code, (kind, base, stock, lot) in ITEMS.items():
            items[code] = c.execute(
                text(
                    "INSERT INTO items (organization_id, code, name, kind, base_uom, stock_uom, lot_tracked)"
                    " VALUES (:o, :c, :c, :k, :b, :s, :l) RETURNING id"
                ),
                {"o": org, "c": code, "k": kind, "b": base, "s": stock, "l": lot},
            ).scalar_one()
        customer = c.execute(
            text(
                "INSERT INTO customers (organization_id, code, name, kind, state_code)"
                " VALUES (:o, 'RET-A', 'DEMO Retailer A', 'RETAILER', '33') RETURNING id"
            ),
            {"o": org},
        ).scalar_one()
    return Tenant(org=org, items=items, locations=locations, customer=customer)


@pytest.fixture
def tenant(owner_engine: Engine) -> Tenant:
    return make_tenant(owner_engine)


SOURCE_FOR_KIND = {
    "OPENING": "opening",
    "RECEIPT": "purchase_receipt",
    "ISSUE": "material_issue",
    "RETURN": "material_issue",
    "RUN_COMPLETION": "production_run",
    "COST_TRUE_UP": "run_cost",
    "DISPATCH": "dispatch",
    "SALES_RETURN": "sales_return",
    "ADJUSTMENT": "stock_count",
    "REVERSAL": "stock_journal",
}

# (item code, location code, lot id or None, qty in base units, value in rupees, line role)
Line = tuple[str, str, uuid.UUID | None, str, str, str]


def post_journal(
    conn: Connection,
    t: Tenant,
    kind: str,
    lines: list[Line],
    *,
    posting_date: str = "2026-11-21",
    reason: str | None = None,
    reverses: uuid.UUID | None = None,
    approved_by: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one journal and its lines. Balance is checked by the deferred trigger at commit."""
    journal = conn.execute(
        text(
            "INSERT INTO stock_journals (organization_id, kind, source_type, source_id, posting_date, reason,"
            " reverses_journal_id, approved_by) VALUES (:o, :k, :s, :sid, :d, :r, :rev, :appr) RETURNING id"
        ),
        {
            "o": t.org,
            "k": kind,
            "s": SOURCE_FOR_KIND[kind],
            "sid": uuid.uuid4(),
            "d": posting_date,
            "r": reason,
            "rev": reverses,
            "appr": approved_by,
        },
    ).scalar_one()
    for n, (item, loc, lot, qty, value, role) in enumerate(lines, start=1):
        conn.execute(
            text(
                "INSERT INTO stock_lines (organization_id, journal_id, line_no, item_id, location_id, lot_id,"
                " qty_base, value, line_role) VALUES (:o, :j, :n, :i, :l, :lot, :q, :v, :role)"
            ),
            {
                "o": t.org,
                "j": journal,
                "n": n,
                "i": t.items[item],
                "l": t.locations[loc],
                "lot": lot,
                "q": qty,
                "v": value,
                "role": role,
            },
        )
    return journal


def make_lot(conn: Connection, t: Tenant, item: str, lot_no: str, source: str = "production_run") -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO lots (organization_id, item_id, lot_no, mfg_date, best_before, source_type)"
            " VALUES (:o, :i, :n, '2026-11-21', '2027-02-19', :s) RETURNING id"
        ),
        {"o": t.org, "i": t.items[item], "n": lot_no, "s": source},
    ).scalar_one()


def sqlstate(exc: BaseException) -> str | None:
    """The PostgreSQL SQLSTATE behind a SQLAlchemy error (AH001, 23514, 42501, ...)."""
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None)


def make_user(owner: Engine, label: str = "user") -> uuid.UUID:
    """A DEMO user (global table, created as the owner)."""
    uid = uuid.uuid4()
    with owner.begin() as c:
        c.execute(
            text("INSERT INTO users (id, email, display_name) VALUES (:id, :e, :n)"),
            {"id": uid, "e": f"{label}-{uid.hex[:8]}@demo.invalid", "n": f"DEMO {label}"},
        )
    return uid
