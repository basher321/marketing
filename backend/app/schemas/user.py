"""User management schemas (SPEC-BE-037)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator

from app.schemas.auth import check_password_strength

# Live role_type values accepted by the users API. `custom` is rejected: no permission model
# exists for custom roles yet, and they would silently resolve to viewer.
RoleType = Literal["owner", "manager", "operator", "analyst", "viewer"]
# PATCH may only activate or disable a user; invited/locked have no flow that sets them yet.
SettableUserStatus = Literal["active", "disabled"]


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    role: RoleType

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str, info: ValidationInfo) -> str:
        return check_password_strength(value, info.data.get("email"))


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    role: RoleType | None = None
    status: SettableUserStatus | None = None


class UserRead(BaseModel):
    id: str
    email: str
    first_name: str | None
    last_name: str | None
    # The user's highest live role_type within their tenant; "viewer" when none is assigned.
    role: str
    # Live user_status enum: active, invited, disabled, locked.
    status: str
    last_login_at: datetime | None
    created_at: datetime
