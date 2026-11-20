"""Registry that imports every models.py so `Base.metadata` is complete (used by Alembic and tests).

It sits outside `app.modules`, like `main.py`, so it does not break the module layering contract.
"""

from app.core import models as core_models
from app.core.db import Base
from app.modules.audit import models as audit_models
from app.modules.billing import models as billing_models
from app.modules.catalog import models as catalog_models
from app.modules.collections import models as collections_models
from app.modules.costing import models as costing_models
from app.modules.dispatch import models as dispatch_models
from app.modules.identity import models as identity_models
from app.modules.ledger import models as ledger_models
from app.modules.planning import models as planning_models
from app.modules.procurement import models as procurement_models
from app.modules.production import models as production_models
from app.modules.recipe import models as recipe_models
from app.modules.reports import models as reports_models
from app.modules.sales import models as sales_models
from app.modules.tax import models as tax_models
from app.modules.transport import models as transport_models
from app.modules.uom import models as uom_models
from app.modules.valuation import models as valuation_models

MODEL_MODULES = (
    core_models,
    identity_models,
    audit_models,
    uom_models,
    catalog_models,
    ledger_models,
    recipe_models,
    valuation_models,
    procurement_models,
    production_models,
    sales_models,
    tax_models,
    costing_models,
    billing_models,
    dispatch_models,
    collections_models,
    transport_models,
    planning_models,
    reports_models,
)

metadata = Base.metadata
