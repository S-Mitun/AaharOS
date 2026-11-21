"""RBAC on every route (MP03 gate): generated route x role tests, the auditor's 403 on every mutation,
and the permission matrix in the database equal to the one in code.
"""

import re
import uuid
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.main import create_app
from app.modules.identity.api import PUBLIC_ROUTES
from app.modules.identity.domain import (
    ALL_PERMISSIONS,
    MUTATING_PERMISSIONS,
    READ_PERMISSIONS,
    ROLE_PERMISSIONS,
    ROLES,
    can,
)
from app.modules.identity.service import require, require_login
from tests.db.conftest import Staff, login_client

# Public on purpose: health check and the read-only benchmark guide for first-time visitors (judge module).
OPEN_ROUTES = PUBLIC_ROUTES | {("GET", "/health"), ("GET", "/api/guide/expected"), ("GET", "/api/guide/scoreboard")}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LOGIN_ONLY = "<any logged-in role>"


def _guard(route: APIRoute) -> str | None:
    """The permission a route requires, LOGIN_ONLY, or None if it has no identity guard at all."""
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if isinstance(dep.call, require):
            return dep.call.permission
        if isinstance(dep.call, require_login):
            return LOGIN_ONLY
        stack.extend(dep.dependencies)
    return None


def _routes() -> list[tuple[str, str, str | None]]:
    out = []
    for route in create_app().routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                out.append((method, route.path, _guard(route)))
    return out


ROUTES = _routes()
GUARDED = [(m, p, g) for m, p, g in ROUTES if g is not None]


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_every_route_is_guarded_or_deliberately_public() -> None:
    unguarded = [(m, p) for m, p, g in ROUTES if g is None and (m, p) not in OPEN_ROUTES]
    assert unguarded == [], "add Depends(require('<perm>')) or list the route as public with a reason"
    stale = [r for r in OPEN_ROUTES if r not in {(m, p) for m, p, _ in ROUTES}]
    assert stale == []


def test_every_mutating_route_needs_a_mutating_permission() -> None:
    weak = [(m, p, g) for m, p, g in GUARDED if m in MUTATING_METHODS and g not in MUTATING_PERMISSIONS]
    assert weak == []


@pytest.fixture(scope="module")
def clients(api_app: Any, staff: Staff) -> dict[str, TestClient]:
    return {role: login_client(api_app, staff.emails[role]) for role in ROLES}


@pytest.mark.parametrize(("method", "path", "guard"), GUARDED, ids=[f"{m} {p}" for m, p, _ in GUARDED])
@pytest.mark.parametrize("role", ROLES)
def test_route_role_matrix(clients: dict[str, TestClient], method: str, path: str, guard: str, role: str) -> None:
    """Generated: every guarded route x every role. Allowed roles never get 401/403; others always get 403."""
    r = clients[role].request(method, _concrete(path), json={} if method in MUTATING_METHODS else None)
    allowed = guard == LOGIN_ONLY or can(role, guard)
    if allowed:
        assert r.status_code not in (401, 403), r.text
    else:
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "forbidden"


def test_auditor_gets_403_on_every_mutation(clients: dict[str, TestClient]) -> None:
    mutations = [(m, p) for m, p, g in GUARDED if m in MUTATING_METHODS]
    assert mutations, "there must be mutating routes to test"
    for method, path in mutations:
        r = clients["AUDITOR"].request(method, _concrete(path), json={})
        assert r.status_code == 403, f"{method} {path}: {r.status_code}"


def test_auditor_holds_read_permissions_only() -> None:
    assert ROLE_PERMISSIONS["AUDITOR"] <= READ_PERMISSIONS


def test_matrix_is_complete() -> None:
    assert set(ROLE_PERMISSIONS) == set(ROLES)
    assert ROLE_PERMISSIONS["OWNER"] == ALL_PERMISSIONS
    used = set().union(*ROLE_PERMISSIONS.values())
    assert used == ALL_PERMISSIONS
    assert not (READ_PERMISSIONS & MUTATING_PERMISSIONS)


def test_database_matrix_equals_code(owner_engine: Engine) -> None:
    """role_permissions (for auditors querying the DB) must match the matrix the API enforces."""
    with owner_engine.connect() as c:
        rows = c.execute(text("SELECT role_code, permission_code FROM role_permissions")).all()
        seeded = set(c.execute(text("SELECT code FROM permissions")).scalars())
    db: dict[str, set[str]] = {}
    for role, perm in rows:
        db.setdefault(role, set()).add(perm)
    assert db == {role: set(perms) for role, perms in ROLE_PERMISSIONS.items()}
    assert seeded == ALL_PERMISSIONS
