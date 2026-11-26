"""Identity use cases: login, refresh, logout, the per-request principal, `require(perm)`, and member management.

Other modules use `require`, `require_login` and `Principal` from here (module rule in CLAUDE.md).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Select, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session, org_scope
from app.core.errors import AuthenticationError, ConflictError, DomainError, PermissionDeniedError, RateLimitedError
from app.modules.audit import service as audit
from app.modules.identity.domain import (
    ACCESS_COOKIE,
    ALL_PERMISSIONS,
    OWN_ROWS_ROLES,
    ROLE_PERMISSIONS,
    ROLES,
    AccessClaims,
    RefreshParts,
    TokenError,
    can,
    hash_password,
    issue_access_token,
    needs_rehash,
    new_refresh_secret,
    parse_refresh_cookie,
    read_access_token,
    refresh_cookie_value,
    token_hash,
    verify_password,
)
from app.modules.identity.models import (
    AuthSession,
    LoginAttempt,
    Membership,
    Organization,
    RefreshToken,
    SalesmanCustomerAssignment,
    User,
)

MIN_PASSWORD_LENGTH = 10


@dataclass(frozen=True)
class Principal:
    """Who is calling, in which organization, with which role. Built from the DB on every request."""

    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    session_id: uuid.UUID

    @property
    def permissions(self) -> frozenset[str]:
        return ROLE_PERMISSIONS.get(self.role, frozenset())

    @property
    def sees_only_own_rows(self) -> bool:
        """True for a salesman: assigned customers and own orders only."""
        return self.role in OWN_ROWS_ROLES


@dataclass(frozen=True)
class IssuedTokens:
    principal: Principal
    access_token: str
    refresh_cookie: str


def _now() -> datetime:
    return datetime.now(UTC)


def _invalid_credentials() -> AuthenticationError:
    return AuthenticationError("invalid_credentials", "email or password is wrong")


def _not_authenticated(reason: str = "please log in") -> AuthenticationError:
    return AuthenticationError("not_authenticated", reason)


# ---------- login ----------


def _check_rate_limit(session: Session, email_lower: str, ip: str | None) -> None:
    settings = get_settings()
    since = _now() - timedelta(minutes=settings.login_window_minutes)
    by_email = session.execute(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.email_lower == email_lower, ~LoginAttempt.succeeded, LoginAttempt.attempted_at >= since)
    ).scalar_one()
    by_ip = 0
    if ip:
        by_ip = session.execute(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.ip == ip, ~LoginAttempt.succeeded, LoginAttempt.attempted_at >= since)
        ).scalar_one()
    if by_email >= settings.login_max_failures or by_ip >= settings.login_max_failures_per_ip:
        raise RateLimitedError(
            "too_many_attempts",
            f"too many failed logins; try again in {settings.login_window_minutes} minutes",
        )


def _issue(session: Session, principal_user: uuid.UUID, org: uuid.UUID, auth_session_id: uuid.UUID) -> tuple[str, str]:
    settings = get_settings()
    secret = new_refresh_secret()
    session.add(
        RefreshToken(
            organization_id=org,
            session_id=auth_session_id,
            token_hash=token_hash(secret),
            expires_at=_now() + timedelta(days=settings.refresh_token_days),
            created_by=principal_user,
        )
    )
    access = issue_access_token(
        AccessClaims(principal_user, org, auth_session_id),
        settings.auth_secret,
        timedelta(minutes=settings.access_token_minutes),
    )
    return access, refresh_cookie_value(RefreshParts(org, auth_session_id, secret))


def login(
    session: Session,
    *,
    email: str,
    password: str,
    organization_code: str | None,
    ip: str | None,
    user_agent: str | None,
) -> IssuedTokens:
    email_lower = email.strip().lower()
    _check_rate_limit(session, email_lower, ip)

    # Runs before any organization is known, so it uses a narrow SECURITY DEFINER lookup (migration 0007).
    rows = session.execute(
        text(
            "SELECT user_id, password_hash, is_active, organization_id, organization_code, role_code,"
            " membership_active FROM aahar_login_lookup(:email)"
        ),
        {"email": email_lower},
    ).all()
    first = rows[0] if rows else None
    password_ok = verify_password(None if first is None else first.password_hash, password)  # always hashes
    memberships = [r for r in rows if r.organization_id is not None and r.membership_active]
    if organization_code:
        memberships = [r for r in memberships if r.organization_code == organization_code]

    if first is None or not password_ok or not first.is_active or not memberships:
        session.add(LoginAttempt(email_lower=email_lower, ip=ip, succeeded=False))
        session.commit()
        raise _invalid_credentials()
    if len(memberships) > 1:
        raise DomainError(
            "organization_required",
            "this login belongs to more than one organization; choose one",
            {"organizations": sorted(r.organization_code for r in memberships)},
        )

    chosen = memberships[0]
    user_id: uuid.UUID = chosen.user_id
    org_id: uuid.UUID = chosen.organization_id
    session.add(LoginAttempt(email_lower=email_lower, ip=ip, succeeded=True))
    org_scope(session, org_id, user_id)

    if needs_rehash(first.password_hash):
        session.execute(update(User).where(User.id == user_id).values(password_hash=hash_password(password)))

    auth_session = AuthSession(
        organization_id=org_id,
        user_id=user_id,
        expires_at=_now() + timedelta(days=get_settings().refresh_token_days),
        user_agent=(user_agent or "")[:300] or None,
        ip=ip,
        created_by=user_id,
    )
    session.add(auth_session)
    session.flush()
    access, refresh = _issue(session, user_id, org_id, auth_session.id)
    audit.record(
        session,
        organization_id=org_id,
        actor_id=user_id,
        action="auth.login",
        entity_type="auth_session",
        entity_id=auth_session.id,
        after={"role": chosen.role_code, "ip": ip},
    )
    session.commit()
    return IssuedTokens(Principal(user_id, org_id, chosen.role_code, auth_session.id), access, refresh)


# ---------- per-request authentication ----------


def _load_principal(session: Session, claims: AccessClaims) -> Principal:
    org_scope(session, claims.organization_id, claims.user_id)
    row = session.execute(
        select(
            AuthSession.revoked_at, AuthSession.expires_at, Membership.role_code, Membership.is_active, User.is_active
        )
        .join(
            Membership,
            (Membership.organization_id == AuthSession.organization_id) & (Membership.user_id == AuthSession.user_id),
        )
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.id == claims.session_id, AuthSession.user_id == claims.user_id)
    ).one_or_none()
    if row is None:
        raise _not_authenticated("your session is not valid; please log in again")
    revoked_at, expires_at, role, membership_active, user_active = row
    if revoked_at is not None or expires_at <= _now():
        raise _not_authenticated("your session has ended; please log in again")
    if not (membership_active and user_active):
        raise _not_authenticated("your account is no longer active")
    return Principal(claims.user_id, claims.organization_id, role, claims.session_id)


def authenticate(request: Request, session: Session) -> Principal:
    """Read the access cookie, check its session in the DB, and scope the DB session to the caller's org."""
    cached = getattr(request.state, "principal", None)
    if isinstance(cached, Principal):
        return cached
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise _not_authenticated()
    try:
        claims = read_access_token(token, get_settings().auth_secret)
    except TokenError as exc:
        raise _not_authenticated("your login has expired or is not valid") from exc
    principal = _load_principal(session, claims)
    request.state.principal = principal
    return principal


