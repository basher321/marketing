"""Facebook Page organic publishing (SPEC-BE-075). Graph API with a Page access
token (pages_manage_posts, pages_read_engagement).

- text (+ link): POST /{page}/feed
- one image:     POST /{page}/photos (multipart source + caption)
- 2+ images:     each POST /{page}/photos published=false, then /{page}/feed
                 with attached_media
- video / reel:  POST graph-video /{page}/videos (multipart source + description)
Bytes are uploaded, so Facebook needs no public media URL.
"""
import json
from typing import Any
from urllib.parse import urlencode

from app.config import get_settings
from app.integrations.meta_ads import graph_base
from app.integrations.social_base import MediaItem, PostPayload, PublishResult, SocialError, call

PLATFORM = "facebook"
CAPTION_MAX = 63206
REQUIRED_PERMISSIONS = ("pages_manage_posts", "pages_read_engagement")
# Post insights requested by metrics(); a metric Meta no longer serves comes
# back as an error for the whole call, so each is asked separately and a
# failure leaves that metric null (never estimated).
INSIGHTS = {"impressions": "post_impressions", "reach": "post_impressions_unique", "clicks": "post_clicks"}


def _video_base() -> str:
    return graph_base().replace("://graph.", "://graph-video.")


def _handle_from_link(link: str | None) -> str | None:
    # facebook.com/<vanity> -> "<vanity>"; profile.php?id=... links have no handle.
    if not link or "profile.php" in link:
        return None
    slug = link.rstrip("/").rsplit("/", 1)[-1]
    return slug or None


def _page_creds(creds: dict[str, str]) -> dict[str, str]:
    """The pasted token may be a *user* token (Graph API Explorer's default)
    rather than the Page's own token. Reading or posting to a Page with a user
    token fails with "#100 ... requires the 'pages_read_engagement' permission",
    so ask Graph for the Page token: GET /{page}?fields=access_token answers it
    when the token's user manages the Page (pages_show_list). If that fails the
    pasted token is used as-is (it may already be a Page token)."""
    try:
        body = call(PLATFORM, "GET", f"{graph_base()}/{creds['page_id']}",
                    params={"fields": "access_token", "access_token": creds["access_token"]}).json()
    except SocialError as exc:
        if exc.auth or exc.transient:
            raise
        return creds
    token = body.get("access_token")
    return {**creds, "access_token": token} if token else creds


PAGE_READ_HINT = (
    " Use a Page access token for this Page (Graph API Explorer: choose the Page under"
    " 'User or Page'), or a user token with pages_show_list, pages_read_engagement and"
    " pages_manage_posts from someone who manages the Page. Check the Page ID too."
)


def check(creds: dict[str, str]) -> dict[str, Any]:
    creds = _page_creds(creds)
    # `username` is not requested: Graph answers "#100 nonexisting field
    # (username)" for Pages without a vanity name on current versions, which
    # failed the whole check. The handle is derived from `link` instead.
    try:
        page = call(PLATFORM, "GET", f"{graph_base()}/{creds['page_id']}",
                    params={"fields": "name,link,picture{url}", "access_token": creds["access_token"]}).json()
    except SocialError as exc:
        if exc.auth or exc.transient:
            raise
        raise SocialError(exc.message.rstrip(". ") + "." + PAGE_READ_HINT) from None
    missing: list[str] | None = None
    try:
        perms = call(PLATFORM, "GET", f"{graph_base()}/me/permissions", params={"access_token": creds["access_token"]}).json()
        granted = {p.get("permission") for p in perms.get("data") or [] if p.get("status") == "granted"}
        if granted:
            missing = [p for p in REQUIRED_PERMISSIONS if p not in granted]
    except SocialError:
        missing = None  # a Page token can't list permissions; publishing will tell
    return {
        "account_name": page.get("name"),
        "handle": _handle_from_link(page.get("link")),
        "avatar_url": ((page.get("picture") or {}).get("data") or {}).get("url"),
        "missing_permissions": missing,
        "capabilities": {"text_only": True, "image": True, "carousel": True, "video": True, "story": False, "reel": True},
        "limits": {"caption_max": CAPTION_MAX, "hashtags_max": 30, "video_max_s": 14400},
        "extra": {"link": page.get("link")},
    }


def _photo(creds: dict[str, str], item: MediaItem, caption: str | None, published: bool) -> dict[str, Any]:
    assert item.read is not None
    data = {"access_token": creds["access_token"], "published": "true" if published else "false"}
    if caption:
        data["caption"] = caption
    return call(PLATFORM, "POST", f"{graph_base()}/{creds['page_id']}/photos", data=data,
                files={"source": (f"{item.media_id}.img", item.read(), item.mime)}, timeout=120.0).json()


