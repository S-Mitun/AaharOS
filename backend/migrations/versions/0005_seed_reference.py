"""Seed global reference data only: roles, permission codes and system units of measure.

The role → permission matrix is MP03's (it lives in code and docs/security.md). Business data (items, locations,
customers) is seeded per tenant by MP05's `make seed-benchmark`, never here.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = (
    ("SALESMAN", "Salesman"),
    ("ADMIN", "Admin"),
    ("PRODUCTION", "Production supervisor"),
    ("AUDITOR", "Auditor (read-only)"),
    ("OWNER", "Owner"),
)

PERMISSIONS = (
    ("customer.read", "See customers"),
    ("customer.manage", "Create and edit customers"),
    ("order.create", "Take a sales order"),
    ("order.read", "See sales orders"),
    ("order.approve", "Approve, reject or part-approve an order"),
    ("order.amend", "Amend price or quantity on an order (with reason)"),
    ("price.manage", "Publish a new price list version"),
    ("invoice.post", "Post a GST invoice"),
    ("invoice.cancel", "Cancel an invoice (with reason)"),
    ("credit_note.post", "Post a credit note"),
    ("dispatch.post", "Post a dispatch"),
    ("payment.post", "Record a payment and allocate it"),
    ("receipt.post", "Post a purchase receipt"),
    ("stock.read", "See stock and stock movements"),
    ("stock.adjust", "Post a stock count adjustment"),
    ("stock.adjust.approve", "Approve a stock count adjustment"),
    ("recipe.manage", "Create recipe and pack spec versions"),
    ("run.start", "Start a production run and issue material"),
    ("run.complete", "Record production output"),
    ("run.cost", "Enter run costs (labour, gas/power)"),
    ("run.reverse", "Reverse a production run"),
    ("settings.manage", "Change effective-dated settings and tax rules"),
    ("period.lock", "Close a month"),
    ("period.reopen", "Reopen a closed month (owner, with reason)"),
    ("report.read", "See reports and Explain this number"),
    ("audit.read", "See the audit log and verify the chain"),
    ("user.manage", "Manage users and roles"),
    ("benchmark.run", "Run the NIT benchmark replay"),
)

# (code, name, dimension, factor to the base unit, is base)
UOMS = (
    ("g", "gram", "MASS", "1", True),
    ("kg", "kilogram", "MASS", "1000", False),
    ("mL", "millilitre", "VOLUME", "1", True),
    ("L", "litre", "VOLUME", "1000", False),
    ("piece", "piece", "COUNT", "1", True),
    ("packet", "packet", "COUNT", "1", False),
)


def upgrade() -> None:
    roles = sa.table("roles", sa.column("code"), sa.column("name"))
    permissions = sa.table("permissions", sa.column("code"), sa.column("description"))
    uoms = sa.table(
        "uoms",
        sa.column("code"),
        sa.column("name"),
        sa.column("dimension"),
        sa.column("to_base", sa.Numeric(18, 6)),
        sa.column("is_base", sa.Boolean),
    )
    op.bulk_insert(roles, [{"code": c, "name": n} for c, n in ROLES])
    op.bulk_insert(permissions, [{"code": c, "description": d} for c, d in PERMISSIONS])
    op.execute(
        uoms.insert().values(
            [
                {"code": c, "name": n, "dimension": d, "to_base": sa.literal(f, sa.Numeric(18, 6)), "is_base": b}
                for c, n, d, f, b in UOMS
            ]
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM uoms WHERE code = ANY(:codes)").bindparams(codes=[u[0] for u in UOMS]))
    op.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(codes=[p[0] for p in PERMISSIONS])
    )
    op.execute(sa.text("DELETE FROM roles WHERE code = ANY(:codes)").bindparams(codes=[r[0] for r in ROLES]))
