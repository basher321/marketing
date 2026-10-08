"""RBAC permission checks and decorators."""
from enum import Enum
from functools import wraps
from typing import Callable

from fastapi import HTTPException, status


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    AGENT = "agent"
    VIEWER = "viewer"


ROLE_HIERARCHY: dict[Role, int] = {
    Role.OWNER: 100,
    Role.ADMIN: 80,
    Role.MANAGER: 60,
    Role.AGENT: 40,
    Role.VIEWER: 20,
}


def role_at_least(user_role: str, minimum: Role) -> bool:
    try:
        return ROLE_HIERARCHY[Role(user_role)] >= ROLE_HIERARCHY[minimum]
    except ValueError:
        return False


def require_role(minimum: Role) -> Callable:
    """Dependency-style decorator for service/route functions receiving a `current_user`."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if current_user is None or not role_at_least(current_user.role, minimum):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions for this action.",
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
