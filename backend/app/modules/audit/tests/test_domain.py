"""Pure tests of the audit hash chain (no database)."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.audit.domain import (
    GENESIS_HASH,
    REDACTED,
    AuditRow,
    build_summary,
    canonical_json,
    compute_hash,
    redact,
    verify_chain,
)

ORG = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
T0 = datetime(2026, 11, 21, 4, 30, tzinfo=UTC)


def chain(n: int) -> list[AuditRow]:
    rows: list[AuditRow] = []
    prev = GENESIS_HASH
    for i in range(1, n + 1):
        row = AuditRow(ORG, i, None, "test", "thing", None, {"i": i}, None, T0 + timedelta(seconds=i), prev, b"")
        row = replace(row, hash=compute_hash(prev, row))
        rows.append(row)
        prev = row.hash
    return rows


def test_valid_chain_verifies() -> None:
    rows = chain(4)
    verdict = verify_chain(ORG, rows, 4, rows[-1].hash)
    assert (verdict.ok, verdict.rows_checked) == (True, 4)


def test_empty_chain_verifies() -> None:
    assert verify_chain(ORG, [], None, None).ok


@pytest.mark.parametrize("bad", [1, 2, 4])
def test_any_edited_row_breaks_the_chain(bad: int) -> None:
    rows = chain(4)
    rows[bad - 1] = replace(rows[bad - 1], summary={"i": 999})
    verdict = verify_chain(ORG, rows, 4, rows[-1].hash)
    assert (verdict.ok, verdict.first_bad_seq) == (False, bad)


def test_reordered_rows_break_the_chain() -> None:
    rows = chain(3)
    verdict = verify_chain(ORG, [rows[0], rows[2], rows[1]], 3, rows[-1].hash)
    assert not verdict.ok and verdict.first_bad_seq == 2


def test_rewritten_tail_with_stale_head_is_caught() -> None:
    rows = chain(3)
    assert not verify_chain(ORG, rows[:2], 3, rows[-1].hash).ok


def test_timestamps_hash_the_same_in_any_timezone() -> None:
    row = chain(1)[0]
    ist = replace(row, occurred_at=row.occurred_at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")))
    assert canonical_json(row) == canonical_json(ist)


def test_secrets_are_redacted_at_any_depth() -> None:
    summary = build_summary(
        {"password": "x", "nested": {"refresh_token": "y", "ok": 1}},
        {"items": [{"api_secret": "z", "qty": Decimal("1.500")}]},
    )
    assert summary["before"] == {"password": REDACTED, "nested": {"refresh_token": REDACTED, "ok": 1}}
    assert summary["after"] == {"items": [{"api_secret": REDACTED, "qty": "1.500"}]}
    assert redact("plain") == "plain"


def test_floats_are_refused_in_summaries() -> None:
    with pytest.raises(TypeError):
        build_summary(None, {"amount": 7875.0})
