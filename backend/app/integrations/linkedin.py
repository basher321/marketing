"""LinkedIn company page organic publishing (SPEC-BE-075): the Posts API with an
organization token (w_organization_social; Community Management API access).

- images: /rest/images?action=initializeUpload -> PUT bytes -> image URN
  (2+ images -> multiImage)
- video:  /rest/videos?action=initializeUpload -> PUT each part (ETag) ->
          action=finalizeUpload
- post:   POST /rest/posts; the new post's URN is in the x-restli-id header.
Commentary uses LinkedIn's "little text" format: reserved characters are
escaped, and #tags become {hashtag|\\#|tag} so they stay hashtags.
"""
import re
from typing import Any
from urllib.parse import urlencode

from app.config import get_settings
from app.integrations.social_base import MediaItem, PostPayload, PublishResult, SocialError, call, expiry, oauth_token

PLATFORM = "linkedin"
BASE = "https://api.linkedin.com/rest"
CAPTION_MAX = 3000
RESERVED = re.compile(r"([\\|{}@\[\]()<>*_~])")
HASHTAG = re.compile(r"(?<![\w#])#(\w+)")


def _headers(creds: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {creds['access_token']}", "Linkedin-Version": get_settings().LINKEDIN_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0"}


def _org(creds: dict[str, str]) -> str:
    urn = creds["organization_urn"].strip()
    if not urn.startswith("urn:li:organization:"):
        raise SocialError("The Page must be an organization URN like urn:li:organization:12345.", status_code=422)
    return urn


def little_text(text: str) -> str:
    tags: list[str] = []

    def keep(m: re.Match[str]) -> str:
        tags.append(m.group(1))
        return f"\x00{len(tags) - 1}\x00"

    marked = HASHTAG.sub(keep, text)
    escaped = RESERVED.sub(r"\\\1", marked).replace("#", "\\#")
    return re.sub(r"\x00(\d+)\x00", lambda m: "{hashtag|\\#|" + tags[int(m.group(1))] + "}", escaped)


def check(creds: dict[str, str]) -> dict[str, Any]:
    org_id = _org(creds).rsplit(":", 1)[1]
    org = call(PLATFORM, "GET", f"{BASE}/organizations/{org_id}", headers=_headers(creds)).json()
    return {
        "account_name": org.get("localizedName"),
        "handle": org.get("vanityName"),
        "avatar_url": None,
        "missing_permissions": None,
        "capabilities": {"text_only": True, "image": True, "carousel": True, "video": True, "story": False, "reel": False},
        "limits": {"caption_max": CAPTION_MAX, "hashtags_max": 30, "video_max_s": 1800},
        "extra": {},
    }


def _upload_image(creds: dict[str, str], item: MediaItem) -> str:
    assert item.read is not None
    init = call(PLATFORM, "POST", f"{BASE}/images", params={"action": "initializeUpload"}, headers=_headers(creds),
                json={"initializeUploadRequest": {"owner": _org(creds)}}).json().get("value") or {}
    if not init.get("uploadUrl") or not init.get("image"):
        raise SocialError("LinkedIn didn't return an image upload address.")
    call(PLATFORM, "PUT", init["uploadUrl"], content=item.read(), headers={"Authorization": f"Bearer {creds['access_token']}"}, timeout=300.0)
    return str(init["image"])


def _upload_video(creds: dict[str, str], item: MediaItem) -> str:
    assert item.read is not None
    data = item.read()
    init = call(PLATFORM, "POST", f"{BASE}/videos", params={"action": "initializeUpload"}, headers=_headers(creds),
                json={"initializeUploadRequest": {"owner": _org(creds), "fileSizeBytes": len(data),
                                                  "uploadCaptions": False, "uploadThumbnail": False}}).json().get("value") or {}
    video, instructions = init.get("video"), init.get("uploadInstructions") or []
    if not video or not instructions:
        raise SocialError("LinkedIn didn't return a video upload address.")
    etags = []
    for part in instructions:
        first, last = int(part.get("firstByte") or 0), min(int(part.get("lastByte") or len(data) - 1), len(data) - 1)
        resp = call(PLATFORM, "PUT", part["uploadUrl"], content=data[first:last + 1], timeout=600.0,
                    headers={"Authorization": f"Bearer {creds['access_token']}", "Content-Type": "application/octet-stream"})
        etags.append(resp.headers.get("etag", ""))
    call(PLATFORM, "POST", f"{BASE}/videos", params={"action": "finalizeUpload"}, headers=_headers(creds),
         json={"finalizeUploadRequest": {"video": video, "uploadToken": init.get("uploadToken") or "", "uploadedPartIds": etags}})
    return str(video)


