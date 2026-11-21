"""`make seed-demo`: the LIVE DEMO factory and one DEMO login per role (passwords from .env, never printed).

Idempotent: re-running updates names, roles and passwords; it never deletes anything. Customers, items and the
salesman-to-customer assignments come with the master-data seed (MP05).
"""

import os
import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401 - registers every table for the ORM
from app.core.config import get_settings
from app.core.db import org_scope
from app.modules.audit import service as audit
from app.modules.identity.domain import hash_password

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


def main() -> int:
    engine = create_engine(get_settings().migration_database_url)
    with Session(engine) as session:
        seeded = seed(session)
        session.commit()
    engine.dispose()
    print(f"DEMO organization {ORG_CODE}: {len(seeded)} logins (passwords from .env, DEMO_PASSWORD_<ROLE>)")
    for email, role in seeded:
        print(f"  {role:<11} {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
