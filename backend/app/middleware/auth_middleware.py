"""JWT validation helper used by route dependencies (see app/dependencies.py).

Kept as a thin middleware-friendly wrapper around core.security so it can
also be used outside of FastAPI's Depends() mechanism (e.g. in websocket
handlers) if needed.
"""
from app.core.security import TokenError, decode_token


def validate_bearer_token(authorization_header: str | None) -> dict:
    if not authorization_header or not authorization_header.lower().startswith("bearer "):
        raise TokenError("Missing or malformed Authorization header.")
    token = authorization_header.split(" ", 1)[1]
    return decode_token(token)
