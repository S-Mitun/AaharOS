"""Audit use cases: `record()` appends one hash-chained row in the caller's transaction; `verify()` checks a chain.

Other modules call only this file (module rule in CLAUDE.md).
"""

import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.context import current_correlation_id
from app.modules.audit.domain import GENESIS_HASH, AuditRow, ChainVerdict, build_summary, compute_hash, verify_chain
from app.modules.audit.models import AuditChainHead, AuditLog


def record(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    note: str | None = None,
) -> AuditRow:
    """Append one audit row. Locks the organization's chain head, so concurrent writers queue instead of forking.

    Runs in the caller's transaction: if the mutation rolls back, its audit row rolls back with it.
    """
    session.execute(
        insert(AuditChainHead)
        .values(organization_id=organization_id, last_seq=0, last_hash=GENESIS_HASH)
        .on_conflict_do_nothing(index_elements=["organization_id"])
    )
    head = session.execute(
        select(AuditChainHead).where(AuditChainHead.organization_id == organization_id).with_for_update()
    ).scalar_one()

    row = AuditRow(
        organization_id=organization_id,
        seq=head.last_seq + 1,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=build_summary(before, after, note),
        correlation_id=current_correlation_id(),
        occurred_at=datetime.now(UTC),
        prev_hash=head.last_hash,
        hash=b"",
    )
    digest = compute_hash(row.prev_hash, row)
    session.add(
        AuditLog(
            organization_id=row.organization_id,
            seq=row.seq,
            actor_id=row.actor_id,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            summary=row.summary,
            correlation_id=row.correlation_id,
            occurred_at=row.occurred_at,
            prev_hash=row.prev_hash,
            hash=digest,
            created_by=actor_id,
        )
    )
    head.last_seq = row.seq
    head.last_hash = digest
    session.flush()
    return replace(row, hash=digest)


def verify(session: Session, organization_id: uuid.UUID) -> ChainVerdict:
    """Recompute one organization's chain from its rows (the session must be able to see them)."""
    head = session.execute(
        select(AuditChainHead).where(AuditChainHead.organization_id == organization_id)
    ).scalar_one_or_none()
    rows = session.execute(
        select(AuditLog).where(AuditLog.organization_id == organization_id).order_by(AuditLog.seq)
    ).scalars()
    return verify_chain(
        organization_id,
        (
            AuditRow(
                organization_id=r.organization_id,
                seq=r.seq,
                actor_id=r.actor_id,
                action=r.action,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                summary=r.summary,
                correlation_id=r.correlation_id,
                occurred_at=r.occurred_at,
                prev_hash=r.prev_hash,
                hash=r.hash,
            )
            for r in rows
        ),
        None if head is None else head.last_seq,
        None if head is None else head.last_hash,
    )


def organizations_with_audit(session: Session) -> list[uuid.UUID]:
    """Every organization that has audit rows or a chain head (used by `make integrity`, as the owner)."""
    heads = set(session.execute(select(AuditChainHead.organization_id)).scalars())
    logged = set(session.execute(select(AuditLog.organization_id).distinct()).scalars())
    return sorted(heads | logged)


def recent(session: Session, organization_id: uuid.UUID, limit: int = 100) -> list[AuditLog]:
    return list(
        session.execute(
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.seq.desc())
            .limit(limit)
        ).scalars()
    )
