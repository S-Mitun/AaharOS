"""MP08: price list items are append-only (ADR-0015, decision G1).

An order line's `price_captured` is taken from one price list version. Editing that version's items afterwards would
leave the captured price with no list to trace it to, so prices change by publishing a new version. The app role
keeps SELECT and INSERT only, and the existing `aahar_forbid_change()` trigger refuses UPDATE and DELETE even for the
owner (SQLSTATE AH002).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"
TABLES = ("price_list_items",)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM {APP_ROLE}")
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION aahar_forbid_change()"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
        op.execute(f"GRANT UPDATE, DELETE ON {table} TO {APP_ROLE}")
