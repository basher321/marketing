"""Registration, login, token, password reset business logic."""
import hashlib
import math
import secrets
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import column, func, insert, literal_column, or_, select, table, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, UnauthorizedError
from app.core.permissions import ROLE_HIERARCHY
from app.core.permissions import Role as AppRole
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.tenant import Tenant
from app.models.user import Role, User, UserRole
from app.schemas.auth import RegisterRequest, TokenResponse
from app.services import tenant_service, user_service
from app.utils.email_sender import send_email

logger = structlog.get_logger(__name__)

# Live UNIQUE constraints a registration race can hit on the new tenant (subdomain = slug).
TENANT_SLUG_CONSTRAINTS = ("tenants_slug_key", "tenants_subdomain_key")

# Documented login 401 messages (SPEC-BE-036 rules 3 and 5). INVALID_CREDENTIALS covers an
# unknown or soft-deleted tenant, an unknown or soft-deleted user, and a wrong password alike,
# so nothing about which part was wrong leaks. The status-specific messages are only returned
# after the password has been verified, so they can't be used to probe accounts either.
INVALID_CREDENTIALS = "Invalid credentials."
TENANT_STATUS_MESSAGES: dict[str, str] = {
    "suspended": "This organization is suspended.",
    "cancelled": "This organization has been cancelled.",
}
USER_STATUS_MESSAGES: dict[str, str] = {
    "invited": "This account has not been activated yet.",
    "disabled": "This account has been disabled.",
    "locked": "This account is locked.",
}
TWO_FACTOR_NOT_SUPPORTED = "Two-factor authentication is not supported yet."

# Tenant statuses (live tenant_status enum) allowed to log in.
LOGIN_TENANT_STATUSES = ("active", "trial")

# Live role_type enum -> app RBAC role (core/permissions.Role), SPEC-BE-036 open decision 1.
# The app's `admin` level has no live equivalent, so nothing maps to it. Unknown values fall
# back to viewer (least privilege).
ROLE_TYPE_TO_APP_ROLE: dict[str, AppRole] = {
    "owner": AppRole.OWNER,
    "manager": AppRole.MANAGER,
    "operator": AppRole.AGENT,
    "analyst": AppRole.VIEWER,
    "viewer": AppRole.VIEWER,
    "custom": AppRole.VIEWER,
}


def register(
    db: Session, payload: RegisterRequest, client: tuple[str | None, str | None] = (None, None)
) -> TokenResponse:
    """Create a new tenant, its first user as owner, and return tokens (SPEC-BE-037).

    Always a NEW tenant: an existing slug is a 409, never a join (joining someone else's
    tenant by slug was a security hole). The slug is already normalized and the password
    already policy-checked by RegisterRequest. Tenant, user, owner role, role assignment and
    the audit row are one transaction: write_audit_log's commit is the only commit, and any
    failure before it leaves nothing behind (get_db closes the session, rolling back).
    """
    try:
        tenant = tenant_service.create_tenant(
            db, payload.tenant_name, payload.tenant_slug, payload.country_code, payload.timezone
        )
        # Active at once and unverified: no email-verification or invite flow exists yet
        # (open decision 3), and login only admits 'active' users.
        user = User(
            tenant_id=tenant.id,
            email=payload.email,
            password_hash=hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            status="active",
            email_verified=False,
        )
        db.add(user)
        db.flush()
        user_service.assign_role(db, str(tenant.id), str(user.id), "owner")
    except IntegrityError as exc:
        # A concurrent registration won the slug/subdomain between the check and the insert.
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint in TENANT_SLUG_CONSTRAINTS:
            raise ConflictError(tenant_service.slug_taken_message(payload.tenant_slug)) from exc
        raise

    # Self-registration has no acting user yet: actor NULL (recorded as actor_type 'system').
    write_audit_log(
        db,
        tenant_id=str(tenant.id),
        actor_user_id=None,
        action="tenant.registered",
        resource_type="tenant",
        resource_id=str(tenant.id),
        metadata={"slug": tenant.slug, "owner_user_id": str(user.id)},
    )
    logger.info("auth.registered", tenant_id=str(tenant.id), user_id=str(user.id))
    return _issue_tokens(db, user, client)


