"""User, Role, Permission models.

`User`, `Role` and `UserRole` are mapped to the live `users`, `roles` and `user_roles` tables
(SPEC-BE-036). Enum columns (`users.status` -> user_status, `roles.type` -> role_type) are
mapped as plain strings; `users.email` is citext, so equality lookups are case-insensitive in
the database itself.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TenantScopedModel

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class User(Base, TenantScopedModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # SPEC-BE-113 "my profile": phone and a profile photo (a data URL, <= 1 MB).
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Live user_status enum: active, invited, disabled, locked. Only 'active' may authenticate.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="invited")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Per-account wrong-password lockout (SPEC-BE-039).
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")

    # Not a column: the app-level RBAC role (core/permissions.Role value). `users` has no role
    # column; dependencies.get_current_user resolves it per request from user_roles -> roles
    # (auth_service.resolve_app_role) and sets it on the instance. Defaults to least privilege.
    role = "viewer"


class Role(Base):
    """A live `roles` row. `tenant_id` is NULL for a system role shared by all tenants."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Live role_type enum: owner, manager, operator, analyst, viewer, custom.
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UserRole(Base):
    """A live `user_roles` row assigning a role to a user within one tenant."""

    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)


class Permission(Base):
    """Static catalog of permission strings (e.g. 'products.write')."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")


class RolePermission(Base):
    """Association between a role name and a permission code."""

    __tablename__ = "role_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    permission_code: Mapped[str] = mapped_column(
        String(100), ForeignKey("permissions.code"), nullable=False
    )
