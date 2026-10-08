"""Password hashing, JWT encode/decode, token utilities."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# SPEC-BE-071 F14: the configured cost factor is used (it was ignored before).
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS)

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: str, tenant_id: str, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, tenant_id: str) -> str:
    return _create_token(
        user_id, tenant_id, "access", timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(user_id: str, tenant_id: str) -> str:
    return _create_token(
        user_id, tenant_id, "refresh", timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    )


class TokenError(Exception):
    pass


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY.get_secret_value(), algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
