"""TikTok organic publishing (SPEC-BE-075): Content Posting API, Direct Post.

- creator_info/query first: the account's allowed privacy levels, interaction
  switches and maximum video length. The post's privacy level must be one of
  them (TikTok's UX rules: the user picks it; there is no default).
- video: post/publish/video/init (FILE_UPLOAD) -> PUT the bytes to upload_url in
  chunks -> status/fetch until PUBLISH_COMPLETE (the job polls).
- photos: post/publish/content/init (media_type PHOTO, PULL_FROM_URL - TikTok
  fetches the images, so the URL domain must be verified in the TikTok app).

Until TikTok audits the developer app, every API post is private
(SELF_ONLY); the accounts page says so.
"""
from typing import Any
from urllib.parse import urlencode

from app.config import get_settings
from app.integrations.social_base import PostPayload, PublishResult, SocialError, call, expiry, from_response, oauth_token

PLATFORM = "tiktok"
BASE = "https://open.tiktokapis.com/v2"
CAPTION_MAX = 2200
PHOTO_TITLE_MAX = 90
PHOTO_DESCRIPTION_MAX = 4000
MIN_CHUNK = 5 * 1024 * 1024
MAX_CHUNK = 64 * 1024 * 1024


def _headers(creds: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {creds['access_token']}", "Content-Type": "application/json; charset=UTF-8"}


def _data(resp: Any) -> dict[str, Any]:
    body = resp.json()
    err = body.get("error") or {}
    if err.get("code") not in (None, "", "ok"):
        code = err.get("code")
        raise SocialError(f"TikTok: {err.get('message') or code}", auth=code in ("access_token_invalid", "scope_not_authorized"),
                          transient=code in ("rate_limit_exceeded", "internal_error"))
    return dict(body.get("data") or {})


def creator_info(creds: dict[str, str]) -> dict[str, Any]:
    return _data(call(PLATFORM, "POST", f"{BASE}/post/publish/creator_info/query/", headers=_headers(creds), json={}))


def check(creds: dict[str, str]) -> dict[str, Any]:
    info = creator_info(creds)
    return {
        "account_name": info.get("creator_nickname") or info.get("creator_username"),
        "handle": info.get("creator_username"),
        "avatar_url": info.get("creator_avatar_url"),
        "missing_permissions": None,
        "capabilities": {"text_only": False, "image": True, "carousel": True, "video": True, "story": False, "reel": False},
        "limits": {"caption_max": CAPTION_MAX, "hashtags_max": None, "video_max_s": info.get("max_video_post_duration_sec")},
        "extra": {
            "privacy_level_options": info.get("privacy_level_options") or [],
            "comment_disabled": bool(info.get("comment_disabled")),
            "duet_disabled": bool(info.get("duet_disabled")),
            "stitch_disabled": bool(info.get("stitch_disabled")),
            "username": info.get("creator_username"),
        },
    }


def _post_info(payload: PostPayload, info: dict[str, Any], photo: bool) -> dict[str, Any]:
    privacy = payload.options.get("privacy_level")
    allowed = info.get("privacy_level_options") or []
    if not privacy or privacy not in allowed:
        raise SocialError(f"Choose a TikTok privacy level ({', '.join(allowed) or 'none offered'}).", status_code=422)
    post: dict[str, Any] = {
        "privacy_level": privacy,
        "disable_comment": bool(payload.options.get("disable_comment") or info.get("comment_disabled")),
    }
    if photo:
        post["title"] = (payload.title or "")[:PHOTO_TITLE_MAX]
        post["description"] = payload.text[:PHOTO_DESCRIPTION_MAX]
        post["auto_add_music"] = bool(payload.options.get("auto_add_music", True))
    else:
        post["title"] = payload.text[:CAPTION_MAX]
        post["disable_duet"] = bool(payload.options.get("disable_duet") or info.get("duet_disabled"))
        post["disable_stitch"] = bool(payload.options.get("disable_stitch") or info.get("stitch_disabled"))
    return post


def publish(creds: dict[str, str], payload: PostPayload) -> PublishResult:
    if not payload.media:
        raise SocialError("TikTok posts need a video or photos.", status_code=422)
    info = creator_info(creds)
    videos = [m for m in payload.media if m.kind == "video"]
    if videos:
        video = videos[0]
        limit = info.get("max_video_post_duration_sec")
        if limit and video.duration_ms and video.duration_ms / 1000 > float(limit):
            raise SocialError(f"This TikTok account allows videos up to {limit} s.", status_code=422)
        assert video.read is not None
        data = video.read()
        size = len(data)
        chunk = size if size <= MAX_CHUNK else 10 * 1024 * 1024
        count = max(1, size // chunk)
        init = _data(call(PLATFORM, "POST", f"{BASE}/post/publish/video/init/", headers=_headers(creds), json={
            "post_info": _post_info(payload, info, False),
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count},
        }))
        upload_url, publish_id = init.get("upload_url"), init.get("publish_id")
        if not upload_url or not publish_id:
            raise SocialError("TikTok didn't return an upload address.")
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1  # the last chunk takes the remainder
            from app.integrations.base_adapter import PlatformError, http

            try:
                resp = http("PUT", upload_url, content=data[start:end + 1], timeout=600.0,
                            headers={"Content-Type": video.mime, "Content-Range": f"bytes {start}-{end}/{size}"})
            except PlatformError as exc:
                raise SocialError(exc.message, transient=True) from None
            if resp.status_code >= 400:
                raise from_response(PLATFORM, resp)
        return PublishResult("processing", ref={"publish_id": publish_id, "username": info.get("creator_username")})
    images = [m for m in payload.media if m.kind == "image"][:35]
    urls = [m.public_url() for m in images if m.public_url]
    init = _data(call(PLATFORM, "POST", f"{BASE}/post/publish/content/init/", headers=_headers(creds), json={
        "post_info": _post_info(payload, info, True),
        "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": urls},
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }))
    if not init.get("publish_id"):
        raise SocialError("TikTok didn't return a publish id.")
    return PublishResult("processing", ref={"publish_id": init["publish_id"], "username": info.get("creator_username")})


