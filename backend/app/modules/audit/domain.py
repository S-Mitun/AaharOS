"""Pure hash-chain rules for the audit log (ADR-0007). No DB.

hash(n) = sha256(prev_hash(n) || canonical_json(row n)), prev_hash(1) = 32 zero bytes, and prev_hash(n) = hash(n-1).
Editing, inserting or deleting any row breaks verification at that seq; deleting the newest rows is caught by the
chain head, which records the last seq and hash.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final

GENESIS_HASH: Final = bytes(32)

# Keys whose values are never written to the audit log (CLAUDE.md: before/after summary, no secrets).
_SECRET_KEY = re.compile(r"pass(word)?|secret|token|hash|cookie|authorization|otp", re.IGNORECASE)
REDACTED: Final = "[redacted]"


def to_json_safe(value: Any) -> Any:
    """Normalise a summary so it round-trips through JSONB unchanged: Decimal, UUID and dates become strings."""
    if isinstance(value, float):
        raise TypeError("floats are not allowed in audit summaries; use Decimal")
    if isinstance(value, bool | int | str) or value is None:
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        items = [to_json_safe(v) for v in value]
        return sorted(items, key=str) if isinstance(value, set | frozenset) else items
    raise TypeError(f"cannot store {type(value).__name__} in an audit summary")


def redact(value: Any) -> Any:
    """Replace the value of any secret-looking key, at any depth."""
    if isinstance(value, Mapping):
        return {k: (REDACTED if _SECRET_KEY.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def build_summary(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None, note: str | None = None
) -> dict[str, Any]:
    summary: dict[str, Any] = {"before": redact(to_json_safe(before)), "after": redact(to_json_safe(after))}
    if note:
        summary["note"] = note
    return summary


@dataclass(frozen=True)
class AuditRow:
    organization_id: uuid.UUID
    seq: int
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    summary: Any
    correlation_id: uuid.UUID | None
    occurred_at: datetime
    prev_hash: bytes
    hash: bytes


def canonical_json(row: AuditRow) -> bytes:
    """The exact bytes that are hashed: sorted keys, no whitespace, UTF-8, timestamps in UTC to the microsecond."""
    doc = {
        "organization_id": str(row.organization_id),
        "seq": row.seq,
        "actor_id": None if row.actor_id is None else str(row.actor_id),
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": None if row.entity_id is None else str(row.entity_id),
        "summary": row.summary,
        "correlation_id": None if row.correlation_id is None else str(row.correlation_id),
        "occurred_at": row.occurred_at.astimezone(UTC).isoformat(timespec="microseconds"),
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_hash(prev_hash: bytes, row: AuditRow) -> bytes:
    return hashlib.sha256(prev_hash + canonical_json(row)).digest()


@dataclass(frozen=True)
class ChainVerdict:
    organization_id: uuid.UUID
    ok: bool
    rows_checked: int
    first_bad_seq: int | None = None
    reason: str | None = None


def verify_chain(
    organization_id: uuid.UUID,
    rows: Iterable[AuditRow],
    head_seq: int | None,
    head_hash: bytes | None,
) -> ChainVerdict:
    """Recompute every hash in seq order and compare the end of the chain with the chain head."""
    expected_seq = 1
    prev = GENESIS_HASH
    checked = 0
    for row in rows:
        if row.seq != expected_seq:
            return ChainVerdict(organization_id, False, checked, expected_seq, f"row {expected_seq} is missing")
        if row.prev_hash != prev:
            return ChainVerdict(organization_id, False, checked, row.seq, "prev_hash does not match the row before")
        if compute_hash(prev, row) != row.hash:
            return ChainVerdict(organization_id, False, checked, row.seq, "row content does not match its hash")
        prev = row.hash
        expected_seq += 1
        checked += 1
    last_seq = expected_seq - 1
    if (head_seq or 0) != last_seq or (last_seq > 0 and head_hash != prev):
        return ChainVerdict(
            organization_id, False, checked, last_seq + 1, f"chain head says {head_seq or 0} rows, found {last_seq}"
        )
    return ChainVerdict(organization_id, True, checked)