def login(
    db: Session,
    email: str,
    password: str,
    tenant_slug: str,
    client: tuple[str | None, str | None] = (None, None),
) -> TokenResponse:
    tenant = db.scalars(
        select(Tenant).where(Tenant.slug == tenant_slug, Tenant.deleted_at.is_(None))
    ).first()
    if tenant is None:
        logger.info("auth.login_failed", reason="unknown_tenant", tenant_slug=tenant_slug)
        raise UnauthorizedError(INVALID_CREDENTIALS)

    # users.email is citext: the database compares case-insensitively, so the email is passed
    # through unchanged rather than lower-cased here.
    user = db.scalars(
        select(User).where(
            User.tenant_id == tenant.id, User.email == email, User.deleted_at.is_(None)
        )
    ).first()
    if user is None:
        logger.info("auth.login_failed", reason="bad_credentials", tenant_id=tenant.id)
        raise UnauthorizedError(INVALID_CREDENTIALS)

    # Per-account lockout (SPEC-BE-039). While locked, the password is not even checked, so
    # guessing is impossible during the lock; the 429 tells the real user how long to wait.
    now = datetime.now(timezone.utc)
    if user.locked_until is not None and user.locked_until > now:
        logger.info("auth.login_failed", reason="account_locked", user_id=user.id)
        raise AppError(_locked_message(user.locked_until, now), status_code=429)
    if not verify_password(password, user.password_hash):
        logger.info("auth.login_failed", reason="bad_credentials", tenant_id=tenant.id)
        _record_failed_attempt(db, str(user.id), now)
        raise UnauthorizedError(INVALID_CREDENTIALS)

    if tenant.status not in LOGIN_TENANT_STATUSES:
        logger.info("auth.login_failed", reason=f"tenant_{tenant.status}", tenant_id=tenant.id)
        raise UnauthorizedError(TENANT_STATUS_MESSAGES.get(tenant.status, INVALID_CREDENTIALS))
    if user.status != "active":
        logger.info("auth.login_failed", reason=f"user_{user.status}", user_id=user.id)
        raise UnauthorizedError(USER_STATUS_MESSAGES.get(user.status, INVALID_CREDENTIALS))
    if user.two_factor_enabled:
        # No 2FA flow exists yet: refuse rather than silently skip the second factor.
        logger.info("auth.login_failed", reason="two_factor_unsupported", user_id=user.id)
        raise UnauthorizedError(TWO_FACTOR_NOT_SUPPORTED)

    # The writes of a successful login: last_login_at (SPEC-BE-036 rule 8) and clearing the
    # wrong-password lockout state (SPEC-BE-039). users.must_change_password is not enforced
    # here (SPEC-BE-036 open decision 2: allowed to log in).
    user.last_login_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    logger.info("auth.login_succeeded", user_id=user.id, tenant_id=user.tenant_id)
    return _issue_tokens(db, user, client)


def _locked_message(locked_until: datetime, now: datetime) -> str:
    seconds = max(1, math.ceil((locked_until - now).total_seconds()))
    return f"Too many failed attempts. Try again in {seconds} seconds."