def publish(creds: dict[str, str], payload: PostPayload) -> PublishResult:
    creds = _page_creds(creds)
    page = creds["page_id"]
    token = creds["access_token"]
    images = [m for m in payload.media if m.kind == "image"]
    videos = [m for m in payload.media if m.kind == "video"]
    if videos:
        video = videos[0]
        assert video.read is not None
        video_data = {"access_token": token, "description": payload.text}
        if payload.title:
            video_data["title"] = payload.title
        res = call(PLATFORM, "POST", f"{_video_base()}/{page}/videos", data=video_data,
                   files={"source": (f"{video.media_id}.mp4", video.read(), video.mime)}, timeout=600.0).json()
        vid = str(res.get("id") or "")
        return PublishResult("published", vid, f"https://www.facebook.com/{page}/videos/{vid}" if vid else None)
    if len(images) == 1:
        res = _photo(creds, images[0], payload.text, True)
        post_id = str(res.get("post_id") or res.get("id") or "")
        return PublishResult("published", post_id, f"https://www.facebook.com/{post_id}" if post_id else None)
    data: dict[str, str] = {"access_token": token, "message": payload.text}
    if images:
        for i, img in enumerate(images[:10]):
            fbid = _photo(creds, img, None, False).get("id")
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": fbid})
    elif payload.link_url:
        data["link"] = payload.link_url
    res = call(PLATFORM, "POST", f"{graph_base()}/{page}/feed", data=data).json()
    post_id = str(res.get("id") or "")
    return PublishResult("published", post_id, f"https://www.facebook.com/{post_id}" if post_id else None)


def poll(creds: dict[str, str], ref: dict[str, Any]) -> PublishResult:
    raise SocialError("Facebook posts are published synchronously; nothing to poll.")


def metrics(creds: dict[str, str], external_ids: list[str]) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    token = _page_creds(creds)["access_token"]
    for pid in external_ids:
        row: dict[str, float | None] = {k: None for k in ("impressions", "reach", "likes", "comments", "shares", "clicks")}
        try:
            obj = call(PLATFORM, "GET", f"{graph_base()}/{pid}", params={
                "fields": "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0),shares",
                "access_token": token}).json()
            row["likes"] = float(((obj.get("reactions") or {}).get("summary") or {}).get("total_count") or 0)
            row["comments"] = float(((obj.get("comments") or {}).get("summary") or {}).get("total_count") or 0)
            row["shares"] = float((obj.get("shares") or {}).get("count") or 0)
        except SocialError:
            pass
        for key, metric in INSIGHTS.items():
            try:
                ins = call(PLATFORM, "GET", f"{graph_base()}/{pid}/insights", params={"metric": metric, "access_token": token}).json()
                values = ((ins.get("data") or [{}])[0].get("values") or [{}])
                if values and values[0].get("value") is not None:
                    row[key] = float(values[0]["value"])
            except (SocialError, IndexError, TypeError, ValueError):
                pass
        out[pid] = row
    return out


# ---------------------------------------------------------------------------
# OAuth connect (SPEC-BE-080): Facebook Login with the Meta app of SPEC-BE-054.
# A Page token derived from a long-lived user token doesn't expire, so the
# Page (and its Instagram account) needs no refresh.
# ---------------------------------------------------------------------------
OAUTH_SCOPES = (
    "pages_show_list", "pages_read_engagement", "pages_manage_posts", "read_insights",
    "instagram_basic", "instagram_content_publish", "instagram_manage_insights", "business_management",
)


def oauth_configured() -> bool:
    s = get_settings()
    return bool(s.META_APP_ID and s.META_APP_SECRET.get_secret_value())


def login_url(redirect_uri: str, state: str) -> str:
    s = get_settings()
    query: dict[str, str] = {"client_id": s.META_APP_ID, "redirect_uri": redirect_uri, "response_type": "code", "state": state}
    if s.META_SOCIAL_LOGIN_CONFIG_ID:
        # Facebook Login for Business: the configuration names the permissions.
        query["config_id"] = s.META_SOCIAL_LOGIN_CONFIG_ID
    else:
        query["scope"] = ",".join(OAUTH_SCOPES)
    return f"https://www.facebook.com/{s.META_GRAPH_VERSION}/dialog/oauth?{urlencode(query)}"


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    """code -> long-lived user token -> the Pages it manages (each with its own
    Page token and linked Instagram account) and the granted permissions."""
    s = get_settings()
    app = {"client_id": s.META_APP_ID, "client_secret": s.META_APP_SECRET.get_secret_value()}
    short_lived = call(PLATFORM, "GET", f"{graph_base()}/oauth/access_token",
                       params={**app, "redirect_uri": redirect_uri, "code": code}).json().get("access_token")
    if not short_lived:
        raise SocialError("Facebook didn't return an access token.")
    long_lived = call(PLATFORM, "GET", f"{graph_base()}/oauth/access_token",
                      params={**app, "grant_type": "fb_exchange_token", "fb_exchange_token": short_lived}).json().get("access_token") or short_lived
    accounts = call(PLATFORM, "GET", f"{graph_base()}/me/accounts", params={
        "fields": "id,name,access_token,picture{url},instagram_business_account{id,username,profile_picture_url}",
        "limit": "100", "access_token": long_lived}).json()
    perms = call(PLATFORM, "GET", f"{graph_base()}/me/permissions", params={"access_token": long_lived}).json()
    pages = []
    for p in accounts.get("data") or []:
        if not p.get("access_token"):
            continue  # a Page the user can't manage
        ig = p.get("instagram_business_account") or None
        pages.append({
            "id": str(p["id"]), "name": p.get("name") or str(p["id"]), "token": p["access_token"],
            "avatar_url": ((p.get("picture") or {}).get("data") or {}).get("url"),
            "instagram": {"id": str(ig["id"]), "username": ig.get("username"), "avatar_url": ig.get("profile_picture_url")} if ig else None,
        })
    scopes = sorted(str(x.get("permission")) for x in perms.get("data") or [] if x.get("status") == "granted")
    return {"pages": pages, "scopes": scopes}
