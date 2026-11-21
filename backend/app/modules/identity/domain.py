"""Pure identity rules: the role -> permission matrix, password hashing, access and refresh tokens. No DB.

The matrix here is the source of truth (docs/security.md is its readable copy). Migration 0007 seeds the same
matrix into `role_permissions` for auditors who query the database; a test keeps the two identical.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ROLES: Final = ("SALESMAN", "ADMIN", "PRODUCTION", "AUDITOR", "OWNER")

# Read-only permissions. Everything else mutates something, and the AUDITOR may hold read-only permissions only.
READ_PERMISSIONS: Final = frozenset(
    {"customer.read", "order.read", "stock.read", "report.read", "audit.read"},
)

MUTATING_PERMISSIONS: Final = frozenset(
    {
        "customer.manage",
        "order.create",
        "order.approve",
        "order.amend",
        "price.manage",
        "invoice.post",
        "invoice.cancel",
        "credit_note.post",
        "dispatch.post",
        "payment.post",
        "receipt.post",
        "stock.adjust",
        "stock.adjust.approve",
        "recipe.manage",
        "run.start",
        "run.complete",
        "run.cost",
        "run.reverse",
        "settings.manage",
        "period.lock",
        "period.reopen",
        "user.manage",
        "benchmark.run",
    }
)

ALL_PERMISSIONS: Final = READ_PERMISSIONS | MUTATING_PERMISSIONS

ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    # Field sales: own customers and orders only (row filter in the sales service), plus the "available today" hint.
    "SALESMAN": frozenset({"customer.read", "order.read", "order.create", "stock.read"}),
    # Billing desk: orders to invoices, dispatch, payments, price lists, tax settings, month close.
    "ADMIN": frozenset(
        {
            "customer.read",
            "customer.manage",
            "order.read",
            "order.approve",
            "order.amend",
            "price.manage",
            "invoice.post",
            "invoice.cancel",
            "credit_note.post",
            "dispatch.post",
            "payment.post",
            "stock.read",
            "stock.adjust",
            "run.cost",
            "run.reverse",
            "settings.manage",
            "period.lock",
            "report.read",
            "benchmark.run",
        }
    ),
    # Floor: receipts, recipes, runs and their costs, count differences.
    "PRODUCTION": frozenset(
        {
            "stock.read",
            "receipt.post",
            "recipe.manage",
            "run.start",
            "run.complete",
            "run.cost",
            "stock.adjust",
            "report.read",
        }
    ),
    # Accountant / auditor: read-only, enforced by the API (every mutating route needs a mutating permission).
    "AUDITOR": frozenset({"customer.read", "order.read", "stock.read", "report.read", "audit.read"}),
    # Owner: everything, including approving adjustments, reopening a closed month and managing users.
    "OWNER": ALL_PERMISSIONS,
}


# Roles that see only their own rows: a salesman sees assigned customers and their own orders (row filter).
OWN_ROWS_ROLES: Final = frozenset({"SALESMAN"})


def can(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


# ---------- passwords (Argon2id, library defaults: RFC 9106 low-memory profile) ----------

_hasher = PasswordHasher()
# Verified against when the email is unknown, so a miss costs the same time as a wrong password.
_DUMMY_HASH: Final = _hasher.hash("not-a-real-password-" + secrets.token_hex(8))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# ---------- access tokens (HS256 JWT, short-lived; the session row is checked on every request) ----------

ACCESS_COOKIE: Final = "aahar_access"
REFRESH_COOKIE: Final = "aahar_refresh"
_ALGORITHM: Final = "HS256"


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    session_id: uuid.UUID


class TokenError(Exception):
    """The token is missing, malformed, tampered with or expired."""


def issue_access_token(claims: AccessClaims, secret: str, ttl: timedelta, now: datetime | None = None) -> str:
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(claims.user_id),
        "org": str(claims.organization_id),
        "sid": str(claims.session_id),
        "typ": "access",
        "iat": int(issued.timestamp()),
        "exp": int((issued + ttl).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def read_access_token(token: str, secret: str) -> AccessClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM], options={"require": ["exp", "sub", "sid"]})
        if payload.get("typ") != "access":
            raise TokenError("not an access token")
        return AccessClaims(uuid.UUID(payload["sub"]), uuid.UUID(payload["org"]), uuid.UUID(payload["sid"]))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise TokenError(str(exc)) from exc


# ---------- refresh tokens (opaque, stored only as a SHA-256 hash, rotated on every use) ----------


@dataclass(frozen=True)
class RefreshParts:
    organization_id: uuid.UUID
    session_id: uuid.UUID
    secret: str


def new_refresh_secret() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def refresh_cookie_value(parts: RefreshParts) -> str:
    """`<org>.<session>.<secret>`: the org lets the server scope RLS before it looks the token up."""
    return f"{parts.organization_id}.{parts.session_id}.{parts.secret}"


def parse_refresh_cookie(value: str) -> RefreshParts:
    try:
        org, sid, secret = value.split(".", 2)
        if not secret:
            raise ValueError("empty secret")
        return RefreshParts(uuid.UUID(org), uuid.UUID(sid), secret)
    except ValueError as exc:
        raise TokenError("malformed refresh token") from exc


def token_hash(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def same_hash(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)
