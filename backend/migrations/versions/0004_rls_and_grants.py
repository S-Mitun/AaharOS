"""Row-level security on every org-scoped table, and least-privilege grants for `aahar_app` (ADR-0006, ADR-0009).

A session sees only rows whose organization_id equals the `app.org_id` setting, which the request middleware sets
per transaction (`app.core.db.org_scope`). With the setting absent, the app role sees nothing.

The table lists are frozen here on purpose: a migration must not change meaning when models change later.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"

ORG_SCOPED = (
    "alerts",
    "audit_chain_heads",
    "audit_log",
    "credit_note_lines",
    "credit_note_tax_lines",
    "credit_notes",
    "customers",
    "dispatch_lines",
    "dispatches",
    "export_jobs",
    "fill_weight_samples",
    "idempotency_keys",
    "inventory_balances",
    "invoice_lines",
    "invoice_tax_lines",
    "invoices",
    "item_cost_state",
    "items",
    "locations",
    "lots",
    "material_issue_lines",
    "material_issues",
    "memberships",
    "number_sequences",
    "oil_sessions",
    "order_lines",
    "order_status_history",
    "outbox_events",
    "pack_spec_lines",
    "pack_spec_versions",
    "pack_specs",
    "payment_allocations",
    "payments",
    "period_locks",
    "price_list_items",
    "price_lists",
    "production_runs",
    "purchase_receipt_lines",
    "purchase_receipts",
    "recipe_lines",
    "recipe_versions",
    "recipes",
    "reservations",
    "run_costs",
    "run_pack_lines",
    "sales_orders",
    "salesman_customer_assignments",
    "settings",
    "standard_cost_cards",
    "standard_cost_lines",
    "stock_journals",
    "stock_lines",
    "suppliers",
    "tax_rules",
    "transport_costs",
    "trip_stops",
    "trips",
    "uom_conversions",
    "valuation_layers",
    "variance_results",
    "vehicles",
)

# Global reference data: read-only for the app.
REFERENCE = ("uoms", "roles", "permissions", "role_permissions")

# Insert-only for the app (matches the immutability triggers in 0003).
INSERT_ONLY = (
    "stock_journals",
    "stock_lines",
    "audit_log",
    "invoice_lines",
    "invoice_tax_lines",
    "credit_notes",
    "credit_note_lines",
    "credit_note_tax_lines",
    "payments",
    "payment_allocations",
    "material_issues",
    "material_issue_lines",
    "run_costs",
    "order_status_history",
    "dispatch_lines",
)

# Maintained by the projection trigger only (ADR-0009): the app can read, never write.
READ_ONLY = ("inventory_balances",)

# Posted invoices: insert, and update only the cancellation columns (the trigger checks the transition).
INVOICE_UPDATABLE_COLUMNS = ("status", "cancelled_at", "cancel_reason")


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION aahar_current_org() RETURNS uuid
        LANGUAGE sql STABLE AS $$
          SELECT NULLIF(current_setting('app.org_id', true), '')::uuid
        $$
        """
    )

    for table in ORG_SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY org_isolation ON {table}"
            " USING (organization_id = aahar_current_org())"
            " WITH CHECK (organization_id = aahar_current_org())"
        )

    # A session sees and edits only its own organization row, but may create a new tenant
    # (a fresh BENCHMARK organization per replay, ADR-0006).
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_isolation ON organizations"
        " USING (id = aahar_current_org()) WITH CHECK (id = aahar_current_org())"
    )
    op.execute("CREATE POLICY org_create ON organizations FOR INSERT WITH CHECK (true)")

    op.execute(f"GRANT SELECT ON {', '.join(REFERENCE)} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON organizations, users TO {APP_ROLE}")
    for table in ORG_SCOPED:
        if table in READ_ONLY:
            op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
        elif table in INSERT_ONLY:
            op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}")
        elif table == "invoices":
            op.execute(f"GRANT SELECT, INSERT ON invoices TO {APP_ROLE}")
            op.execute(f"GRANT UPDATE ({', '.join(INVOICE_UPDATABLE_COLUMNS)}) ON invoices TO {APP_ROLE}")
        else:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    all_tables = (*ORG_SCOPED, "organizations", "users", *REFERENCE)
    op.execute(f"REVOKE ALL ON {', '.join(all_tables)} FROM {APP_ROLE}")
    op.execute("DROP POLICY IF EXISTS org_create ON organizations")
    op.execute("DROP POLICY IF EXISTS org_isolation ON organizations")
    op.execute("ALTER TABLE organizations DISABLE ROW LEVEL SECURITY")
    for table in ORG_SCOPED:
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS aahar_current_org()")
