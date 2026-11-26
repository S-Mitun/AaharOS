"""MP14: transport and cost-to-serve, kept light (ADR-0021).

- customers and suppliers get an optional location (latitude, longitude in degrees) for trip planning and backhaul.
- vehicles get their running costs: fuel use (L per 100 km), driver allowance and fixed cost per trip (rupees).
- trips get a number (TRP/{fy}/{n}, gapless), a status (PLANNED -> DONE) and the tolls paid; a stop's packets and
  its share of the trip cost are computed on read. A trip stop names one dispatch, once.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEG = sa.Numeric(9, 6)
MONEY = sa.Numeric(14, 2)


def _located(table: str) -> None:
    op.add_column(table, sa.Column("latitude", DEG, nullable=True))
    op.add_column(table, sa.Column("longitude", DEG, nullable=True))
    op.create_check_constraint(
        "location_valid",
        table,
        "(latitude IS NULL) = (longitude IS NULL)"
        " AND (latitude IS NULL OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))",
    )


def upgrade() -> None:
    _located("customers")
    _located("suppliers")
    op.add_column("vehicles", sa.Column("fuel_l_per_100km", sa.Numeric(8, 3), nullable=False, server_default="0"))
    op.add_column("vehicles", sa.Column("driver_allowance", MONEY, nullable=False, server_default="0"))
    op.add_column("vehicles", sa.Column("fixed_cost", MONEY, nullable=False, server_default="0"))
    op.create_check_constraint(
        "running_costs_not_negative", "vehicles", "fuel_l_per_100km >= 0 AND driver_allowance >= 0 AND fixed_cost >= 0"
    )
    op.add_column("trips", sa.Column("trip_no", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("status", sa.Text(), nullable=False, server_default="PLANNED"))
    op.add_column("trips", sa.Column("tolls", MONEY, nullable=False, server_default="0"))
    op.create_check_constraint("status", "trips", "status IN ('PLANNED', 'DONE')")
    op.create_check_constraint("tolls_not_negative", "trips", "tolls >= 0")
    op.create_check_constraint("done_has_actual_km", "trips", "status <> 'DONE' OR actual_km IS NOT NULL")
    op.create_unique_constraint("uq_trips_organization_id_trip_no", "trips", ["organization_id", "trip_no"])
    op.create_unique_constraint("uq_trip_stops_dispatch_id", "trip_stops", ["dispatch_id"])


def downgrade() -> None:
    op.drop_constraint("uq_trip_stops_dispatch_id", "trip_stops", type_="unique")
    op.drop_constraint("uq_trips_organization_id_trip_no", "trips", type_="unique")
    for name in ("done_has_actual_km", "tolls_not_negative", "status"):
        op.drop_constraint(name, "trips", type_="check")
    for col in ("tolls", "status", "trip_no"):
        op.drop_column("trips", col)
    op.drop_constraint("running_costs_not_negative", "vehicles", type_="check")
    for col in ("fixed_cost", "driver_allowance", "fuel_l_per_100km"):
        op.drop_column("vehicles", col)
    for table in ("suppliers", "customers"):
        op.drop_constraint("location_valid", table, type_="check")
        op.drop_column(table, "longitude")
        op.drop_column(table, "latitude")
