"""MP10: dispatches keep their mock e-way bill payload, and a dispatch is written once (ADR-0017, J6/J7).

A dispatch row is inserted complete (its journal is posted first), so the app role needs no UPDATE or DELETE on it,
and the existing `aahar_forbid_change()` trigger refuses both even for the owner (SQLSTATE AH002). The e-way bill
payload is a MOCK (never sent to the portal) kept for the record.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"


def upgrade() -> None:
    op.add_column("dispatches", sa.Column("eway_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.execute(f"REVOKE UPDATE, DELETE ON dispatches FROM {APP_ROLE}")
    op.execute(
        "CREATE TRIGGER trg_dispatches_immutable BEFORE UPDATE OR DELETE ON dispatches"
        " FOR EACH ROW EXECUTE FUNCTION aahar_forbid_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_dispatches_immutable ON dispatches")
    op.execute(f"GRANT UPDATE, DELETE ON dispatches TO {APP_ROLE}")
    op.drop_column("dispatches", "eway_payload")
