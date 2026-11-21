"""Read-only stock routes (MP04): balances and the stock ledger. Every role with `stock.read` may call them.

A salesman holds `stock.read` for the "available today" hint only, so a salesman gets quantities without any
rupee value: stock values are cost, and cost is margin data (docs/security.md).

Posting has no route yet: receipts (MP05), runs (MP06) and dispatches (MP10) post through ledger.service from their
own use cases, so no endpoint can move stock without its source document.
"""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require
from app.modules.ledger import service

router = APIRouter(prefix="/api/stock", tags=["stock"])

VALUE_KEYS = frozenset({"value"})


def _for(principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    """Drop every rupee value for roles that see only their own rows (the salesman)."""
    return payload if not principal.sees_only_own_rows else _strip_values(payload)


def _strip_values(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_values(v) for k, v in node.items() if k not in VALUE_KEYS}
    if isinstance(node, list):
        return [_strip_values(v) for v in node]
    return node


@router.get("/balances")
def balances(
    principal: Annotated[Principal, Depends(require("stock.read"))],
    session: Annotated[Session, Depends(get_session)],
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,
    include_virtual: bool = False,
    include_zero: bool = False,
) -> dict[str, Any]:
    """Current balances from the projection. Stores only, unless `include_virtual` (SUPPLIER, CUSTOMER, ...)."""
    return _for(
        principal,
        {
            "balances": service.balances(
                session,
                item_id=item_id,
                location_id=location_id,
                lot_id=lot_id,
                include_virtual=include_virtual,
                include_zero=include_zero,
            )
        },
    )


@router.get("/ledger")
def stock_ledger(
    principal: Annotated[Principal, Depends(require("stock.read"))],
    session: Annotated[Session, Depends(get_session)],
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> dict[str, Any]:
    """Stock movements with opening balance, running balance and the source document of every row."""
    return _for(
        principal,
        service.stock_ledger(
            session,
            item_id=item_id,
            location_id=location_id,
            lot_id=lot_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        ),
    )
