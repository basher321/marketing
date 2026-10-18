"""Organic posts through SocialAPI (SPEC-BE-104).

The SPEC-BE-075 publishing contract (see social_base) for a platform whose only
usable connection is the company's SocialAPI account:

    publish(creds, payload) -> PublishResult
    poll(creds, ref) -> PublishResult
    metrics(creds, ids) -> {external_id: {metric: number | None}}

`creds` = {key, account_id, platform} from social_account_service.connection():
the company's brand-restricted key, never logged or returned.

Mapping rules:
- Media from our library is uploaded to SocialAPI as bytes, so no public URL is
  needed (unlike direct Instagram).
- POST /posts with publish_now and one target. The organic payload carries a
  link separately only when there's no media; SocialAPI has no link field, so
  it is added to the text.
- `external_id` is the **SocialAPI post id**, because results are read by it;
  `external_url` is the platform permalink.
- Target status published -> published; pending / publishing -> processing
  (ref {post_id}, polled with GET /posts/{id}); failed -> SocialError with
  SocialAPI's message (error category rate_limit / system = transient).
- HTTP 429 / 5xx are transient. A 401 is transient too: the next attempt's
  account lookup rebuilds the company key (SPEC-BE-101 Amendment A), and a
  direct integration is never marked expired for it.
"""
from typing import Any

from app.integrations import socialapi as api
from app.integrations.social_base import MediaItem, PostPayload, PublishResult, SocialError

EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "video/mp4": "mp4",
       "video/quicktime": "mov"}
TRANSIENT_CATEGORIES = {"rate_limit", "system"}
ENGAGEMENT = ("likes", "comments", "shares", "saves")


def _error(exc: api.SocialAPIError) -> SocialError:
    return SocialError(exc.message, transient=exc.transient or exc.auth, status_code=exc.status_code)


def _upload(key: str, m: MediaItem) -> dict[str, str]:
    if m.read is None:
        raise SocialError("A media file of this post can't be read.")
    name = f"{m.media_id}.{EXT.get(m.mime, m.mime.split('/')[-1])}"
    media_id = api.upload_media(key, name, m.mime, m.read())
    return {"source_type": "media_id", "source": media_id, "type": "video" if m.kind == "video" else "image"}


def _result(post: dict[str, Any], account_id: str) -> PublishResult:
    targets = [t for t in (post.get("targets") or []) if isinstance(t, dict)]
    target = next((t for t in targets if str(t.get("account_id")) == account_id), targets[0] if targets else {})
    status = str(target.get("status") or post.get("status") or "")
    post_id = str(post.get("id") or "")
    if status == "published":
        return PublishResult("published", external_id=post_id or None, external_url=target.get("permalink") or None)
    if status == "failed":
        raw = target.get("error")
        err: dict[str, Any] = raw if isinstance(raw, dict) else {}
        message = str(err.get("message") or "SocialAPI couldn't publish the post.")
        raise SocialError(f"SocialAPI: {message}", transient=str(err.get("category") or "") in TRANSIENT_CATEGORIES)
    if status in ("cancelled",):
        raise SocialError("SocialAPI cancelled the post.")
    # pending / publishing / scheduled: delivery runs in the background.
    return PublishResult("processing", ref={"post_id": post_id})


def publish(creds: dict[str, Any], payload: PostPayload) -> PublishResult:
    key, account_id, platform = str(creds["key"]), str(creds["account_id"]), str(creds.get("platform") or "")
    try:
        media = [_upload(key, m) for m in payload.media]
        text = payload.text
        if payload.link_url and payload.link_url not in text:
            text = f"{text}\n\n{payload.link_url}".strip()
        body: dict[str, Any] = {"text": text, "targets": [{"account_id": account_id}], "publish_now": True}
        if media:
            body["media"] = media
        if payload.title:
            body["title"] = payload.title
        privacy = payload.options.get("privacy_level")
        if platform == "tiktok" and privacy:
            body["platform_data"] = {"tiktok": {"privacy_level": privacy}}
        post = api.create_post(key, body)
    except api.SocialAPIError as exc:
        raise _error(exc) from None
    return _result(post, account_id)


def poll(creds: dict[str, Any], ref: dict[str, Any]) -> PublishResult:
    post_id = str(ref.get("post_id") or "")
    if not post_id:
        raise SocialError("Publishing state unknown — check SocialAPI before retrying.")
    try:
        post = api.get_post(str(creds["key"]), post_id)
    except api.SocialAPIError as exc:
        raise _error(exc) from None
    return _result(post, str(creds["account_id"]))


def metrics(creds: dict[str, Any], ids: list[str]) -> dict[str, dict[str, float | None]]:
    """Likes, comments, shares and saves per SocialAPI post (the other organic
    metrics aren't reported by SocialAPI: absent, never estimated)."""
    key, account_id = str(creds["key"]), str(creds["account_id"])
    out: dict[str, dict[str, float | None]] = {}
    for post_id in ids:
        try:
            targets = api.post_metrics(key, post_id)
        except api.SocialAPIError as exc:
            if exc.status_code == 404:
                continue  # deleted in SocialAPI
            raise _error(exc) from None
        target = next((t for t in targets if str(t.get("account_id")) == account_id), targets[0] if targets else {})
        m = target.get("metrics") if isinstance(target.get("metrics"), dict) else None
        if m:
            out[post_id] = {k: (float(m[k]) if isinstance(m.get(k), (int, float)) else None) for k in ENGAGEMENT}
    return out
