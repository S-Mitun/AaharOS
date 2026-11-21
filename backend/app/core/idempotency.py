"""One client key, one effect (invariant D4), shared by every module that accepts an Idempotency-Key.

`claim()` inserts the key with a hash of what the request *means*. A concurrent duplicate waits on that row (INSERT
... ON CONFLICT DO NOTHING blocks until the first transaction ends), then sees it. Same key and same hash returns the
stored response; same key and a different hash is 409. `complete()` stores the response in the same transaction as
the effect, so a rolled-back effect also rolls back its key.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.models import IdempotencyKey


@dataclass(frozen=True)
class StoredResponse:
    status: int
    body: dict[str, Any]


def _canon(value: Any) -> Any:
    if isinstance(value, float):
        raise TypeError("floats cannot be part of an idempotent request; use Decimal")
    if isinstance(value, Decimal):
        return "0" if value == 0 else format(value.normalize(), "f")
    if isinstance(value, uuid.UUID | date):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_canon(v) for v in value]
    return value


def request_hash(doc: dict[str, Any]) -> bytes:
    """SHA-256 of a canonical JSON form: sorted keys, Decimals without trailing zeros (60.0 and 60 hash alike)."""
    return hashlib.sha256(json.dumps(_canon(doc), sort_keys=True, separators=(",", ":")).encode()).digest()


def claim(session: Session, organization_id: uuid.UUID, key: uuid.UUID, digest: bytes) -> StoredResponse | None:
    """None if this call now owns the key; the stored response if this exact request already succeeded."""
    claimed = session.execute(
        insert(IdempotencyKey)
        .values(organization_id=organization_id, key=key, request_hash=digest)
        .on_conflict_do_nothing(index_elements=["organization_id", "key"])
        .returning(IdempotencyKey.key)
    ).scalar_one_or_none()
    if claimed is not None:
        return None
    row = session.execute(
        select(IdempotencyKey).where(IdempotencyKey.organization_id == organization_id, IdempotencyKey.key == key)
    ).scalar_one()
    if bytes(row.request_hash) != digest:
        raise ConflictError(
            "idempotency_key_reused",
            "this Idempotency-Key was already used for a different request",
            {"idempotency_key": str(key)},
        )
    if row.response_status is None or not isinstance(row.response_body, dict):
        raise ConflictError(
            "idempotency_key_in_flight", "this request is still being processed", {"idempotency_key": str(key)}
        )
    return StoredResponse(row.response_status, row.response_body)


def complete(session: Session, organization_id: uuid.UUID, key: uuid.UUID, status: int, body: dict[str, Any]) -> None:
    session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.organization_id == organization_id, IdempotencyKey.key == key)
        .values(response_status=status, response_body=_canon(body))
    )
