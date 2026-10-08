"""Login, register, token, password reset schemas."""
import re

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator

from app.utils import locale_data
from app.utils.slugify import slugify
from app.validators.password_policy import validate_password_strength

# Live CHECK constraints tenants.slug_format / tenants.subdomain_format (SPEC-BE-037 rule 2).
TENANT_SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")
TENANT_SLUG_MAX_LENGTH = 100


def check_password_strength(password: str, email: str | None = None) -> str:
    """Pydantic validator body: 422 with every password-policy message joined."""
    errors = validate_password_strength(password, email)
    if errors:
        raise ValueError(" ".join(errors))
    return password


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    tenant_slug: str
    email: EmailStr
    password: str
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    # SPEC-BE-072: detected by the sign-up page from the browser (optional). The company's
    # currency follows the country; without them the database defaults (USD, UTC) apply.
    # These are hints, not user input, so sign-up never fails on them: an old zone name
    # (Chrome reports Asia/Calcutta) is mapped to the current one, and anything unusable
    # is dropped.
    timezone: str | None = Field(default=None, max_length=64)
    country_code: str | None = Field(default=None, max_length=8)

    @field_validator("timezone")
    @classmethod
    def detected_timezone(cls, value: str | None) -> str | None:
        return locale_data.canonical_timezone(value)

    @field_validator("country_code")
    @classmethod
    def detected_country(cls, value: str | None) -> str | None:
        code = (value or "").strip().upper()
        return code if locale_data.is_country(code) else None

    @field_validator("tenant_slug")
    @classmethod
    def normalize_tenant_slug(cls, value: str) -> str:
        # The normalized slug is also the tenant's subdomain, so it must satisfy the live
        # slug/subdomain format checks; "My Shop!" -> "my-shop", "!!!" or "my_shop" -> 422.
        slug = slugify(value)
        if not slug or len(slug) > TENANT_SLUG_MAX_LENGTH or not TENANT_SLUG_PATTERN.match(slug):
            raise ValueError(
                "Tenant slug must contain only lowercase letters, digits and hyphens "
                f"(max {TENANT_SLUG_MAX_LENGTH} characters)."
            )
        return slug

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str, info: ValidationInfo) -> str:
        return check_password_strength(value, info.data.get("email"))


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=4096)


class PasswordResetRequest(BaseModel):
    email: EmailStr
    tenant_slug: str


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return check_password_strength(value)


class MessageResponse(BaseModel):
    message: str
