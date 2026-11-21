"""`make e2e` setup: a fresh scratch tenant with its own DEMO logins, so Playwright never touches the DEMO factory.

Prints one JSON object (organization code, emails, a random per-run password) to stdout; the Makefile writes it to
e2e/.tenant.json (git-ignored) for the Playwright container. The tenant is a SIM organization (ADR-0006: scratch
tenants are kept, never deleted; Judge Mode reads only BENCHMARK tenants), with the section 5 master data, the
opening stock and the general price list, and Retailer A assigned to the salesman.
"""

import json
import secrets
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401 - registers every table for the ORM
from app.core.config import get_settings
from app.core.db import get_engine, org_scope
from app.core.oracle import load_oracle
from app.modules.identity import service as identity
from app.modules.identity.domain import hash_password
from app.modules.judge.replay import post_section5_opening, setup_section5

ROLES = ("SALESMAN", "ADMIN", "OWNER")


def main() -> int:
    oracle = load_oracle(get_settings().oracle_path)
    with Session(get_engine(), expire_on_commit=False) as app_session:
        org = identity.create_scratch_tenant(app_session, kind="SIM", label="E2E")
        s5 = setup_section5(app_session, oracle, org)
        post_section5_opening(app_session, oracle, s5)
        app_session.commit()
        code = app_session.execute(text("SELECT code FROM organizations WHERE id = :o"), {"o": org}).scalar_one()

    password = secrets.token_urlsafe(18)
    emails: dict[str, str] = {}
    user_ids = {}
    owner = create_engine(get_settings().migration_database_url)
    with Session(owner) as session:
        for role in ROLES:
            email = f"{role.lower()}-e2e-{secrets.token_hex(5)}@aaharos-demo.invalid"
            user_ids[role] = session.execute(
                text("INSERT INTO users (email, display_name, password_hash) VALUES (:e, :n, :h) RETURNING id"),
                {"e": email, "n": f"{role.title()} (DEMO e2e)", "h": hash_password(password)},
            ).scalar_one()
            session.execute(
                text("INSERT INTO memberships (organization_id, user_id, role_code) VALUES (:o, :u, :r)"),
                {"o": org, "u": user_ids[role], "r": role},
            )
            emails[role] = email
        session.commit()
    owner.dispose()

    with Session(get_engine(), expire_on_commit=False) as app_session:
        org_scope(app_session, org)
        identity.assign_customer(
            app_session,
            organization_id=org,
            actor_id=None,
            salesman_id=user_ids["SALESMAN"],
            customer_id=s5.customer_ids["RET-A"],
            route_order=1,
        )
        app_session.commit()

    json.dump(
        {
            "organization_code": code,
            "emails": emails,
            "password": password,
            "item_id": str(s5.item_ids["murukku_200g"]),
            "customer_id": str(s5.customer_ids["RET-A"]),
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
