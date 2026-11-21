"""Units in the database (MP04): the seeded system units equal the domain table; densities are per item."""

import uuid
from decimal import Decimal

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.modules.catalog import service as catalog
from app.modules.uom import service as uom
from app.modules.uom.domain import SYSTEM_UNITS, to_base
from tests.db.conftest import Tenant, scoped_session


def test_seeded_units_equal_the_domain_table(owner_engine: Engine) -> None:
    with Session(owner_engine) as s:
        assert uom.seeded_units(s) == SYSTEM_UNITS


def test_density_is_explicit_and_per_item(owner_engine: Engine, app_engine: Engine, tenant: Tenant) -> None:
    oil, flour = tenant.items["oil"], tenant.items["flour"]
    with owner_engine.begin() as c:  # 1 g of this oil is 1.098901 mL (DEMO figure)
        c.execute(
            text(
                "INSERT INTO uom_conversions (id, organization_id, from_uom, to_uom, factor, item_id)"
                " VALUES (:id, :o, 'g', 'mL', 1.098901, :i)"
            ),
            {"id": uuid.uuid4(), "o": tenant.org, "i": oil},
        )
    s = scoped_session(app_engine, tenant)
    units = catalog.units_for(s, [oil, flour])
    s.close()
    assert units[oil].density == Decimal("1.098901")
    assert units[flour].density is None
    assert to_base(Decimal("1"), "kg", units[oil]) == Decimal("1098.901")
