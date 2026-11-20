"""Extensions and the application's non-owner database role (ADR-0006).

The API connects as `aahar_app`: not a superuser, not the table owner, no BYPASSRLS, so row-level security
applies to every query it runs. Migrations keep running as the owner.

Roles are cluster-wide, so downgrade only removes this database's grants (DROP OWNED); it never drops the role,
which other databases on the same server (e.g. the test database) may still use.

Revision ID: 0001
Revises:
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

from app.core.config import get_settings

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    password = _sql_literal(get_settings().app_db_password)
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {password};
          ELSE
            ALTER ROLE {APP_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {password};
          END IF;
        END
        $$;
        """
    )
    op.execute(f"DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {APP_ROLE}', current_database()); END $$;")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP OWNED BY {APP_ROLE}")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
