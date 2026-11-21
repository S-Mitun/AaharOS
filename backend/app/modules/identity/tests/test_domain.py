"""Pure tests of the identity rules: matrix, passwords, tokens (no database)."""

import uuid
from datetime import timedelta

import pytest

from app.modules.identity.domain import (
    ROLE_PERMISSIONS,
    AccessClaims,
    RefreshParts,
    TokenError,
    can,
    hash_password,
    issue_access_token,
    parse_refresh_cookie,
    read_access_token,
    refresh_cookie_value,
    verify_password,
)
from app.modules.identity.service import require

SECRET = "unit-test-secret-of-a-sensible-length-0123456789"  # noqa: S105


def test_benchmark_roles_can_do_their_steps() -> None:
    assert can("SALESMAN", "order.create")  # step 4 and 6
    assert can("ADMIN", "order.approve") and can("ADMIN", "invoice.post") and can("ADMIN", "dispatch.post")  # step 5
    assert can("ADMIN", "payment.post")  # step 7
    assert can("PRODUCTION", "receipt.post") and can("PRODUCTION", "run.start")  # steps 1-3
    assert can("PRODUCTION", "run.cost")  # step 8
    assert can("AUDITOR", "report.read")  # step 9
    assert not can("SALESMAN", "order.approve")
    assert not can("PRODUCTION", "invoice.post")
    assert not can("AUDITOR", "invoice.post")
    assert not can("ADMIN", "period.reopen")  # owner only
    assert not can("NOBODY", "order.read")


def test_unknown_permission_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="unknown permission"):
        require("order.teleport")


def test_password_round_trip() -> None:
    stored = hash_password("DEMO-correct-horse")
    assert stored.startswith("$argon2id$")
    assert verify_password(stored, "DEMO-correct-horse")
    assert not verify_password(stored, "DEMO-wrong-horse")
    assert not verify_password(None, "anything")  # unknown user
    assert not verify_password("not-a-hash", "anything")


def test_access_token_round_trip_and_rejections() -> None:
    claims = AccessClaims(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    token = issue_access_token(claims, SECRET, timedelta(minutes=15))
    assert read_access_token(token, SECRET) == claims
    with pytest.raises(TokenError):
        read_access_token(token, SECRET + "x")
    with pytest.raises(TokenError):
        read_access_token(issue_access_token(claims, SECRET, timedelta(seconds=-5)), SECRET)
    with pytest.raises(TokenError):
        read_access_token("garbage", SECRET)


def test_refresh_cookie_round_trip() -> None:
    parts = RefreshParts(uuid.uuid4(), uuid.uuid4(), "s3cr3t.with.dots")
    assert parse_refresh_cookie(refresh_cookie_value(parts)) == parts
    for bad in ("", "a.b", "not-a-uuid.also-not.secret", f"{uuid.uuid4()}.{uuid.uuid4()}."):
        with pytest.raises(TokenError):
            parse_refresh_cookie(bad)


def test_owner_has_every_permission() -> None:
    assert all(ROLE_PERMISSIONS["OWNER"] >= perms for perms in ROLE_PERMISSIONS.values())
