"""`make seed-demo`: the LIVE DEMO factory and one DEMO login per role (passwords from .env, never printed).

Idempotent: re-running updates names, roles and passwords; it never deletes anything.

MP05 adds the DEMO master data on the first run only (MP06 adds the recipe, the pack specs and the tolerance to it):
the section 5 items, a DEMO supplier, Retailer A and Distributor B, salesman A -> Retailer A and salesman B ->
Distributor B, and the valued opening stock. Users and the LIVE organization are written as the owner (the app role
may not create LIVE tenants); the master data is written as `aahar_app`, scoped to the organization, because the
owner bypasses row-level security and the services rely on it.
"""

import os
import sys
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401 - registers every table for the ORM
from app.core import effective_settings
from app.core.config import get_settings
from app.core.db import get_engine, org_scope
from app.core.errors import NotFoundError
from app.core.oracle import load_oracle
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.identity import service as identity
from app.modules.identity.domain import hash_password
from app.modules.judge.replay import (
    B2CL_THRESHOLD_DEMO,
    CREDIT_LIMITS,
    EXTRA_ITEMS,
    ITEMS,
    PAYMENT_TERMS_DAYS,
    PRICE_LIST_CODE,
    RECIPE,
    SETTINGS_FROM,
    post_section5_opening,
    setup_section5,
    setup_section5_bom,
    setup_section5_price_list,
    setup_section5_tax,
)
from app.modules.recipe import service as recipes
from app.modules.sales import service as sales
from app.modules.tax import service as tax

ORG_CODE = "DEMO-FACTORY"
ORG_NAME = "AaharOS Demo Snacks (DEMO)"
DEFAULT_DEMO_PASSWORD = "change-me-demo"  # noqa: S105 - the documented DEMO default from .env.example

# (email, display name, role, environment variable holding the password)
DEMO_USERS = (
    ("salesman.a@aaharos-demo.invalid", "Salesman A (DEMO)", "SALESMAN", "DEMO_PASSWORD_SALESMAN"),
    ("salesman.b@aaharos-demo.invalid", "Salesman B (DEMO)", "SALESMAN", "DEMO_PASSWORD_SALESMAN"),
    ("admin@aaharos-demo.invalid", "Factory Admin (DEMO)", "ADMIN", "DEMO_PASSWORD_ADMIN"),
    ("production@aaharos-demo.invalid", "Production Supervisor (DEMO)", "PRODUCTION", "DEMO_PASSWORD_PRODUCTION"),
    ("auditor@aaharos-demo.invalid", "Auditor (DEMO)", "AUDITOR", "DEMO_PASSWORD_AUDITOR"),
    ("owner@aaharos-demo.invalid", "Owner (DEMO)", "OWNER", "DEMO_PASSWORD_OWNER"),
)


def seed(session: Session) -> list[tuple[str, str]]:
    org_id = session.execute(text("SELECT id FROM organizations WHERE code = :c"), {"c": ORG_CODE}).scalar()
    if org_id is None:
        org_id = uuid.uuid4()
        session.execute(
            text("INSERT INTO organizations (id, code, name, kind, state_code) VALUES (:i, :c, :n, 'LIVE', '33')"),
            {"i": org_id, "c": ORG_CODE, "n": ORG_NAME},
        )
    org_scope(session, org_id)
    seeded: list[tuple[str, str]] = []
    for email, name, role, env in DEMO_USERS:
        password = os.environ.get(env) or DEFAULT_DEMO_PASSWORD
        user_id = session.execute(
            text(
                "INSERT INTO users (email, display_name, password_hash) VALUES (:e, :n, :h)"
                " ON CONFLICT ((lower(email))) DO UPDATE SET display_name = EXCLUDED.display_name,"
                " password_hash = EXCLUDED.password_hash, is_active = true RETURNING id"
            ),
            {"e": email, "n": name, "h": hash_password(password)},
        ).scalar_one()
        session.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role_code) VALUES (:o, :u, :r)"
                " ON CONFLICT (organization_id, user_id) DO UPDATE SET role_code = EXCLUDED.role_code, is_active = true"
            ),
            {"o": org_id, "u": user_id, "r": role},
        )
        seeded.append((email, role))
    audit.record(
        session,
        organization_id=org_id,
        actor_id=None,
        action="seed.demo_users",
        entity_type="organization",
        entity_id=org_id,
        after={"users": [f"{e} ({r})" for e, r in seeded]},
        note="make seed-demo",
    )
    return seeded


# salesman email -> customer code (MP03 row filter: each salesman sees only these)
ASSIGNMENTS = (("salesman.a@aaharos-demo.invalid", "RET-A"), ("salesman.b@aaharos-demo.invalid", "DIST-B"))


def seed_master_data(app_session: Session, org_id: uuid.UUID, user_ids: dict[str, uuid.UUID]) -> bool:
    """First run only: section 5 master data, assignments and opening stock. Returns False if already there."""
    org_scope(app_session, org_id)
    try:
        catalog.id_by_code(app_session, "flour")
        return False
    except NotFoundError:
        pass
    oracle = load_oracle(get_settings().oracle_path)
    s5 = setup_section5(app_session, oracle, org_id)
    for n, (email, customer) in enumerate(ASSIGNMENTS, start=1):
        identity.assign_customer(
            app_session,
            organization_id=org_id,
            actor_id=None,
            salesman_id=user_ids[email],
            customer_id=s5.customer_ids[customer],
            route_order=n,
        )
    post_section5_opening(app_session, oracle, s5)
    return True


