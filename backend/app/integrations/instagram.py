"""Instagram organic publishing (SPEC-BE-075): the Instagram Graph API content
publishing flow for professional accounts (instagram_content_publish).

1. Create a container: POST /{ig}/media with image_url / video_url (public
   https - Instagram fetches the file itself; media_service.platform_url).
   Reels: media_type=REELS; Stories: media_type=STORIES; carousel: one child
   container per item (is_carousel_item) then a CAROUSEL container.
2. Wait until the container's status_code is FINISHED (videos take a while:
   publish() returns "processing" and the job polls).
3. POST /{ig}/media_publish creation_id -> the media id; permalink read back.

The account's rolling-24h API publishing limit is checked first
(content_publishing_limit); reaching it is a permanent error with the reason.
"""
from typing import Any

from app.integrations.meta_ads import graph_base
from app.integrations.social_base import MediaItem, PostPayload, PublishResult, SocialError, call

PLATFORM = "instagram"
CAPTION_MAX = 2200
HASHTAGS_MAX = 30
REQUIRED_PERMISSIONS = ("instagram_basic", "instagram_content_publish")


def check(creds: dict[str, str]) -> dict[str, Any]:
    token = creds["access_token"]
    ig = call(PLATFORM, "GET", f"{graph_base()}/{creds['ig_account_id']}",
              params={"fields": "username,name,profile_picture_url", "access_token": token}).json()
    missing: list[str] | None = None
    try:
        perms = call(PLATFORM, "GET", f"{graph_base()}/me/permissions", params={"access_token": token}).json()
        granted = {p.get("permission") for p in perms.get("data") or [] if p.get("status") == "granted"}
        if granted:
            missing = [p for p in REQUIRED_PERMISSIONS if p not in granted]
    except SocialError:
        missing = None
    quota = _quota(creds)
    return {
        "account_name": ig.get("name") or ig.get("username"),
        "handle": ig.get("username"),
        "avatar_url": ig.get("profile_picture_url"),
        "missing_permissions": missing,
        "capabilities": {"text_only": False, "image": True, "carousel": True, "video": True, "story": True, "reel": True},
        "limits": {"caption_max": CAPTION_MAX, "hashtags_max": HASHTAGS_MAX, "video_max_s": 900,
                   "posts_per_24h": quota[1] if quota else 100, "posts_used_24h": quota[0] if quota else None},
        "extra": {},
    }


def _quota(creds: dict[str, str]) -> tuple[int, int] | None:
    try:
        body = call(PLATFORM, "GET", f"{graph_base()}/{creds['ig_account_id']}/content_publishing_limit",
                    params={"fields": "quota_usage,config", "access_token": creds["access_token"]}).json()
        row = (body.get("data") or [{}])[0]
        return int(row.get("quota_usage") or 0), int((row.get("config") or {}).get("quota_total") or 100)
    except (SocialError, ValueError, TypeError, IndexError):
        return None


def _container(creds: dict[str, str], item: MediaItem, fields: dict[str, str]) -> str:
    assert item.public_url is not None
    body = {"access_token": creds["access_token"], **fields}
    if item.kind == "image":
        body["image_url"] = item.public_url()
    else:
        body["video_url"] = item.public_url()
    res = call(PLATFORM, "POST", f"{graph_base()}/{creds['ig_account_id']}/media", data=body, timeout=120.0).json()
    cid = res.get("id")
    if not cid:
        raise SocialError("Instagram didn't return a container id.")
    return str(cid)


def _container_status(creds: dict[str, str], cid: str) -> str:
    body = call(PLATFORM, "GET", f"{graph_base()}/{cid}", params={"fields": "status_code,status", "access_token": creds["access_token"]}).json()
    code = str(body.get("status_code") or "")
    if code in ("ERROR", "EXPIRED"):
        raise SocialError(f"Instagram couldn't process the media ({body.get('status') or code}).")
    return code


def _publish_container(creds: dict[str, str], cid: str) -> PublishResult:
    res = call(PLATFORM, "POST", f"{graph_base()}/{creds['ig_account_id']}/media_publish",
               data={"creation_id": cid, "access_token": creds["access_token"]}).json()
    media_id = str(res.get("id") or "")
    permalink = None
    if media_id:
        try:
            permalink = call(PLATFORM, "GET", f"{graph_base()}/{media_id}",
                             params={"fields": "permalink", "access_token": creds["access_token"]}).json().get("permalink")
        except SocialError:
            permalink = None
    return PublishResult("published", media_id, permalink)


def publish(creds: dict[str, str], payload: PostPayload) -> PublishResult:
    if not payload.media:
        raise SocialError("Instagram posts need an image or a video.", status_code=422)
    quota = _quota(creds)
    if quota and quota[0] >= quota[1]:
        raise SocialError(f"Instagram's limit of {quota[1]} API posts per 24 hours is reached; try again later.")
    fmt = payload.post_format
    caption = {"caption": payload.text} if fmt != "story" else {}
    if fmt == "carousel" and len(payload.media) >= 2:
        children = []
        for item in payload.media[:10]:
            extra = {"is_carousel_item": "true"}
            if item.kind == "video":
                extra["media_type"] = "VIDEO"
            children.append(_container(creds, item, extra))
        body ={"access_token": creds["access_token"], "media_type": "CAROUSEL", "children": ",".join(children), **caption}
        cid = str(call(PLATFORM, "POST", f"{graph_base()}/{creds['ig_account_id']}/media", data=body).json().get("id") or "")
        if not cid:
            raise SocialError("Instagram didn't return a carousel container id.")
    else:
        item = payload.media[0]
        fields: dict[str, str] = dict(caption)
        if fmt == "story":
            fields["media_type"] = "STORIES"
        elif item.kind == "video":
            fields["media_type"] = "REELS"
            if payload.options.get("share_to_feed") is not None:
                fields["share_to_feed"] = "true" if payload.options["share_to_feed"] else "false"
        cid = _container(creds, item, fields)
    status = _container_status(creds, cid)
    if status and status != "FINISHED":
        return PublishResult("processing", ref={"container": cid})
    return _publish_container(creds, cid)


def poll(creds: dict[str, str], ref: dict[str, Any]) -> PublishResult:
    cid = str(ref.get("container") or "")
    if not cid:
        raise SocialError("Nothing to poll for this Instagram post.")
    if _container_status(creds, cid) != "FINISHED":
        return PublishResult("processing", ref=ref)
    return _publish_container(creds, cid)


# Instagram retired "impressions" for new media in 2025; "views" is its
# replacement and is stored as impressions (the closest meaning).
METRICS = {"views": "impressions", "reach": "reach", "likes": "likes", "comments": "comments", "shares": "shares", "saved": "saves"}


def metrics(creds: dict[str, str], external_ids: list[str]) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for mid in external_ids:
        row: dict[str, float | None] = {v: None for v in METRICS.values()}
        try:
            body = call(PLATFORM, "GET", f"{graph_base()}/{mid}/insights",
                        params={"metric": ",".join(METRICS), "access_token": creds["access_token"]}).json()
            for item in body.get("data") or []:
                key = METRICS.get(str(item.get("name")))
                values = item.get("values") or []
                if key and values and values[0].get("value") is not None:
                    row[key] = float(values[0]["value"])
        except (SocialError, TypeError, ValueError):
            pass
        out[mid] = row
    return out
