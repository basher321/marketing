"""Organic social publishing contract (SPEC-BE-075).

Each of integrations/{facebook,instagram,tiktok,linkedin}.py is a module with:

    check(creds) -> dict                     profile: account_name, handle, avatar_url,
                                             missing_permissions (None = couldn't tell),
                                             capabilities, limits, extra
    publish(creds, payload) -> PublishResult  state "published", or "processing" + ref
    poll(creds, ref) -> PublishResult         for async containers / uploads
    metrics(creds, items) -> {external_id: {metric: number | None}}

`creds` is integration_service.ad_platform_connection(...)["fields"]: decrypted,
never logged or returned. Every HTTP call goes through base_adapter.http, so
httpx.MockTransport and dev_fakes intercept it.

Errors are SocialError:
- transient (retry later): HTTP 5xx, 429, timeouts / network errors, Meta
  codes 1, 2, 4, 17, 341 and is_transient=true;
- auth (integration marked expired): HTTP 401, Meta code 190;
- otherwise permanent, keeping the platform's own message.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.integrations.base_adapter import PlatformError, short

PLATFORMS = ("facebook", "instagram", "tiktok", "linkedin")
# channel_type / integration_provider per platform (the same names).
PROVIDER = {p: p for p in PLATFORMS}
META_TRANSIENT_CODES = {1, 2, 4, 17, 341, 368}


class SocialError(PlatformError):
    def __init__(self, message: str, *, transient: bool = False, auth: bool = False, status_code: int = 502):
        super().__init__(message, status_code=status_code, auth=auth)
        self.transient = transient


@dataclass
class MediaItem:
    media_id: str
    kind: str  # image | video
    mime: str
    size: int
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    # Lazy: a public URL can raise (no public https address); bytes are read
    # only by the platforms that upload them.
    public_url: Callable[[], str] | None = None
    read: Callable[[], bytes] | None = None


@dataclass
class PostPayload:
    text: str
    link_url: str | None = None
    media: list[MediaItem] = field(default_factory=list)
    post_format: str = "post"  # post | carousel | reel | story | video
    title: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishResult:
    state: str  # published | processing
    external_id: str | None = None
    external_url: str | None = None
    ref: dict[str, Any] = field(default_factory=dict)


def from_response(platform: str, resp: httpx.Response) -> SocialError:
    """A failed platform answer -> SocialError with the platform's message."""
    message = f"HTTP {resp.status_code}"
    code: Any = None
    transient_flag = False
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            message = str(err.get("error_user_msg") or err.get("message") or message)
            code = err.get("code")
            transient_flag = bool(err.get("is_transient"))
        elif body.get("message"):
            message = str(body["message"])
    auth = resp.status_code == 401 or code == 190 or (platform == "tiktok" and code in ("access_token_invalid", "scope_not_authorized"))
    transient = (
        resp.status_code == 429
        or resp.status_code >= 500
        or transient_flag
        or (isinstance(code, int) and code in META_TRANSIENT_CODES)
        or code == "rate_limit_exceeded"
    )
    return SocialError(f"{platform.title()}: {short(message, 300)}", transient=transient and not auth, auth=auth)


def wrap_network(exc: PlatformError) -> SocialError:
    """base_adapter.http turns timeouts/network errors into PlatformError: retryable."""
    return SocialError(exc.message, transient=True, status_code=exc.status_code)


def call(platform: str, method: str, url: str, **kwargs: Any) -> httpx.Response:
    from app.integrations.base_adapter import http

    try:
        resp = http(method, url, **kwargs)
    except SocialError:
        raise
    except PlatformError as exc:
        raise wrap_network(exc) from None
    if resp.status_code >= 400:
        raise from_response(platform, resp)
    return resp


# ---------------------------------------------------------------------------
# OAuth (SPEC-BE-080): token endpoints of TikTok and LinkedIn (form POST).
# ---------------------------------------------------------------------------
def oauth_token(platform: str, url: str, data: dict[str, str]) -> dict[str, Any]:
    """POST a token request; the token body, or SocialError. A rejected grant
    (invalid/expired code or refresh token, bad client) is auth=True so the
    integration is marked expired; 5xx / 429 / network errors are transient.
    The request and answer hold secrets: never logged."""
    from app.integrations.base_adapter import http

    try:
        resp = http("POST", url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    except PlatformError as exc:
        raise wrap_network(exc) from None
    try:
        body = resp.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    if resp.status_code < 400 and body.get("access_token"):
        return body
    # TikTok answers HTTP 200 with {"error": "invalid_grant", ...}; LinkedIn 400.
    err = body.get("error")
    if isinstance(err, dict):
        err = err.get("code") or err.get("message")
    message = body.get("error_description") or body.get("message") or err or f"HTTP {resp.status_code}"
    transient = resp.status_code == 429 or resp.status_code >= 500
    raise SocialError(f"{platform.title()}: {short(message, 300)}", transient=transient, auth=not transient)


def expiry(seconds: Any) -> str | None:
    """expires_in seconds -> an ISO UTC timestamp (None when not given / 0)."""
    from datetime import datetime, timedelta, timezone

    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=value)).isoformat() if value > 0 else None


def adapter(platform: str) -> Any:
    import importlib

    if platform not in PLATFORMS:
        raise SocialError(f"{platform} publishing isn't supported.")
    return importlib.import_module(f"app.integrations.{platform}")
