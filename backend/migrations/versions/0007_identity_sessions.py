"""MP03 identity: login sessions, rotating refresh tokens, login attempts, the permission matrix, users RLS.

- `auth_sessions` and `refresh_tokens` are org-scoped (RLS); `login_attempts` is global (before any org is known).
- `memberships.is_active`: deactivation is per organization.
- `users` gets RLS: a session sees itself and the members of its own organization, so password hashes of other
  tenants' users are never readable. Login runs before an org is chosen, through the narrow SECURITY DEFINER
  function `aahar_login_lookup(email)`.
- `role_permissions` is seeded from a frozen copy of the matrix in `app/modules/identity/domain.py`
  (tests/db/test_rbac.py keeps the two identical).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"

_READ = ("customer.read", "order.read", "stock.read", "report.read", "audit.read")
_ALL = (
    *_READ,
    "customer.manage",
    "order.create",
    "order.approve",
    "order.amend",
    "price.manage",
    "invoice.post",
    "invoice.cancel",
    "credit_note.post",
    "dispatch.post",
    "payment.post",
    "receipt.post",
    "stock.adjust",
    "stock.adjust.approve",
    "recipe.manage",
    "run.start",
    "run.complete",
    "run.cost",
    "run.reverse",
    "settings.manage",
    "period.lock",
    "period.reopen",
    "user.manage",
    "benchmark.run",
)
MATRIX: dict[str, tuple[str, ...]] = {
    "SALESMAN": ("customer.read", "order.read", "order.create", "stock.read"),
    "ADMIN": (
        "customer.read",
        "customer.manage",
        "order.read",
        "order.approve",
        "order.amend",
        "price.manage",
        "invoice.post",
        "invoice.cancel",
        "credit_note.post",
        "dispatch.post",
        "payment.post",
        "stock.read",
        "stock.adjust",
        "run.cost",
        "run.reverse",
        "settings.manage",
        "period.lock",
        "report.read",
        "benchmark.run",
    ),
    "PRODUCTION": (
        "stock.read",
        "receipt.post",
        "recipe.manage",
        "run.start",
        "run.complete",
        "run.cost",
        "stock.adjust",
        "report.read",
    ),
    "AUDITOR": _READ,
    "OWNER": _ALL,
}

FUNCTIONS = """
CREATE FUNCTION aahar_current_user() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$$;

-- Login happens before an organization is chosen, so it cannot go through RLS. This is the only way in:
-- given an email, the user's hash, status and memberships. Nothing else about any tenant is exposed.
CREATE FUNCTION aahar_login_lookup(p_email text)
RETURNS TABLE (
  user_id uuid, password_hash text, is_active boolean,
  organization_id uuid, organization_code text, role_code text, membership_active boolean
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT u.id, u.password_hash, u.is_active, m.organization_id, o.code, m.role_code, m.is_active
    FROM users u
    LEFT JOIN memberships m ON m.user_id = u.id
    LEFT JOIN organizations o ON o.id = m.organization_id
   WHERE lower(u.email) = lower(p_email)
$$;
REVOKE EXECUTE ON FUNCTION aahar_login_lookup(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aahar_login_lookup(text) TO aahar_app;
"""

# memberships is itself RLS-filtered, so this means "myself, or members of my organization"
USERS_VISIBLE = "id = aahar_current_user() OR EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = users.id)"


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email_lower", sa.Text(), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    op.create_index(
        op.f("ix_login_attempts_email_lower_attempted_at"), "login_attempts", ["email_lower", "attempted_at"]
    )
    op.create_index(op.f("ix_login_attempts_ip_attempted_at"), "login_attempts", ["ip", "attempted_at"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_auth_sessions_expires_after_created")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_auth_sessions_created_by_users")),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name=op.f("fk_auth_sessions_organization_id_organizations")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("id", "organization_id", name=op.f("uq_auth_sessions_id_organization_id")),
    )
    op.create_index(op.f("ix_auth_sessions_organization_id"), "auth_sessions", ["organization_id"])
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("octet_length(token_hash) = 32", name=op.f("ck_refresh_tokens_sha256_length")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_refresh_tokens_created_by_users")),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name=op.f("fk_refresh_tokens_organization_id_organizations")
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "organization_id"],
            ["auth_sessions.id", "auth_sessions.organization_id"],
            name=op.f("fk_refresh_tokens_session_id_organization_id_auth_sessions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_organization_id"), "refresh_tokens", ["organization_id"])
    op.create_index(op.f("ix_refresh_tokens_session_id"), "refresh_tokens", ["session_id"])
    op.add_column("memberships", sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False))

    op.execute(FUNCTIONS)

    for table in ("auth_sessions", "refresh_tokens"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY org_isolation ON {table}"
            " USING (organization_id = aahar_current_org()) WITH CHECK (organization_id = aahar_current_org())"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON login_attempts TO {APP_ROLE}")

    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY user_visible ON users FOR SELECT USING ({USERS_VISIBLE})")
    op.execute(f"CREATE POLICY user_update ON users FOR UPDATE USING ({USERS_VISIBLE}) WITH CHECK ({USERS_VISIBLE})")
    op.execute("CREATE POLICY user_insert ON users FOR INSERT WITH CHECK (true)")

    role_permissions = sa.table("role_permissions", sa.column("role_code"), sa.column("permission_code"))
    op.bulk_insert(
        role_permissions,
        [{"role_code": role, "permission_code": perm} for role, perms in MATRIX.items() for perm in perms],
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions")
    for policy in ("user_insert", "user_update", "user_visible"):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS aahar_login_lookup(text)")
    op.execute("DROP FUNCTION IF EXISTS aahar_current_user()")
    op.drop_column("memberships", "is_active")
    op.drop_index(op.f("ix_refresh_tokens_session_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_organization_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_auth_sessions_organization_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index(op.f("ix_login_attempts_ip_attempted_at"), table_name="login_attempts")
    op.drop_index(op.f("ix_login_attempts_email_lower_attempted_at"), table_name="login_attempts")
    op.drop_table("login_attempts")
