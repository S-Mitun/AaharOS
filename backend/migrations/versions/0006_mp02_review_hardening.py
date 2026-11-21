"""MP02 review hardening: same-org check before privileged triggers; the app may create only test tenants.

1. PostgreSQL runs BEFORE triggers before it applies the row-level-security WITH CHECK. The allocation guard is
   SECURITY DEFINER (it must lock payment and invoice rows), so without this an app session could insert an
   allocation stamped with another organization's id and learn that organization's invoice number or status
   from the guard's error message before RLS rejected the row. A new BEFORE trigger, named so it fires first
   (triggers fire in name order), rejects any app-role row whose organization_id is not the session's org.
2. The app role may create BENCHMARK and SIM organizations (a fresh tenant per replay, ADR-0006), never LIVE ones.
   The LIVE demo factory is created by the owner-run seed command.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"

# Tables whose BEFORE triggers run with owner rights (SECURITY DEFINER) and could otherwise see another tenant.
DEFINER_GUARDED = ("payment_allocations",)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE FUNCTION aahar_require_current_org() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF session_user = '{APP_ROLE}' AND NEW.organization_id IS DISTINCT FROM aahar_current_org() THEN
            RAISE EXCEPTION 'row belongs to a different organization than this session'
              USING ERRCODE = '42501';
          END IF;
          RETURN NEW;
        END
        $$
        """
    )
    for table in DEFINER_GUARDED:
        # "trg_<table>_0_same_org" sorts before every other trg_<table>_* trigger, so it fires first.
        op.execute(
            f"CREATE TRIGGER trg_{table}_0_same_org BEFORE INSERT OR UPDATE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION aahar_require_current_org()"
        )

    op.execute("DROP POLICY org_create ON organizations")
    op.execute("CREATE POLICY org_create ON organizations FOR INSERT WITH CHECK (kind IN ('BENCHMARK', 'SIM'))")


def downgrade() -> None:
    op.execute("DROP POLICY org_create ON organizations")
    op.execute("CREATE POLICY org_create ON organizations FOR INSERT WITH CHECK (true)")
    for table in DEFINER_GUARDED:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_0_same_org ON {table}")
    op.execute("DROP FUNCTION IF EXISTS aahar_require_current_org()")