def poll(creds: dict[str, str], ref: dict[str, Any]) -> PublishResult:
    data = _data(call(PLATFORM, "POST", f"{BASE}/post/publish/status/fetch/", headers=_headers(creds),
                      json={"publish_id": ref.get("publish_id")}))
    status = data.get("status")
    if status == "FAILED":
        raise SocialError(f"TikTok couldn't publish the post ({data.get('fail_reason') or 'no reason given'}).")
    if status != "PUBLISH_COMPLETE":
        return PublishResult("processing", ref=ref)
    ids = data.get("publicaly_available_post_id") or data.get("publicly_available_post_id") or []
    post_id = str(ids[0]) if ids else str(ref.get("publish_id"))
    # Private (SELF_ONLY) posts have no public id; the publish id is kept.
    url = f"https://www.tiktok.com/@{ref['username']}/video/{ids[0]}" if ids and ref.get("username") else None
    return PublishResult("published", post_id, url)


def metrics(creds: dict[str, str], external_ids: list[str]) -> dict[str, dict[str, float | None]]:
    """Needs the video.list scope; without it every metric stays null."""
    empty: dict[str, float | None] = {"impressions": None, "likes": None, "comments": None, "shares": None, "video_views": None}
    out = {vid: dict(empty) for vid in external_ids}
    if not external_ids:
        return out
    try:
        data = _data(call(PLATFORM, "POST", f"{BASE}/video/query/", headers=_headers(creds),
                          params={"fields": "id,like_count,comment_count,share_count,view_count"},
                          json={"filters": {"video_ids": external_ids[:20]}}))
    except SocialError:
        return out
    for v in data.get("videos") or []:
        vid = str(v.get("id"))
        if vid in out:
            out[vid] = {"impressions": None, "likes": _num(v.get("like_count")), "comments": _num(v.get("comment_count")),
                        "shares": _num(v.get("share_count")), "video_views": _num(v.get("view_count"))}
    return out


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


# ---------------------------------------------------------------------------
# OAuth connect (SPEC-BE-080): TikTok Login Kit for Web. Access tokens last
# 24 h, refresh tokens 365 days; TikTok may rotate the refresh token, so the
# one in each answer is the one to keep.
# ---------------------------------------------------------------------------
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
OAUTH_SCOPES = ("user.info.basic", "video.publish", "video.upload", "video.list")


def oauth_configured() -> bool:
    s = get_settings()
    return bool(s.TIKTOK_CLIENT_KEY and s.TIKTOK_CLIENT_SECRET.get_secret_value())


def login_url(redirect_uri: str, state: str) -> str:
    query = {"client_key": get_settings().TIKTOK_CLIENT_KEY, "scope": ",".join(OAUTH_SCOPES), "response_type": "code",
             "redirect_uri": redirect_uri, "state": state}
    return f"{AUTH_URL}?{urlencode(query)}"


def _token(body: dict[str, Any]) -> dict[str, Any]:
    scope = body.get("scope") or ""
    return {
        "access_token": body["access_token"], "refresh_token": body.get("refresh_token") or "",
        "access_expires_at": expiry(body.get("expires_in")), "refresh_expires_at": expiry(body.get("refresh_expires_in")),
        "scopes": sorted(x for x in str(scope).replace(" ", ",").split(",") if x), "account_id": body.get("open_id"),
    }


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    s = get_settings()
    return _token(oauth_token(PLATFORM, f"{BASE}/oauth/token/", {
        "client_key": s.TIKTOK_CLIENT_KEY, "client_secret": s.TIKTOK_CLIENT_SECRET.get_secret_value(), "code": code,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri}))


def refresh(refresh_token: str) -> dict[str, Any]:
    s = get_settings()
    return _token(oauth_token(PLATFORM, f"{BASE}/oauth/token/", {
        "client_key": s.TIKTOK_CLIENT_KEY, "client_secret": s.TIKTOK_CLIENT_SECRET.get_secret_value(),
        "grant_type": "refresh_token", "refresh_token": refresh_token}))
