"""Database refusals become clear DomainErrors (app/core/pg_errors.py). Pure: the driver error is faked."""

from dataclasses import dataclass

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.errors import ConflictError
from app.core.pg_errors import domain_error_from_db


@dataclass
class _Diag:
    constraint_name: str | None = None
    message_primary: str | None = None


class _Orig(Exception):
    def __init__(self, sqlstate: str, constraint: str | None = None, message: str | None = None) -> None:
        super().__init__(message or sqlstate)
        self.sqlstate = sqlstate
        self.diag = _Diag(constraint, message)


def _err(sqlstate: str, constraint: str | None = None, message: str | None = None) -> DBAPIError:
    return DBAPIError("INSERT ...", {}, _Orig(sqlstate, constraint, message))


@pytest.mark.parametrize("state", ["40P01", "40001"])
def test_deadlock_and_serialization_failure_are_retryable_conflicts(state: str) -> None:
    err = domain_error_from_db(_err(state))
    assert isinstance(err, ConflictError)
    assert (err.code, err.status_code) == ("retry", 409)


def test_store_negative_check_is_named() -> None:
    err = domain_error_from_db(_err("23514", "ck_inventory_balances_store_not_negative"))
    assert err is not None and err.code == "negative_stock"


def test_guard_message_is_kept() -> None:
    err = domain_error_from_db(_err("AH003", message="period 2026-10 is locked: cannot post to stock_journals"))
    assert err is not None and err.code == "period_locked" and "2026-10" in err.message


def test_idempotency_unique_is_a_conflict_and_unknown_states_pass_through() -> None:
    err = domain_error_from_db(_err("23505", "uq_stock_journals_organization_id_idempotency_key"))
    assert isinstance(err, ConflictError)
    assert domain_error_from_db(_err("XX000")) is None
