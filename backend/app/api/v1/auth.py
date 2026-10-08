"""/auth endpoints (register, login, refresh, logout)."""
import ipaddress

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _client(request: Request) -> tuple[str | None, str | None]:
    """(ip address, user agent) recorded with each refresh token (SPEC-BE-071 F7).

    refresh_tokens.ip_address is inet: a client host that isn't an IP address (a Unix
    socket, a test client) is recorded as unknown rather than failing the login.
    """
    host = request.client.host if request.client else None
    try:
        ip = str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        ip = None
    return (ip, request.headers.get("user-agent"))


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    return auth_service.register(db, payload, _client(request))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return auth_service.login(
        db, payload.email, payload.password, payload.tenant_slug, _client(request)
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    return auth_service.refresh(db, payload.refresh_token, _client(request))


# Password reset (SPEC-BE-040). Both unauthenticated. The request always answers the same
# 202, whether or not the account exists, so emails can't be probed.
@router.post("/password-reset/request", response_model=MessageResponse, status_code=202)
def request_password_reset(
    payload: PasswordResetRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    auth_service.request_password_reset(db, payload.email, payload.tenant_slug)
    return MessageResponse(message=auth_service.RESET_REQUEST_MESSAGE)


@router.post("/password-reset/confirm", response_model=MessageResponse, status_code=200)
def confirm_password_reset(
    payload: PasswordResetConfirm, db: Session = Depends(get_db)
) -> MessageResponse:
    auth_service.confirm_password_reset(db, payload.token, payload.new_password)
    return MessageResponse(message=auth_service.RESET_DONE_MESSAGE)


@router.post("/logout", status_code=204)
def logout(payload: LogoutRequest | None = None, db: Session = Depends(get_db)) -> None:
    # SPEC-BE-071 F7: revokes the presented refresh token. Always 204, whatever was sent, so
    # nothing about the token leaks. The access token expires on its own (15 minutes).
    auth_service.logout(db, payload.refresh_token if payload else None)