def top_up_master_data(app_session: Session, org_id: uuid.UUID) -> list[str]:
    """An existing DEMO factory seeded by an earlier MP gets what later MPs added, if missing: the MP06 items,
    recipe, pack specs, standard cost card and tolerance, and the MP08 price list. Nothing is changed or deleted."""
    org_scope(app_session, org_id)
    oracle = load_oracle(get_settings().oracle_path)
    added: list[str] = []
    ids = {code: catalog.id_by_code(app_session, code) for code in ITEMS}
    for code, (kind, base, stock) in EXTRA_ITEMS.items():
        try:
            ids[code] = catalog.id_by_code(app_session, code)
        except NotFoundError:
            ids[code] = catalog.create_item(
                app_session,
                organization_id=org_id,
                actor_id=None,
                code=code,
                name=f"DEMO {code.replace('_', ' ')}",
                kind=kind,
                base_uom=base,
                stock_uom=stock,
                lot_tracked=kind == "FG",
            )
            added.append(f"item {code}")
    if RECIPE[0] not in {r["code"] for r in recipes.list_recipes(app_session)}:
        setup_section5_bom(app_session, oracle, org_id, ids)
        added.append("recipe v1, 200 g / 500 g pack specs, standard cost card, tolerance")
    if PRICE_LIST_CODE not in {p["code"] for p in sales.list_price_lists(app_session)}:
        setup_section5_price_list(app_session, oracle, org_id, ids)
        added.append("price list GENERAL v1")
    if not tax.rules(app_session):  # MP10: HSN, the GST rule, the DEMO business profile, e-way thresholds
        setup_section5_tax(app_session, oracle, org_id, ids)
        added.append("GST rule, HSN, DEMO business profile and e-way thresholds")
        for code in CREDIT_LIMITS:
            customer_id = sales.customer_id_by_code(app_session, code)
            if customer_id is not None and sales.customer_terms(app_session, customer_id)["payment_terms_days"] == 0:
                sales.set_payment_terms(
                    app_session,
                    organization_id=org_id,
                    actor_id=None,
                    customer_id=customer_id,
                    days=PAYMENT_TERMS_DAYS,
                    msme_terms=True,
                )
                added.append(f"payment terms {code}")
    if effective_settings.value_on(app_session, "gst.b2cl_threshold", date.today()) is None:  # MP11
        tax.put_setting(
            app_session,
            organization_id=org_id,
            actor_id=None,
            key="gst.b2cl_threshold",
            value=B2CL_THRESHOLD_DEMO,
            effective_from=SETTINGS_FROM,
        )
        added.append("GSTR-1 B2CL threshold")
    for key, margin in (
        ("bank.stock_margin_pct", Decimal("25")),
        ("bank.debtors_margin_pct", Decimal("40")),
        ("planning.attribution_days", Decimal("30")),  # MP12
    ):
        if effective_settings.value_on(app_session, key, date.today()) is None:
            tax.put_setting(
                app_session, organization_id=org_id, actor_id=None, key=key, value=margin, effective_from=SETTINGS_FROM
            )
            added.append(f"DEMO {key}")
    for code, limit in CREDIT_LIMITS.items():  # MP09: only where no limit was ever set
        customer_id = sales.customer_id_by_code(app_session, code)
        if customer_id is not None and sales.credit_limit_of(app_session, customer_id) == 0:
            sales.set_credit_limit(
                app_session, organization_id=org_id, actor_id=None, customer_id=customer_id, limit=limit
            )
            added.append(f"credit limit {code}")
    return added


def main() -> int:
    engine = create_engine(get_settings().migration_database_url)
    with Session(engine) as session:
        seeded = seed(session)
        session.commit()
        org_id = session.execute(text("SELECT id FROM organizations WHERE code = :c"), {"c": ORG_CODE}).scalar_one()
        user_ids = dict(
            session.execute(
                text("SELECT email, id FROM users WHERE email = ANY(:e)"), {"e": [e for e, _ in ASSIGNMENTS]}
            )
            .tuples()
            .all()
        )
    engine.dispose()
    with Session(get_engine(), expire_on_commit=False) as app_session:
        added = seed_master_data(app_session, org_id, user_ids)
        topped_up = [] if added else top_up_master_data(app_session, org_id)
        app_session.commit()
    print(f"DEMO organization {ORG_CODE}: {len(seeded)} logins (passwords from .env, DEMO_PASSWORD_<ROLE>)")
    for email, role in seeded:
        print(f"  {role:<11} {email}")
    if added:
        print("  master data: 9 items, 1 supplier, 2 customers (assigned to salesman A / B), opening stock posted,")
        print("  recipe v1 and the 200 g / 500 g pack specs (ACTIVE), variance tolerance 3%, price list GENERAL v1")
    elif topped_up:
        print("  master data topped up: " + "; ".join(topped_up))
    else:
        print("  master data already present: left unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
