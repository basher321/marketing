"""User management and role assignment (SPEC-BE-037).

Users live in the live `users` table; a user's role is not a column but `user_roles` ->
`roles.type` (live role_type enum) within the user's own tenant. Deletes are soft
(`deleted_at` + status 'disabled'). Every mutation writes one audit_log row via
core/audit.write_audit_log(), which commits the session, so it is always the last write.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.user import Role, User, UserRole
from app.schemas.user import UserCreate, UserUpdate

logger = structlog.get_logger(__name__)

# Precedence among live role_type values when a user holds several roles: the highest wins.
# Consistent with auth_service.ROLE_TYPE_TO_APP_ROLE (owner > manager > operator > the
# viewer-level types); `custom` ranks lowest because it resolves to viewer.
ROLE_TYPE_RANK: dict[str, int] = {
    "owner": 5,
    "manager": 4,
    "operator": 3,
    "analyst": 2,
    "viewer": 1,
    "custom": 0,
}
DEFAULT_ROLE_TYPE = "viewer"

USER_NOT_FOUND = "User not found."
EMAIL_TAKEN = "A user with this email already exists."
LAST_OWNER = "A tenant must keep at least one active owner."
USERS_EMAIL_UNIQUE = "users_tenant_email_unique"


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value is not None else None


def _to_read(user: User, role: str) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": role,
        "status": user.status,
        "last_login_at": _utc(user.last_login_at),
        "created_at": _utc(user.created_at),
    }


def _role_types_by_user(db: Session, tenant_id: str, user_ids: list[str]) -> dict[str, list[str]]:
    # Same tenant rule as auth_service.resolve_app_role: only assignments made in this tenant,
    # to a role of this tenant or a system role (roles.tenant_id NULL), ever count.
    if not user_ids:
        return {}
    rows = db.execute(
        select(UserRole.user_id, Role.type)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id.in_(user_ids),
            UserRole.tenant_id == tenant_id,
            or_(Role.tenant_id.is_(None), Role.tenant_id == tenant_id),
        )
    ).all()
    result: dict[str, list[str]] = {}
    for user_id, role_type in rows:
        result.setdefault(str(user_id), []).append(role_type)
    return result


def _highest_role_type(role_types: list[str]) -> str:
    return max(role_types, key=lambda t: ROLE_TYPE_RANK.get(t, 0), default=DEFAULT_ROLE_TYPE)


def _role_of(db: Session, tenant_id: str, user_id: str) -> str:
    return _highest_role_type(_role_types_by_user(db, tenant_id, [user_id]).get(user_id, []))


def _get_user_row(db: Session, tenant_id: str, user_id: str) -> User:
    # A malformed id can't match the native uuid column; answer 404 rather than letting
    # Postgres raise. Another tenant's user is also 404 (existence isn't leaked).
    try:
        uuid.UUID(user_id)
    except ValueError as exc:
        raise NotFoundError(USER_NOT_FOUND) from exc
    user = db.scalars(
        select(User).where(
            User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None)
        )
    ).first()
    if user is None:
        raise NotFoundError(USER_NOT_FOUND)
    return user


def _active_owner_ids(db: Session, tenant_id: str) -> set[str]:
    """Active, non-deleted users holding an owner role in this tenant.

    The user rows are locked (FOR UPDATE) so two owners demoting each other concurrently can't
    both pass the last-owner guard.
    """
    rows = db.scalars(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
            User.status == "active",
            UserRole.tenant_id == tenant_id,
            or_(Role.tenant_id.is_(None), Role.tenant_id == tenant_id),
            Role.type == "owner",
        )
        .with_for_update(of=User)
    ).all()
    return {str(r) for r in rows}


def _guard_last_owner(db: Session, tenant_id: str, user_id: str) -> None:
    owners = _active_owner_ids(db, tenant_id)
    if owners == {user_id}:
        raise ConflictError(LAST_OWNER)


def assign_role(db: Session, tenant_id: str, user_id: str, role_type: str) -> None:
    """Make `role_type` the user's only role in this tenant (flush only; caller commits).

    Reuses the tenant's own `roles` row of that type, or creates one named after the type
    (e.g. 'Owner') - per-tenant roles, SPEC-BE-037 open decision 4. `user_roles.assigned_by`
    is left NULL: the UserRole model doesn't map it (the actor is in the audit row instead).
    """
    role = db.scalars(
        select(Role).where(Role.tenant_id == tenant_id, Role.type == role_type).order_by(Role.name)
    ).first()
    if role is None:
        # The Role model has no Python-side id default; generate it like every other model.
        role = Role(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=role_type.capitalize(),
            type=role_type,
            is_system=False,
        )
        db.add(role)
        db.flush()
    db.execute(
        delete(UserRole).where(UserRole.user_id == user_id, UserRole.tenant_id == tenant_id)
    )
    db.add(UserRole(user_id=user_id, role_id=role.id, tenant_id=tenant_id))
    db.flush()


def list_users(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    users = db.scalars(
        select(User)
        .where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
        .order_by(User.created_at)
    ).all()
    roles = _role_types_by_user(db, tenant_id, [str(u.id) for u in users])
    return [_to_read(u, _highest_role_type(roles.get(str(u.id), []))) for u in users]


def get_user(db: Session, tenant_id: str, user_id: str) -> dict[str, Any]:
    user = _get_user_row(db, tenant_id, user_id)
    return _to_read(user, _role_of(db, tenant_id, str(user.id)))


def create_user(
    db: Session, tenant_id: str, actor_user_id: str, payload: UserCreate
) -> dict[str, Any]:
    # users.email is citext and UNIQUE (tenant_id, email) also covers soft-deleted users, so
    # this check is case-insensitive and includes them; a race is caught at flush below.
    existing = db.scalars(
        select(User.id).where(User.tenant_id == tenant_id, User.email == payload.email)
    ).first()
    if existing is not None:
        raise ConflictError(EMAIL_TAKEN)

    # No invite flow exists, so owner-created users are active at once (open decision 3).
    user = User(
        tenant_id=tenant_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        status="active",
        email_verified=False,
    )
    try:
        db.add(user)
        db.flush()
        assign_role(db, tenant_id, str(user.id), payload.role)
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == USERS_EMAIL_UNIQUE:
            raise ConflictError(EMAIL_TAKEN) from exc
        raise

    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user.created",
        resource_type="user",
        resource_id=str(user.id),
        metadata={"role": payload.role},
    )
    logger.info("user.created", tenant_id=tenant_id, user_id=str(user.id), role=payload.role)
    return _to_read(user, payload.role)


def update_user(
    db: Session, tenant_id: str, actor_user_id: str, user_id: str, payload: UserUpdate
) -> dict[str, Any]:
    user = _get_user_row(db, tenant_id, user_id)
    uid = str(user.id)
    current_role = _role_of(db, tenant_id, uid)
    changes = payload.model_dump(exclude_unset=True)

    changed: list[str] = []
    for field in ("first_name", "last_name"):
        if field in changes and changes[field] != getattr(user, field):
            setattr(user, field, changes[field])
            changed.append(field)
    # None means "no change": omitted, an explicit null (role/status are not nullable), or the
    # value the user already has.
    new_role: str | None = changes.get("role")
    if new_role == current_role:
        new_role = None
    new_status: str | None = changes.get("status")
    if new_status == user.status:
        new_status = None

    if (new_role is not None and current_role == "owner") or (
        new_status is not None and new_status != "active"
    ):
        _guard_last_owner(db, tenant_id, uid)

    if new_role is not None:
        assign_role(db, tenant_id, uid, new_role)
        changed.append("role")
    if new_status is not None:
        # A disabled user's existing tokens fail on the next request: get_current_user only
        # loads status 'active' users (SPEC-BE-036).
        user.status = new_status
        changed.append("status")

    if not changed:
        return _to_read(user, current_role)

    db.flush()
    metadata: dict[str, Any] = {"fields": changed}
    if new_role is not None:
        metadata["role"] = new_role
    if new_status is not None:
        metadata["status"] = new_status
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user.updated",
        resource_type="user",
        resource_id=uid,
        metadata=metadata,
    )
    logger.info("user.updated", tenant_id=tenant_id, user_id=uid, fields=changed)
    return _to_read(user, new_role or current_role)


def delete_user(db: Session, tenant_id: str, actor_user_id: str, user_id: str) -> None:
    user = _get_user_row(db, tenant_id, user_id)
    uid = str(user.id)
    _guard_last_owner(db, tenant_id, uid)

    # Soft delete: the row and its role assignments stay for audit history.
    user.deleted_at = datetime.now(timezone.utc)
    user.status = "disabled"
    db.flush()
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user.deleted",
        resource_type="user",
        resource_id=uid,
    )
    logger.info("user.deleted", tenant_id=tenant_id, user_id=uid)
