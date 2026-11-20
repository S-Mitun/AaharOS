"""Identity tables: organizations (tenants), users, roles, permissions, memberships, salesman assignments."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.core.db import Base, OrgScoped, in_list, uuid_pk

ORG_KINDS = ("LIVE", "BENCHMARK", "SIM")
LANGUAGES = ("en", "ta")


class Organization(Base):
    """A tenant. Row-level security restricts each session to one organization (ADR-0006)."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(in_list("kind", ORG_KINDS), name="kind"),
        CheckConstraint("state_code ~ '^[0-9]{2}$'", name="state_code_format"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(in_list("language", LANGUAGES), name="language"),
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Role(Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Permission(Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    """Filled by MP03 (the permission matrix lives in code and docs/security.md)."""

    __tablename__ = "role_permissions"
    __table_args__ = (PrimaryKeyConstraint("role_code", "permission_code"),)

    role_code: Mapped[str] = mapped_column(Text, ForeignKey("roles.code"), nullable=False)
    permission_code: Mapped[str] = mapped_column(Text, ForeignKey("permissions.code"), nullable=False)


class Membership(OrgScoped, Base):
    __tablename__ = "memberships"
    __table_args__ = (PrimaryKeyConstraint("organization_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_code: Mapped[str] = mapped_column(Text, ForeignKey("roles.code"), nullable=False)


class SalesmanCustomerAssignment(OrgScoped, Base):
    """A salesman sees only assigned customers (MP03 row filter)."""

    __tablename__ = "salesman_customer_assignments"
    __table_args__ = (PrimaryKeyConstraint("organization_id", "user_id", "customer_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    route_order: Mapped[int | None] = mapped_column(Integer)
