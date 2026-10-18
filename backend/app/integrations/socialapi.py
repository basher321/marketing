"""SocialAPI.ai client (SPEC-BE-083): one third-party API for organic posting,
analytics and the inbox on many social platforms.

SocialAPI has no paid-ads features (no campaigns, budgets or targeting); it
publishes organic posts and reads/answers comments, DMs and reviews. It holds
the platform tokens itself: we only keep the company's SocialAPI key
(`sapi_key_...`), sent as `Authorization: Bearer <key>`.

Every call goes through base_adapter.http, so httpx.MockTransport in tests and
dev_fakes (META_FAKE_TRANSPORT=true) intercept it. The key is never logged.

Errors are SocialAPIError (a PlatformError):
- auth: HTTP 401 (bad / revoked key), so the key card shows "fix the key";
- transient: 429, 5xx, timeouts / network errors (try again later);
- otherwise permanent, with SocialAPI's own `error.message`.
API reference: https://docs.social-api.ai/llms.txt
"""
from typing import Any
from urllib.parse import quote

import httpx

from app.integrations.base_adapter import PlatformError, short

BASE_URL = "https://api.social-api.ai/v1"
DOCS_URL = "https://docs.social-api.ai/"
# Platform slugs SocialAPI uses (GET /posts `platform` filter).
PLATFORMS = (
    "instagram", "facebook", "threads", "tiktok", "linkedin", "youtube", "twitter",
    "bluesky", "pinterest", "google", "telegram", "whatsapp", "zalo",
)
# Connected through SocialAPI's managed OAuth (POST /accounts/connect -> auth_url).
# X/Twitter is listed by SocialAPI as "coming soon"; its own error is shown if refused.
OAUTH_PLATFORMS = ("instagram", "facebook", "threads", "tiktok", "linkedin", "youtube", "pinterest", "google", "twitter")
# Media at or below this size goes through the one-request upload (POST /media/upload);
# larger files and every video use the presigned URL flow (no API size limit, only
# the plan's storage quota). The one-request upload is documented as 50 MB but
# answers a bare HTTP 413 well below that for video.
PRESIGNED_FROM_BYTES = 4 * 1024 * 1024
UPLOAD_TIMEOUT = 600.0  # seconds for the PUT of a large video to SocialAPI's storage


class SocialAPIError(PlatformError):
    def __init__(self, message: str, *, status_code: int = 502, auth: bool = False, transient: bool = False,
                 code: str | None = None) -> None:
        super().__init__(message, status_code=status_code, auth=auth)
        self.transient = transient
        self.code = code


def _error(resp: httpx.Response) -> SocialAPIError:
    """{"error": {"code", "message", "meta"}, "request_id"} -> SocialAPIError."""
    message, code = f"HTTP {resp.status_code}", None
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or message)
            code = str(err.get("code")) if err.get("code") else None
        elif isinstance(err, str) and err:
            message = err
        elif body.get("message"):
            message = str(body["message"])
    auth = resp.status_code == 401
    transient = resp.status_code == 429 or resp.status_code >= 500
    # Our own status: a bad key / rejected input is the user's to fix (422),
    # a quota (429) stays 429, anything upstream is 502.
    status = 422 if auth or resp.status_code in (400, 409, 413, 422) else 404 if resp.status_code == 404 \
        else 429 if resp.status_code == 429 else 403 if resp.status_code in (402, 403) else 502
    if auth:
        message = "the API key was rejected (it may be revoked or mistyped)."
    return SocialAPIError(f"SocialAPI: {short(message, 300)}", status_code=status, auth=auth,
                          transient=transient and not auth, code=code)


def call(key: str, method: str, path: str, **kwargs: Any) -> Any:
    """One API call -> the parsed JSON body ({} for 204 / empty)."""
    from app.integrations.base_adapter import http

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    headers.update(kwargs.pop("headers", None) or {})
    try:
        resp = http(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
    except PlatformError as exc:
        raise SocialAPIError(exc.message.replace("The platform", "SocialAPI"), status_code=exc.status_code,
                             transient=True) from None
    if resp.status_code >= 400:
        raise _error(resp)
    if resp.status_code == 204 or not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        raise SocialAPIError("SocialAPI returned an unreadable answer.") from None


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v not in (None, "")}