def _record_failed_attempt(db: Session, user_id: str, now: datetime) -> None:
    """Count one wrong password; lock the account once the threshold is reached.

    The increment is a single atomic UPDATE ... RETURNING, so concurrent wrong guesses are all
    counted. Lock length escalates: 1 minute at LOGIN_MAX_FAILED_ATTEMPTS, then doubling per
    further failure (2, 4, 8 ...), capped at LOGIN_LOCKOUT_MAX_MINUTES. The attempt that
    triggers a lock is answered with the same 429 as a locked account.
    """
    settings = get_settings()
    count = db.execute(
        update(User)
        .where(User.id == user_id)
        .values(failed_login_attempts=User.failed_login_attempts + 1)
        .returning(User.failed_login_attempts)
        .execution_options(synchronize_session=False)
    ).scalar_one()
    over = count - settings.LOGIN_MAX_FAILED_ATTEMPTS
    if over < 0:
        db.commit()
        return
    minutes = min(2 ** min(over, 10), settings.LOGIN_LOCKOUT_MAX_MINUTES)
    locked_until = now + timedelta(minutes=minutes)
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(locked_until=locked_until)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    logger.info("auth.account_locked", user_id=user_id, failed_attempts=count, minutes=minutes)
    raise AppError(_locked_message(locked_until, now), status_code=429)


# ---------------------------------------------------------------------------
# Refresh-token rotation and revocation (SPEC-BE-071 F7). Every issued refresh token is
# recorded in the live refresh_tokens table as the SHA-256 of its jti (the raw token is never
# stored). A refresh accepts only a recorded, unrevoked, unexpired token, revokes it
# (replaced_by = the new row) and issues a new pair. Presenting an already-revoked token is a
# reuse signal (the token was copied): every active refresh token of that user is revoked.
# Tokens issued before this change have no row, so those sessions must sign in again once.
# Access tokens stay stateless and expire on their own (JWT_ACCESS_TOKEN_EXPIRE_MINUTES).
# ---------------------------------------------------------------------------
REFRESH_INVALID = "Invalid or expired refresh token."
_refresh_tokens = table(
    "refresh_tokens",
    column("id"), column("user_id"), column("tenant_id"), column("token_hash"),
    column("device_info"), column("ip_address"), column("user_agent"), column("expires_at"),
    column("revoked_at"), column("replaced_by"), column("created_at"),
)


def _jti_hash(payload: dict) -> str | None:
    jti = payload.get("jti")
    return _hash_token(str(jti)) if jti else None