def publish(creds: dict[str, str], payload: PostPayload) -> PublishResult:
    body: dict[str, Any] = {
        "author": _org(creds),
        "commentary": little_text(payload.text),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    videos = [m for m in payload.media if m.kind == "video"]
    images = [m for m in payload.media if m.kind == "image"]
    if videos:
        body["content"] = {"media": {"id": _upload_video(creds, videos[0]), "title": (payload.title or "")[:200]}}
    elif len(images) == 1:
        body["content"] = {"media": {"id": _upload_image(creds, images[0])}}
    elif len(images) > 1:
        body["content"] = {"multiImage": {"images": [{"id": _upload_image(creds, m)} for m in images[:20]]}}
    elif payload.link_url:
        body["content"] = {"article": {"source": payload.link_url, "title": (payload.title or payload.link_url)[:200]}}
    resp = call(PLATFORM, "POST", f"{BASE}/posts", headers=_headers(creds), json=body)
    urn = resp.headers.get("x-restli-id") or ""
    if not urn:
        raise SocialError("LinkedIn didn't return the new post's id.")
    return PublishResult("published", urn, f"https://www.linkedin.com/feed/update/{urn}")


def poll(creds: dict[str, str], ref: dict[str, Any]) -> PublishResult:
    raise SocialError("LinkedIn posts are published synchronously; nothing to poll.")


def metrics(creds: dict[str, str], external_ids: list[str]) -> dict[str, dict[str, float | None]]:
    """organizationalEntityShareStatistics for shares (urn:li:share) and
    ugcPosts; a post type LinkedIn doesn't report leaves nulls."""
    out: dict[str, dict[str, float | None]] = {
        u: {"impressions": None, "reach": None, "clicks": None, "likes": None, "comments": None, "shares": None} for u in external_ids
    }
    from urllib.parse import quote

    for urn in external_ids:
        kind = "shares" if ":share:" in urn else "ugcPosts"
        try:
            body = call(PLATFORM, "GET", f"{BASE}/organizationalEntityShareStatistics?q=organizationalEntity"
                        f"&organizationalEntity={quote(_org(creds), safe='')}&{kind}=List({quote(urn, safe='')})",
                        headers=_headers(creds)).json()
            stats = ((body.get("elements") or [{}])[0].get("totalShareStatistics")) or {}
            out[urn] = {"impressions": _num(stats.get("impressionCount")), "reach": _num(stats.get("uniqueImpressionsCount")),
                        "clicks": _num(stats.get("clickCount")), "likes": _num(stats.get("likeCount")),
                        "comments": _num(stats.get("commentCount")), "shares": _num(stats.get("shareCount"))}
        except (SocialError, IndexError, TypeError):
            pass
    return out


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


# ---------------------------------------------------------------------------
# OAuth connect (SPEC-BE-080): 3-legged OAuth. Access tokens last 60 days; a
# refresh token (365 days) is issued only to apps LinkedIn has approved for
# it - without one the user reconnects when the access token expires.
# ---------------------------------------------------------------------------
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
OAUTH_SCOPES = ("r_organization_admin", "w_organization_social", "r_organization_social")


def oauth_configured() -> bool:
    s = get_settings()
    return bool(s.LINKEDIN_CLIENT_ID and s.LINKEDIN_CLIENT_SECRET.get_secret_value())


def login_url(redirect_uri: str, state: str) -> str:
    query = {"response_type": "code", "client_id": get_settings().LINKEDIN_CLIENT_ID, "redirect_uri": redirect_uri,
             "state": state, "scope": " ".join(OAUTH_SCOPES)}
    return f"{AUTH_URL}?{urlencode(query)}"


def _token(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "access_token": body["access_token"], "refresh_token": body.get("refresh_token") or "",
        "access_expires_at": expiry(body.get("expires_in")), "refresh_expires_at": expiry(body.get("refresh_token_expires_in")),
        "scopes": sorted(x for x in str(body.get("scope") or "").replace(" ", ",").split(",") if x), "account_id": None,
    }


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    s = get_settings()
    return _token(oauth_token(PLATFORM, TOKEN_URL, {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": s.LINKEDIN_CLIENT_ID, "client_secret": s.LINKEDIN_CLIENT_SECRET.get_secret_value()}))


def refresh(refresh_token: str) -> dict[str, Any]:
    s = get_settings()
    return _token(oauth_token(PLATFORM, TOKEN_URL, {
        "grant_type": "refresh_token", "refresh_token": refresh_token,
        "client_id": s.LINKEDIN_CLIENT_ID, "client_secret": s.LINKEDIN_CLIENT_SECRET.get_secret_value()}))


def list_organizations(access_token: str) -> list[dict[str, Any]]:
    """Company pages the signed-in member administers: [{id (URN), name, handle}]."""
    headers = _headers({"access_token": access_token})
    acls = call(PLATFORM, "GET", f"{BASE}/organizationAcls", headers=headers,
                params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"}).json()
    out: list[dict[str, Any]] = []
    for el in acls.get("elements") or []:
        urn = str(el.get("organization") or el.get("organizationTarget") or "")
        if not urn.startswith("urn:li:organization:") or any(o["id"] == urn for o in out):
            continue
        try:
            org = call(PLATFORM, "GET", f"{BASE}/organizations/{urn.rsplit(':', 1)[1]}", headers=headers).json()
        except SocialError:
            org = {}
        out.append({"id": urn, "name": org.get("localizedName") or urn, "handle": org.get("vanityName"), "avatar_url": None})
    return out