class require:
    """FastAPI dependency: the caller must be logged in and their role must hold `permission`."""

    def __init__(self, permission: str) -> None:
        if permission not in ALL_PERMISSIONS:
            raise ValueError(f"unknown permission {permission!r}")
        self.permission = permission

    def __call__(self, request: Request, session: Annotated[Session, Depends(get_session)]) -> Principal:
        principal = authenticate(request, session)
        if not can(principal.role, self.permission):
            raise PermissionDeniedError(
                "forbidden",
                f"the {principal.role} role may not do this",
                {"permission": self.permission, "role": principal.role},
            )
        return principal


class require_login:
    """FastAPI dependency for routes every logged-in role may use (e.g. "who am I")."""

    def __call__(self, request: Request, session: Annotated[Session, Depends(get_session)]) -> Principal:
        return authenticate(request, session)


# ---------- refresh and logout ----------


def refresh(session: Session, cookie_value: str | None) -> IssuedTokens:
    if not cookie_value:
        raise _not_authenticated()
    try:
        parts = parse_refresh_cookie(cookie_value)
    except TokenError as exc:
        raise _not_authenticated() from exc
    org_scope(session, parts.organization_id)
    token = session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash(parts.secret)).with_for_update()
    ).scalar_one_or_none()
    if token is None or token.session_id != parts.session_id:
        raise _not_authenticated("your login has expired; please log in again")
    auth_session = session.execute(
        select(AuthSession).where(AuthSession.id == token.session_id).with_for_update()
    ).scalar_one()
    now = _now()
    if auth_session.revoked_at is not None or auth_session.expires_at <= now or token.expires_at <= now:
        raise _not_authenticated("your session has ended; please log in again")
    if token.used_at is not None:
        # A spent token came back: someone copied it. End the whole session (ADR-0010).
        auth_session.revoked_at = now
        auth_session.revoke_reason = "refresh_token_reused"
        audit.record(
            session,
            organization_id=auth_session.organization_id,
            actor_id=auth_session.user_id,
            action="auth.refresh_reused",
            entity_type="auth_session",
            entity_id=auth_session.id,
            note="a refresh token was used twice; the session was revoked",
        )
        session.commit()
        raise _not_authenticated("your session was ended for safety; please log in again")

    principal = _load_principal(
        session, AccessClaims(auth_session.user_id, auth_session.organization_id, auth_session.id)
    )
    token.used_at = now
    access, new_refresh = _issue(session, principal.user_id, principal.organization_id, auth_session.id)
    session.commit()
    return IssuedTokens(principal, access, new_refresh)


