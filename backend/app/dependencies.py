"""Shared FastAPI dependencies (DB session, current user, current tenant)."""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_token
from app.core.tenant_context import set_current_tenant_id
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.services import auth_service

__all__ = ["get_db", "get_current_user", "get_current_tenant", "require_permission", "require_super_admin"]


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token."
        )
    return authorization.split(" ", 1)[1]


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_bearer_token(authorization)
    try:
        payload = decode_token(token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token."
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type.")

    # SPEC-BE-036: only a non-deleted, status='active' user authenticates; a user disabled,
    # locked or deleted after the token was issued gets 401 on the next request.
    user = auth_service.get_active_user(db, payload["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    # `users` has no role column: the app role is resolved from user_roles -> roles within the
    # user's own tenant, for require_permission / core.permissions.require_role.
    user.role = auth_service.resolve_app_role(db, user.id, user.tenant_id)
    set_current_tenant_id(user.tenant_id)
    return user


def get_current_tenant(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Tenant:
    tenant = db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    return tenant


def require_permission(minimum_role: str):
    from app.core.permissions import Role, role_at_least

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not role_at_least(current_user.role, Role(minimum_role)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions."
            )
        return current_user

    return dependency


def require_super_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """PilotSonic's Super admin (SPEC-BE-101): a row in platform_admins, which no
    route writes. Anyone else gets a plain 404, so the admin routes aren't revealed."""
    from app.services import platform_service

    if not platform_service.is_super_admin(db, str(current_user.id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return current_user
