"""MP07: standard cost cards and their lines are append-only (ADR-0014, decision F4).

A run's waterfall reads the card in force on its run date, so editing a card would silently revalue past runs.
Standards change by adding a new card version. The app role keeps SELECT and INSERT only, and the existing
`aahar_forbid_change()` trigger refuses UPDATE and DELETE even for the owner (SQLSTATE AH002).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"
TABLES = ("standard_cost_cards", "standard_cost_lines")


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