def _revoke_all_refresh_tokens(db: Session, user_id: str, now: datetime) -> int:
    """Revoke every active refresh token of a user (no commit). Returns how many."""
    result = db.execute(
        update(_refresh_tokens)
        .where(_refresh_tokens.c.user_id == user_id, _refresh_tokens.c.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return result.rowcount or 0


def refresh(
    db: Session, refresh_token: str, client: tuple[str | None, str | None] = (None, None)
) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except TokenError as exc:
        raise UnauthorizedError(REFRESH_INVALID) from exc

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Wrong token type.")
    token_hash = _jti_hash(payload)
    if token_hash is None:
        raise UnauthorizedError(REFRESH_INVALID)

    now = datetime.now(timezone.utc)
    row = db.execute(
        select(
            _refresh_tokens.c.id, _refresh_tokens.c.user_id, _refresh_tokens.c.revoked_at,
            _refresh_tokens.c.expires_at,
        )
        .where(_refresh_tokens.c.token_hash == token_hash)
        .with_for_update()
    ).first()
    if row is None or str(row.user_id) != str(payload.get("sub")):
        raise UnauthorizedError(REFRESH_INVALID)
    if row.revoked_at is not None:
        # Reuse of a rotated or revoked token: treat the whole session family as stolen.
        count = _revoke_all_refresh_tokens(db, str(row.user_id), now)
        db.commit()
        logger.warning("auth.refresh_token_reused", user_id=str(row.user_id), revoked=count)
        raise UnauthorizedError(REFRESH_INVALID)
    if row.expires_at <= now:
        raise UnauthorizedError(REFRESH_INVALID)

    user = get_active_user(db, payload["sub"])
    if user is None:
        raise UnauthorizedError("User not found.")

    return _issue_tokens(db, user, client, replaces=str(row.id))


def logout(db: Session, refresh_token: str | None) -> None:
    """Revoke the presented refresh token. Silent on anything invalid (no information leak)."""
    if not refresh_token:
        return
    try:
        payload = decode_token(refresh_token)
    except TokenError:
        return
    token_hash = _jti_hash(payload)
    if payload.get("type") != "refresh" or token_hash is None:
        return
    db.execute(
        update(_refresh_tokens)
        .where(_refresh_tokens.c.token_hash == token_hash, _refresh_tokens.c.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()
    logger.info("auth.logged_out", user_id=str(payload.get("sub")))


def get_active_user(db: Session, user_id: str) -> User | None:
    """Load a user who may still authenticate: not soft-deleted and status 'active'."""
    return db.scalars(
        select(User).where(User.id == user_id, User.deleted_at.is_(None), User.status == "active")
    ).first()


def resolve_app_role(db: Session, user_id: str, tenant_id: str) -> str:
    """Return the user's highest app role from user_roles -> roles, or viewer if none.

    Only assignments made within the user's own tenant count (`user_roles.tenant_id`), and the
    role itself must be that tenant's or a system role (`roles.tenant_id IS NULL`), so a role
    from another tenant is never applied.
    """
    role_types = db.scalars(
        select(Role.type)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.tenant_id == tenant_id,
            or_(Role.tenant_id.is_(None), Role.tenant_id == tenant_id),
        )
    ).all()
    app_roles = [ROLE_TYPE_TO_APP_ROLE.get(t, AppRole.VIEWER) for t in role_types]
    return max(app_roles, key=ROLE_HIERARCHY.__getitem__, default=AppRole.VIEWER).value


def _issue_tokens(
    db: Session,
    user: User,
    client: tuple[str | None, str | None] = (None, None),
    replaces: str | None = None,
) -> TokenResponse:
    """Issue a token pair and record the refresh token (SPEC-BE-071 F7); commits.

    `client` is (ip address, user agent) when the route knows them. `replaces` is the
    refresh_tokens row being rotated: it is revoked and pointed at the new row.
    """
    # psycopg2 returns the live native-uuid columns as uuid.UUID despite the String(36)
    # mapping; JWT claims must be JSON strings.
    refresh_token = create_refresh_token(str(user.id), str(user.tenant_id))
    claims = decode_token(refresh_token)
    ip_address, user_agent = client
    new_id = db.execute(
        insert(_refresh_tokens)
        .values(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=_jti_hash(claims),
            device_info=literal_column("'{}'::jsonb"),
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500] or None,
            expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        )
        .returning(_refresh_tokens.c.id)
    ).scalar_one()
    if replaces is not None:
        db.execute(
            update(_refresh_tokens)
            .where(_refresh_tokens.c.id == replaces)
            .values(revoked_at=datetime.now(timezone.utc), replaced_by=new_id)
        )
    db.commit()
    return TokenResponse(
        access_token=create_access_token(str(user.id), str(user.tenant_id)),
        refresh_token=refresh_token,
    )


# ---------------------------------------------------------------------------
# Password reset (SPEC-BE-040). Only a SHA-256 hash of each token is stored
# (password_reset_tokens.token_hash); the raw token lives only in the emailed link. Tokens are
# single-use, expire after RESET_TOKEN_MINUTES, and a user has at most one usable token.
# ---------------------------------------------------------------------------
RESET_TOKEN_MINUTES = 30
RESET_RESEND_SECONDS = 60
RESET_REQUEST_MESSAGE = "If an account exists for that email, a reset link has been sent."
RESET_DONE_MESSAGE = "Your password has been reset. You can now sign in."
RESET_INVALID = "This reset link is invalid or has expired."
_reset_tokens = table(
    "password_reset_tokens",
    column("id"), column("user_id"), column("token_hash"), column("expires_at"),
    column("used_at"), column("created_at"),
)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def request_password_reset(db: Session, email: str, tenant_slug: str) -> None:
    """Issue a reset token and email its link - or silently do nothing.

    Nothing is revealed to the caller: unknown tenant/email, a non-active user or tenant, and
    the anti-spam case (a token issued < RESET_RESEND_SECONDS ago) all return normally
    without creating a token. A send failure is logged, never raised.
    """
    tenant = db.scalars(
        select(Tenant).where(Tenant.slug == tenant_slug, Tenant.deleted_at.is_(None))
    ).first()
    if tenant is None or tenant.status not in LOGIN_TENANT_STATUSES:
        logger.info("auth.password_reset_ignored", tenant_slug=tenant_slug)
        return
    user = db.scalars(
        select(User).where(
            User.tenant_id == tenant.id, User.email == email, User.deleted_at.is_(None)
        )
    ).first()
    if user is None or user.status != "active":
        logger.info("auth.password_reset_ignored", tenant_slug=tenant_slug)
        return

    now = datetime.now(timezone.utc)
    last = db.execute(
        select(func.max(_reset_tokens.c.created_at)).where(_reset_tokens.c.user_id == user.id)
    ).scalar()
    if last is not None and (now - last).total_seconds() < RESET_RESEND_SECONDS:
        logger.info("auth.password_reset_throttled", user_id=str(user.id))
        return

    # One usable token per user: retire the earlier unused ones.
    db.execute(
        update(_reset_tokens)
        .where(_reset_tokens.c.user_id == user.id, _reset_tokens.c.used_at.is_(None))
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        insert(_reset_tokens).values(
            user_id=user.id,
            token_hash=_hash_token(raw),
            expires_at=now + timedelta(minutes=RESET_TOKEN_MINUTES),
            created_at=now,
        )
    )
    db.commit()

    link = f"{get_settings().FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={raw}"
    body = (
        f"Hello,\n\nWe received a request to reset the password for {user.email} "
        f"({tenant.name}).\n\nOpen this link to choose a new password (valid for "
        f"{RESET_TOKEN_MINUTES} minutes, single use):\n{link}\n\n"
        "If you didn't ask for this, you can ignore this email; your password stays the same.\n"
    )
    try:
        send_email(user.email, "Reset your password", body)
    except Exception as exc:  # noqa: BLE001 - never reveal delivery problems to the requester
        logger.error("auth.password_reset_email_failed", user_id=str(user.id), error=str(exc))
    logger.info("auth.password_reset_requested", user_id=str(user.id))


def confirm_password_reset(db: Session, raw_token: str, new_password: str) -> None:
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(_reset_tokens.c.id, _reset_tokens.c.user_id)
        .where(
            _reset_tokens.c.token_hash == _hash_token(raw_token),
            _reset_tokens.c.used_at.is_(None),
            _reset_tokens.c.expires_at > now,
        )
        .with_for_update()
    ).first()
    user = (
        db.scalars(select(User).where(User.id == row.user_id, User.deleted_at.is_(None))).first()
        if row is not None
        else None
    )
    if row is None or user is None:
        raise AppError(RESET_INVALID, status_code=400)

    user.password_hash = hash_password(new_password)
    # A reset also lifts a wrong-password lockout (SPEC-BE-039).
    user.failed_login_attempts = 0
    user.locked_until = None
    db.execute(
        update(_reset_tokens)
        .where(_reset_tokens.c.user_id == user.id, _reset_tokens.c.used_at.is_(None))
        .values(used_at=now)
    )
    # SPEC-BE-071 F7: a new password signs every other session out.
    _revoke_all_refresh_tokens(db, str(user.id), now)
    db.flush()
    # write_audit_log commits: password, token and audit row land together.
    write_audit_log(
        db,
        tenant_id=str(user.tenant_id),
        actor_user_id=str(user.id),
        action="user.password_reset",
        resource_type="user",
        resource_id=str(user.id),
    )
    logger.info("auth.password_reset_completed", user_id=str(user.id))
