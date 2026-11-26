"""MP12: per-item planning settings and draft purchase orders (ADR-0019, L3 and L5).

- item_planning: reorder level, safety stock, minimum order (base units) and lead time in days per item. Master
  data, changed through the planning service with an audit row.
- draft_purchase_orders (+ lines): what the planner suggests buying, approved by a person. A DRAFT records intent only:
  no stock and no money move; the delivery is a purchase receipt (MP05). Lines are insert-only; a draft is cancelled,
  never deleted.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "aahar_app"
QTY = sa.Numeric(18, 6)


def _scoped(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY org_isolation ON {table}"
        " USING (organization_id = aahar_current_org()) WITH CHECK (organization_id = aahar_current_org())"
    )


def _common() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("organization_id", sa.UUID(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "item_planning",
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("reorder_level_base", QTY, nullable=False, server_default="0"),
        sa.Column("safety_stock_base", QTY, nullable=False, server_default="0"),
        sa.Column("min_order_base", QTY, nullable=False, server_default="0"),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="0"),
        *_common(),
        sa.PrimaryKeyConstraint("organization_id", "item_id", name=op.f("pk_item_planning")),
        sa.ForeignKeyConstraint(
            ["item_id", "organization_id"],
            ["items.id", "items.organization_id"],
            name=op.f("fk_item_planning_item_id_organization_id_items"),
        ),
        sa.CheckConstraint(
            "reorder_level_base >= 0 AND safety_stock_base >= 0 AND min_order_base >= 0",
            name=op.f("ck_item_planning_not_negative"),
        ),
        sa.CheckConstraint("lead_time_days >= 0 AND lead_time_days <= 365", name=op.f("ck_item_planning_lead_time")),
    )
    op.create_table(
        "draft_purchase_orders",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("draft_no", sa.Text(), nullable=False),
        sa.Column("supplier_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="DRAFT"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        *_common(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draft_purchase_orders")),
        sa.UniqueConstraint(
            "organization_id", "draft_no", name=op.f("uq_draft_purchase_orders_organization_id_draft_no")
        ),
        sa.UniqueConstraint("id", "organization_id", name=op.f("uq_draft_purchase_orders_id_organization_id")),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name=op.f("fk_draft_purchase_orders_supplier_id_suppliers")
        ),
        sa.CheckConstraint("status IN ('DRAFT', 'CANCELLED')", name=op.f("ck_draft_purchase_orders_status")),
        sa.CheckConstraint(
            "status <> 'CANCELLED' OR (cancelled_at IS NOT NULL AND length(trim(coalesce(cancel_reason, ''))) > 0)",
            name=op.f("ck_draft_purchase_orders_cancel_reason"),
        ),
    )
    op.create_table(
        "draft_purchase_order_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("draft_id", sa.UUID(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("qty_base", QTY, nullable=False),
        sa.Column("needed_by", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        *_common(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draft_purchase_order_lines")),
        sa.UniqueConstraint("draft_id", "line_no", name=op.f("uq_draft_purchase_order_lines_draft_id_line_no")),
        sa.ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["draft_purchase_orders.id", "draft_purchase_orders.organization_id"],
            name=op.f("fk_draft_purchase_order_lines_draft_id_organization_id_draft_purchase_orders"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "organization_id"],
            ["items.id", "items.organization_id"],
            name=op.f("fk_draft_purchase_order_lines_item_id_organization_id_items"),
        ),
        sa.CheckConstraint("qty_base > 0", name=op.f("ck_draft_purchase_order_lines_qty_positive")),
    )
    for table in ("item_planning", "draft_purchase_orders", "draft_purchase_order_lines"):
        _scoped(table)
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON item_planning TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON draft_purchase_orders TO {APP_ROLE}")
    op.execute(f"GRANT UPDATE (status, cancelled_at, cancel_reason) ON draft_purchase_orders TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON draft_purchase_order_lines TO {APP_ROLE}")
    op.execute(
        "CREATE TRIGGER trg_draft_purchase_order_lines_immutable BEFORE UPDATE OR DELETE ON draft_purchase_order_lines"
        " FOR EACH ROW EXECUTE FUNCTION aahar_forbid_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_draft_purchase_order_lines_immutable ON draft_purchase_order_lines")
    for table in ("draft_purchase_order_lines", "draft_purchase_orders", "item_planning"):
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
        op.drop_table(table)
