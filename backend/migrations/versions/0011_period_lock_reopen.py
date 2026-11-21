"""MP11: a closed month can be reopened with a reason, and the lock is never deleted (ADR-0018, K5).

- period_locks gets its own id; reopening fills reopened_at / reopened_by / reopen_reason once (a guard trigger
  refuses any other change and every DELETE, even for the owner, SQLSTATE AH002).
- At most one active (not reopened) lock per organization and month: a partial unique index.
- `aahar_period_is_locked` ignores reopened locks, so postings are refused only while a month is closed.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"

GUARD = """
CREATE FUNCTION aahar_guard_period_lock() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'a period lock is never deleted: reopen it with a reason' USING ERRCODE = 'AH002';
  END IF;
  IF OLD.reopened_at IS NOT NULL THEN
    RAISE EXCEPTION 'this lock was already reopened: close the month again instead' USING ERRCODE = 'AH002';
  END IF;
  IF NEW.reopened_at IS NULL
     OR length(trim(coalesce(NEW.reopen_reason, ''))) = 0
     OR NOT aahar_same_except(to_jsonb(OLD), to_jsonb(NEW), ARRAY['reopened_at', 'reopened_by', 'reopen_reason']) THEN
    RAISE EXCEPTION 'only reopening (time, who, reason) may change a period lock' USING ERRCODE = 'AH002';
  END IF;
  RETURN NEW;
END
$$;
"""

IS_LOCKED = """
CREATE OR REPLACE FUNCTION aahar_period_is_locked(p_org uuid, p_date date) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM period_locks
    WHERE organization_id = p_org AND period = date_trunc('month', p_date)::date AND reopened_at IS NULL
  )
$$;
"""

IS_LOCKED_BEFORE = """
CREATE OR REPLACE FUNCTION aahar_period_is_locked(p_org uuid, p_date date) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM period_locks
    WHERE organization_id = p_org AND period = date_trunc('month', p_date)::date
  )
$$;
"""


def upgrade() -> None:
    op.add_column(
        "period_locks", sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)
    )
    op.add_column("period_locks", sa.Column("reopened_at", postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("period_locks", sa.Column("reopened_by", sa.UUID(), nullable=True))
    op.add_column("period_locks", sa.Column("reopen_reason", sa.Text(), nullable=True))
    op.create_foreign_key(op.f("fk_period_locks_reopened_by_users"), "period_locks", "users", ["reopened_by"], ["id"])
    op.drop_constraint("pk_period_locks", "period_locks", type_="primary")
    op.create_primary_key("pk_period_locks", "period_locks", ["id"])
    op.create_index(
        "uq_period_locks_active",
        "period_locks",
        ["organization_id", "period"],
        unique=True,
        postgresql_where=sa.text("reopened_at IS NULL"),
    )
    op.create_check_constraint(
        op.f("ck_period_locks_reopen_needs_reason"),
        "period_locks",
        "reopened_at IS NULL OR length(trim(coalesce(reopen_reason, ''))) > 0",
    )
    op.execute(IS_LOCKED)
    op.execute(GUARD)
    op.execute(
        "CREATE TRIGGER trg_period_locks_guard BEFORE UPDATE OR DELETE ON period_locks"
        " FOR EACH ROW EXECUTE FUNCTION aahar_guard_period_lock()"
    )
    op.execute(f"REVOKE UPDATE, DELETE ON period_locks FROM {APP_ROLE}")
    op.execute(f"GRANT UPDATE (reopened_at, reopened_by, reopen_reason) ON period_locks TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_period_locks_guard ON period_locks")
    op.execute("DROP FUNCTION IF EXISTS aahar_guard_period_lock()")
    op.execute(IS_LOCKED_BEFORE)
    op.execute("DELETE FROM period_locks WHERE reopened_at IS NOT NULL")
    op.drop_constraint(op.f("ck_period_locks_reopen_needs_reason"), "period_locks", type_="check")
    op.drop_index("uq_period_locks_active", table_name="period_locks")
    op.drop_constraint("pk_period_locks", "period_locks", type_="primary")
    op.create_primary_key("pk_period_locks", "period_locks", ["organization_id", "period"])
    op.drop_constraint(op.f("fk_period_locks_reopened_by_users"), "period_locks", type_="foreignkey")
    for column in ("reopen_reason", "reopened_by", "reopened_at", "id"):
        op.drop_column("period_locks", column)