def data_list(body: Any) -> list[dict[str, Any]]:
    data = body.get("data") if isinstance(body, dict) else body
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def next_cursor(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    page = body.get("pagination")
    cursor = page.get("next_cursor") if isinstance(page, dict) else body.get("next_cursor")
    return str(cursor) if cursor else None


# --- Accounts and brands ------------------------------------------------------
def list_accounts(key: str) -> list[dict[str, Any]]:
    return data_list(call(key, "GET", "/accounts"))


def list_brands(key: str) -> list[dict[str, Any]]:
    return data_list(call(key, "GET", "/brands"))


def create_brand(key: str, name: str) -> dict[str, Any]:
    return _data(call(key, "POST", "/brands", json={"name": name}))


# Every scope a brand-restricted key may hold (webhooks:manage and analytics:read
# can't be given to one; SPEC-BE-101, docs: guides/scoped-keys).
RESTRICTED_SCOPES = ["accounts:read", "accounts:manage", "posts:read", "posts:write", "media:read", "media:write",
                     "inbox:read", "inbox:write", "dms:read", "dms:send", "automations:read", "automations:write"]


def create_key(key: str, name: str, brand_ids: list[str], scopes: list[str]) -> dict[str, Any]:
    """POST /keys with a full-access key -> {id, raw_key, ...}; raw_key is shown once."""
    return _data(call(key, "POST", "/keys", json={"name": name, "brand_ids": brand_ids, "scopes": scopes}))


def _data(body: Any) -> dict[str, Any]:
    """{"data": {...}} or the object itself."""
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return dict(body["data"])
    return body if isinstance(body, dict) else {}


def connect(key: str, platform: str, brand_id: str | None, redirect_uri: str, state: str) -> dict[str, Any]:
    """202 -> {"auth_url"}; 201 (direct auth) -> the account."""
    return call(key, "POST", "/accounts/connect",
                json=_clean({"platform": platform, "brand_id": brand_id, "redirect_uri": redirect_uri, "state": state}))


def disconnect(key: str, account_id: str) -> None:
    call(key, "DELETE", f"/accounts/{account_id}")


# A Facebook / Google sign-in that can reach several Pages / locations comes back
# with status=selection_required + connection_id (the login id): the user picks one.
_CHOICES = {"facebook": ("pages", "platform_page_id"), "google": ("locations", "platform_account_id")}


def login_choices(key: str, platform: str, login_id: str) -> list[dict[str, Any]]:
    kind, id_field = _CHOICES[platform]
    body = call(key, "GET", f"/platforms/{platform}/logins/{login_id}/{kind}")
    rows = body.get(kind) if isinstance(body, dict) else None
    return [
        {
            "id": str(r.get(id_field) or ""),
            "name": r.get("name") or str(r.get(id_field) or ""),
            "detail": r.get("category"),
            "picture_url": r.get("picture_url"),
            "assignable": bool(r.get("assignable", True)),
            "assigned_account_id": r.get("assigned_account_id"),
        }
        for r in (rows if isinstance(rows, list) else [])
        if isinstance(r, dict) and r.get(id_field)
    ]


def assign_choice(key: str, platform: str, login_id: str, choice_id: str, brand_id: str) -> dict[str, Any]:
    kind, _ = _CHOICES[platform]
    # Google location ids are resource names ("accounts/1/locations/2"): URL-encoded.
    encoded = quote(choice_id, safe="")
    return call(key, "POST", f"/platforms/{platform}/logins/{login_id}/{kind}/{encoded}/assign", json={"brand_id": brand_id})


# A sign-in that returns status=selection_required carries a PENDING connection id
# (pc_...), not a login id: its choices are read and resolved under
# /accounts/pending/{connection_id} (single-use, expires 30 minutes after sign-in).
# Facebook lists "pages" (every Facebook connect is pending), Google "profiles".
def pending_choices(key: str, platform: str, connection_id: str) -> list[dict[str, Any]]:
    body = _data(call(key, "GET", f"/accounts/pending/{quote(connection_id, safe='')}"))
    if platform == "facebook":
        rows, id_field, name_field, detail_field = body.get("pages"), "platform_page_id", "name", "category"
    else:
        rows, id_field, name_field, detail_field = body.get("profiles"), "platform_account_id", "display_name", "bio"
    return [
        {
            "id": str(r.get(id_field) or ""),
            "name": r.get(name_field) or str(r.get(id_field) or ""),
            "detail": r.get(detail_field) or None,
            "picture_url": r.get("picture_url") or r.get("profile_picture_url") or None,
            "assignable": bool(r.get("assignable", True)),
            "assigned_account_id": r.get("assigned_account_id") or None,
        }
        for r in (rows if isinstance(rows, list) else [])
        if isinstance(r, dict) and r.get(id_field)
    ]


def select_pending(key: str, platform: str, connection_id: str, choice_id: str) -> dict[str, Any]:
    """Facebook takes a list of Page ids, Google one Business Profile id. -> the account."""
    body: dict[str, Any] = {"page_ids": [choice_id]} if platform == "facebook" else {"platform_account_id": choice_id}
    return _data(call(key, "POST", f"/accounts/pending/{quote(connection_id, safe='')}/select", json=body))


def boards(key: str, account_id: str) -> list[dict[str, Any]]:
    return data_list(call(key, "GET", f"/accounts/{account_id}/boards"))


def account_analytics(key: str, account_id: str, start: str, end: str) -> dict[str, Any]:
    return _data(call(key, "GET", f"/accounts/{account_id}/analytics", params={"from": start, "to": end}))


# --- Media and posts ---------------------------------------------------------
def upload_media(key: str, filename: str, mime: str, content: bytes) -> str:
    """Videos and anything over PRESIGNED_FROM_BYTES go through the presigned
    URL (the one-request upload answers a bare HTTP 413 for larger bodies);
    small images use the one-request upload, falling back to presigned on 413."""
    if mime.startswith("video/") or len(content) > PRESIGNED_FROM_BYTES:
        return _upload_presigned(key, filename, mime, content)
    try:
        body = call(key, "POST", "/media/upload", files={"file": (filename, content, mime)})
    except SocialAPIError as exc:
        if exc.code is None and exc.message.endswith("HTTP 413"):
            return _upload_presigned(key, filename, mime, content)
        raise
    data = _data(body)
    media_id = data.get("media_id") or data.get("id")
    if not media_id:
        raise SocialAPIError("SocialAPI didn't return a media id for the upload.")
    return str(media_id)


def _upload_presigned(key: str, filename: str, mime: str, content: bytes) -> str:
    """GET /media/upload-url -> PUT the bytes to upload_url -> POST /media/{id}/verify
    (mandatory: unverified media stays pending and publishing fails)."""
    from app.integrations.base_adapter import http

    data = _data(call(key, "GET", "/media/upload-url", params={"media_type": mime, "filename": filename}))
    media_id, upload_url = data.get("media_id"), data.get("upload_url")
    if not media_id or not upload_url:
        raise SocialAPIError("SocialAPI didn't return an upload link for the media.")
    try:
        # The signed URL carries its own auth: no SocialAPI key on this request.
        resp = http("PUT", str(upload_url), content=content, headers={"Content-Type": mime}, timeout=UPLOAD_TIMEOUT)
    except PlatformError as exc:
        raise SocialAPIError(exc.message.replace("The platform", "SocialAPI's storage"), status_code=exc.status_code,
                             transient=True) from None
    if resp.status_code >= 300:
        raise SocialAPIError(f"SocialAPI's storage refused {filename} (HTTP {resp.status_code}).",
                             transient=resp.status_code >= 500)
    call(key, "POST", f"/media/{media_id}/verify")
    return str(media_id)


def create_post(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    # 201 accepted, 207 partial success: both are answers, not errors. 422
    # (every account failed) is raised with SocialAPI's message.
    return _data(call(key, "POST", "/posts", json=payload))


def list_posts(key: str, *, status: str | None, platform: str | None, search: str | None, cursor: str | None,
               limit: int = 25) -> tuple[list[dict[str, Any]], str | None]:
    body = call(key, "GET", "/posts", params=_clean({"status": status, "platform": platform, "search": search,
                                                       "cursor": cursor, "limit": limit, "sort": "created_desc"}))
    return data_list(body), next_cursor(body)


def get_post(key: str, post_id: str) -> dict[str, Any]:
    return _data(call(key, "GET", f"/posts/{post_id}"))


def publish_post(key: str, post_id: str) -> dict[str, Any]:
    return _data(call(key, "POST", f"/posts/{post_id}/publish"))


def retry_post(key: str, post_id: str) -> None:
    call(key, "POST", f"/posts/{post_id}/retry")


def delete_post(key: str, post_id: str) -> dict[str, Any]:
    body = call(key, "DELETE", f"/posts/{post_id}")
    return body if isinstance(body, dict) else {}


def validate_post(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = call(key, "POST", "/posts/validate", json=payload)
    return body if isinstance(body, dict) else {}


def constraints(key: str, platform: str | None) -> dict[str, Any]:
    body = call(key, "GET", "/posts/validate", params=_clean({"platform": platform}))
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else {}


def post_metrics(key: str, post_id: str) -> list[dict[str, Any]]:
    body = call(key, "GET", f"/posts/{post_id}/metrics")
    data = body.get("data") if isinstance(body, dict) else None
    targets = data.get("targets") if isinstance(data, dict) else None
    return [t for t in targets if isinstance(t, dict)] if isinstance(targets, list) else []


# --- Inbox --------------------------------------------------------------------
def conversations(key: str, *, platform: str | None, account_id: str | None, status: str | None,
                  cursor: str | None) -> dict[str, Any]:
    body = call(key, "GET", "/inbox/conversations", params=_clean({
        "platform": platform, "account_id": account_id, "status": status, "cursor": cursor, "limit": 25}))
    return {"items": data_list(body), "next_cursor": next_cursor(body),
            "sync_state": body.get("sync_state") if isinstance(body, dict) else None}


def messages(key: str, conversation_id: str, cursor: str | None) -> dict[str, Any]:
    body = call(key, "GET", f"/inbox/conversations/{conversation_id}/messages",
                params=_clean({"cursor": cursor, "limit": 50}))
    return {"items": data_list(body), "next_cursor": next_cursor(body)}


def send_message(key: str, conversation_id: str, account_id: str, text: str) -> dict[str, Any]:
    body = call(key, "POST", f"/inbox/conversations/{conversation_id}/messages",
                json={"account_id": account_id, "text": text})
    return body if isinstance(body, dict) else {}


def commented_posts(key: str, *, platform: str | None, account_id: str | None, cursor: str | None) -> dict[str, Any]:
    body = call(key, "GET", "/inbox/comments", params=_clean({
        "platform": platform, "account_id": account_id, "cursor": cursor, "limit": 25}))
    return {"items": data_list(body), "next_cursor": next_cursor(body)}


# Comment paths: {post_id} is the PLATFORM post id; {comment_id} is SocialAPI's
# interaction id (sapi_cmt_...), per the inbox guide.
def comments(key: str, post_id: str, account_id: str, cursor: str | None) -> dict[str, Any]:
    body = call(key, "GET", f"/inbox/comments/{post_id}",
                params=_clean({"account_id": account_id, "cursor": cursor, "limit": 50}))
    return {"items": data_list(body), "next_cursor": next_cursor(body)}


def reply_comment(key: str, post_id: str, account_id: str, comment_id: str, text: str) -> dict[str, Any]:
    body = call(key, "POST", f"/inbox/comments/{post_id}",
                json={"account_id": account_id, "comment_id": comment_id, "text": text})
    return body if isinstance(body, dict) else {}


def moderate_comment(key: str, post_id: str, comment_id: str, account_id: str, action: str) -> None:
    if action == "delete":
        call(key, "DELETE", f"/inbox/comments/{post_id}/{comment_id}", params={"account_id": account_id})
    else:  # hide | unhide
        call(key, "POST", f"/inbox/comments/{post_id}/{comment_id}/{action}", json={"account_id": account_id})


def reviews(key: str, account_id: str, cursor: str | None) -> dict[str, Any]:
    body = call(key, "GET", f"/inbox/reviews/{account_id}", params=_clean({"cursor": cursor, "limit": 20}))
    summary = body.get("summary") if isinstance(body, dict) and isinstance(body.get("summary"), dict) else {}
    return {"items": data_list(body), "next_cursor": next_cursor(body), "summary": summary}


def reply_review(key: str, review_id: str, account_id: str, text: str) -> dict[str, Any]:
    body = call(key, "POST", f"/inbox/reviews/{review_id}/reply", json={"account_id": account_id, "text": text})
    return body if isinstance(body, dict) else {}
