"""Turn PostgreSQL guard failures into clear DomainErrors (ADR-0009 SQLSTATEs AH001-AH005, plus standard ones).

The database is the last line of defence: the services check the same rules first, so a user normally sees the
service's message. When a guard fires anyway (a race, or a rule only the database knows), this keeps the message
readable and the HTTP status a 4xx instead of a 500.
"""

from sqlalchemy.exc import DBAPIError

from app.core.errors import ConflictError, DomainError

_GUARDS = {
    "AH001": ("journal_unbalanced", "the journal does not balance"),
    "AH002": ("immutable", "posted records are immutable: post a reversal or a credit note"),
    "AH003": ("period_locked", "the period is locked"),
    "AH004": ("allocation_refused", "the payment allocation is not allowed"),
    "AH005": ("value_only_not_allowed", "value-only lines are allowed only in cost true-ups and reversals"),
}

_CHECKS = {
    "ck_inventory_balances_store_not_negative": ("negative_stock", "this would take a store below zero"),
    "ck_inventory_balances_empty_store_has_no_value": (
        "store_value_mismatch",
        "this would leave value on an empty store position",
    ),
}

_UNIQUES = {
    "uq_stock_journals_reverses_journal_id": ("already_reversed", "this journal has already been reversed"),
    "uq_stock_journals_organization_id_idempotency_key": (
        "idempotency_key_reused",
        "this Idempotency-Key was already used",
    ),
}


def sqlstate(exc: BaseException) -> str | None:
    return getattr(getattr(exc, "orig", None), "sqlstate", None)


def _constraint(exc: BaseException) -> str | None:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None)


def _message(exc: BaseException) -> str:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return str(getattr(diag, "message_primary", None) or exc)


def domain_error_from_db(exc: DBAPIError) -> DomainError | None:
    """The DomainError a known database refusal means, or None if it is not one we recognise (then re-raise)."""
    state = sqlstate(exc)
    if state in _GUARDS:
        code, fallback = _GUARDS[state]
        return DomainError(code, _message(exc) or fallback, {"sqlstate": state})
    constraint = _constraint(exc)
    if state == "23514":
        code, message = _CHECKS.get(constraint or "", ("check_violation", "a database rule refused this change"))
        return DomainError(code, message, {"sqlstate": state, "constraint": constraint})
    if state == "23505":
        code, message = _UNIQUES.get(constraint or "", ("duplicate", "this record already exists"))
        error_type = ConflictError if code == "idempotency_key_reused" else DomainError
        return error_type(code, message, {"sqlstate": state, "constraint": constraint})
    if state == "23503":
        return DomainError("invalid_reference", "a referenced record does not exist here", {"constraint": constraint})
    if state == "42501":
        return DomainError("not_permitted", "the database refused this change for your organization")
    if state in ("40P01", "40001"):  # deadlock or serialization failure: nothing was written, so a retry is safe
        return ConflictError(
            "retry",
            "another change to the same stock happened at the same moment: please try again",
            {"sqlstate": state},
        )
    return None