def _revoke(session: Session, auth_session_id: uuid.UUID, actor: uuid.UUID, org: uuid.UUID) -> None:
    changed = session.execute(
        update(AuthSession)
        .where(AuthSession.id == auth_session_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now(), revoke_reason="logout")
    ).rowcount
    if changed:
        audit.record(
            session,
            organization_id=org,
            actor_id=actor,
            action="auth.logout",
            entity_type="auth_session",
            entity_id=auth_session_id,
        )
    session.commit()


def logout(session: Session, request: Request) -> None:
    """End the caller's session, found from the access cookie, or from the refresh cookie if access expired."""
    try:
        principal = authenticate(request, session)
        _revoke(session, principal.session_id, principal.user_id, principal.organization_id)
        return
    except AuthenticationError:
        session.rollback()
    cookie = request.cookies.get("aahar_refresh")
    if not cookie:
        return
    try:
        parts = parse_refresh_cookie(cookie)
    except TokenError:
        return
    org_scope(session, parts.organization_id)
    token = session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash(parts.secret))
    ).scalar_one_or_none()
    if token is None or token.session_id != parts.session_id:
        return
    owner = session.execute(select(AuthSession.user_id).where(AuthSession.id == token.session_id)).scalar_one()
    _revoke(session, token.session_id, owner, parts.organization_id)


# ---------- row filters other modules apply ----------


