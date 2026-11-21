"""Effective-dated configuration (`settings`): tolerance %, thresholds, registration numbers (CLAUDE.md golden rule).

Values are stored as JSON **strings** for numbers ("3", not 3), so a float never enters a money or quantity path.
The table's EXCLUDE constraint keeps one value per key per day; `value_on` reads the one in force on a date.
"""

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import insert, or_, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.models import Setting


def value_on(session: Session, key: str, on: date) -> Any | None:
    """The value of `key` in force on `on` for the scoped organization, or None if none is configured."""
    return session.execute(
        select(Setting.value).where(
            Setting.key == key,
            Setting.effective_from <= on,
            or_(Setting.effective_to.is_(None), Setting.effective_to >= on),
        )
    ).scalar_one_or_none()


def decimal_on(session: Session, key: str, on: date) -> Decimal | None:
    raw = value_on(session, key, on)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise DomainError("setting_not_decimal_text", f"setting {key!r} must be stored as a decimal string")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise DomainError("setting_not_decimal_text", f"setting {key!r} is not a decimal: {raw!r}") from exc


def put(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    key: str,
    value: Any,
    effective_from: date,
    effective_to: date | None = None,
) -> uuid.UUID:
    """Insert one effective-dated value (the caller audits and commits). Overlapping ranges are refused by the DB."""
    if isinstance(value, float):
        raise DomainError("not_decimal", "store numbers as decimal strings, never floats")
    if isinstance(value, Decimal):
        value = str(value)
    setting_id = uuid.uuid4()
    session.execute(
        insert(Setting).values(
            id=setting_id,
            organization_id=organization_id,
            key=key,
            value=value,
            effective_from=effective_from,
            effective_to=effective_to,
            created_by=actor_id,
        )
    )
    return setting_id
