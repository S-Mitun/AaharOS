"""Identity routes: login, refresh, logout, who-am-I, and member management.

Tokens travel only in httpOnly cookies: the access cookie (15 min, path /api, SameSite=Lax) and the refresh cookie
(7 days, path /api/auth, SameSite=Strict). JavaScript can never read either (ADR-0010).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.modules.identity import service
from app.modules.identity.domain import ACCESS_COOKIE, REFRESH_COOKIE
from app.modules.identity.schemas import CreatedResponse, CreateMemberRequest, LoginRequest
from app.modules.identity.service import IssuedTokens, Principal, require, require_login

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
identity_router = APIRouter(prefix="/api/identity", tags=["identity"])

DbSession = Annotated[Session, Depends(get_session)]

# Routes that work without a logged-in role. Every other route must depend on `require(...)` or `require_login()`;
# tests/db/test_rbac.py fails if a new route forgets.
PUBLIC_ROUTES = frozenset(
    {
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/refresh"),
        ("POST", "/api/auth/logout"),
    }
)


def _set_auth_cookies(response: Response, tokens: IssuedTokens) -> None:
    settings = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        max_age=settings.access_token_minutes * 60,
        path="/api",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_cookie,
        max_age=settings.refresh_token_days * 24 * 3600,
        path="/api/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/api")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


@auth_router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, session: DbSession) -> dict[str, Any]:
    tokens = service.login(
        session,
        email=body.email,
        password=body.password,
        organization_code=body.organization_code,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, tokens)
    return service.describe(session, tokens.principal)


@auth_router.post("/refresh")
def refresh(request: Request, response: Response, session: DbSession) -> dict[str, Any]:
    tokens = service.refresh(session, request.cookies.get(REFRESH_COOKIE))
    _set_auth_cookies(response, tokens)
    return service.describe(session, tokens.principal)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, session: DbSession) -> Response:
    service.logout(session, request)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response


@auth_router.get("/me")
def me(principal: Annotated[Principal, Depends(require_login())], session: DbSession) -> dict[str, Any]:
    return service.describe(session, principal)


@identity_router.post("/users", status_code=status.HTTP_201_CREATED)
def create_member(
    body: CreateMemberRequest,
    principal: Annotated[Principal, Depends(require("user.manage"))],
    session: DbSession,
) -> CreatedResponse:
    user_id = service.create_member(
        session, principal, email=body.email, display_name=body.display_name, role=body.role, password=body.password
    )
    return CreatedResponse(id=str(user_id))


@identity_router.post("/users/{user_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_member(
    user_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require("user.manage"))],
    session: DbSession,
) -> Response:
    service.deactivate_member(session, principal, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