def assigned_customer_ids(user_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
    """Customers assigned to a salesman, as a subquery for `Customer.id.in_(...)`."""
    return select(SalesmanCustomerAssignment.customer_id).where(SalesmanCustomerAssignment.user_id == user_id)


def route_order(session: Session, user_id: uuid.UUID) -> dict[uuid.UUID, int | None]:
    """A salesman's assigned customers and their place on the day's route (MP08 Today screen)."""
    rows = session.execute(
        select(SalesmanCustomerAssignment.customer_id, SalesmanCustomerAssignment.route_order).where(
            SalesmanCustomerAssignment.user_id == user_id
        )
    ).tuples()
    return dict(rows.all())


def is_assigned(session: Session, user_id: uuid.UUID, customer_id: uuid.UUID) -> bool:
    return (
        session.execute(
            select(SalesmanCustomerAssignment.customer_id).where(
                SalesmanCustomerAssignment.user_id == user_id, SalesmanCustomerAssignment.customer_id == customer_id
            )
        ).first()
        is not None
    )


def display_names(session: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    return dict(session.execute(select(User.id, User.display_name).where(User.id.in_(user_ids))).tuples().all())


# ---------- who am I, members ----------


def organization(session: Session, organization_id: uuid.UUID) -> dict[str, str]:
    """Name, code, kind and GST state code of an organization (MP10: the supplier on an invoice)."""
    org = session.execute(select(Organization).where(Organization.id == organization_id)).scalar_one()
    return {"id": str(org.id), "code": org.code, "name": org.name, "kind": org.kind, "state_code": org.state_code}


def describe(session: Session, principal: Principal) -> dict[str, object]:
    user = session.execute(select(User).where(User.id == principal.user_id)).scalar_one()
    org = session.execute(select(Organization).where(Organization.id == principal.organization_id)).scalar_one()
    return {
        "user": {"id": str(user.id), "email": user.email, "display_name": user.display_name, "language": user.language},
        "organization": {"id": str(org.id), "code": org.code, "name": org.name, "kind": org.kind},
        "role": principal.role,
        "permissions": sorted(principal.permissions),
    }


def create_member(
    session: Session, principal: Principal, *, email: str, display_name: str, role: str, password: str
) -> uuid.UUID:
    if role not in ROLES:
        raise DomainError("unknown_role", f"role must be one of {', '.join(ROLES)}")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise DomainError("weak_password", f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    user_id = uuid.uuid4()
    try:
        # Core INSERT without RETURNING: the new user becomes visible (RLS) only once the membership exists.
        session.execute(
            insert(User).values(
                id=user_id,
                email=email.strip(),
                display_name=display_name.strip(),
                password_hash=hash_password(password),
            )
        )
        session.execute(
            insert(Membership).values(
                organization_id=principal.organization_id, user_id=user_id, role_code=role, created_by=principal.user_id
            )
        )
    except IntegrityError as exc:
        session.rollback()
        raise DomainError("email_taken", "a user with this email already exists") from exc
    audit.record(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="user.create",
        entity_type="user",
        entity_id=user_id,
        after={"email": email.strip(), "display_name": display_name.strip(), "role": role},
    )
    session.commit()
    return user_id


def deactivate_member(session: Session, principal: Principal, user_id: uuid.UUID) -> None:
    """Remove a user's access to this organization and end their sessions here. Other organizations are untouched."""
    if user_id == principal.user_id:
        raise DomainError("cannot_deactivate_self", "you cannot deactivate your own account")
    membership = session.execute(
        select(Membership).where(Membership.user_id == user_id, Membership.organization_id == principal.organization_id)
    ).scalar_one_or_none()
    if membership is None:
        raise DomainError("not_a_member", "this user is not a member of your organization")
    if not membership.is_active:
        return
    membership.is_active = False
    session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now(), revoke_reason="deactivated")
    )
    audit.record(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="user.deactivate",
        entity_type="user",
        entity_id=user_id,
        before={"role": membership.role_code, "active": True},
        after={"role": membership.role_code, "active": False},
    )
    session.commit()


SCRATCH_ORG_KINDS = ("BENCHMARK", "SIM")


def create_scratch_tenant(
    session: Session, *, kind: str, label: str, state_code: str = "33", name: str | None = None
) -> uuid.UUID:
    """A fresh BENCHMARK or SIM organization, scoped onto this session (ADR-0006: a new tenant per replay, no
    deletes). LIVE organizations are seeded by the owner only; the database refuses them for the app role too."""
    if kind not in SCRATCH_ORG_KINDS:
        raise DomainError("not_a_scratch_tenant", f"only {' or '.join(SCRATCH_ORG_KINDS)} tenants are created here")
    org_id = uuid.uuid4()
    org_scope(session, org_id)
    session.execute(
        insert(Organization).values(
            id=org_id,
            code=f"{kind}-{label}-{org_id.hex[:8]}".upper(),
            name=name or f"DEMO {kind.lower()} {label}",
            kind=kind,
            state_code=state_code,
        )
    )
    audit.record(
        session,
        organization_id=org_id,
        actor_id=None,
        action="organization.create",
        entity_type="organization",
        entity_id=org_id,
        after={"kind": kind, "label": label},
    )
    return org_id


def create_first_owner(
    session: Session, *, organization_id: uuid.UUID, email: str, display_name: str, password: str
) -> uuid.UUID:
    """Self sign-up (deployment): the first OWNER of a fresh sandbox organization. The caller commits."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise DomainError("weak_password", f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    user_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                insert(User).values(
                    id=user_id,
                    email=email.strip(),
                    display_name=display_name.strip(),
                    password_hash=hash_password(password),
                )
            )
            session.execute(
                insert(Membership).values(organization_id=organization_id, user_id=user_id, role_code="OWNER")
            )
    except IntegrityError as exc:
        raise ConflictError("email_taken", "an account with this email already exists; sign in instead") from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=user_id,
        action="user.signup",
        entity_type="user",
        entity_id=user_id,
        after={"email": email.strip(), "display_name": display_name.strip(), "role": "OWNER"},
    )
    return user_id


def assign_customer(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    salesman_id: uuid.UUID,
    customer_id: uuid.UUID,
    route_order: int | None = None,
) -> None:
    """Give a salesman a customer (the MP03 row filter then shows it to them). Re-assigning is a no-op."""
    session.execute(
        pg_insert(SalesmanCustomerAssignment)
        .values(
            organization_id=organization_id,
            user_id=salesman_id,
            customer_id=customer_id,
            route_order=route_order,
            created_by=actor_id,
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "user_id", "customer_id"])
    )
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="salesman.assign",
        entity_type="customer",
        entity_id=customer_id,
        after={"salesman_id": salesman_id, "route_order": route_order},
    )
