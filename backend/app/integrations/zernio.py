"""Zernio client (SPEC-BE-084): one paid-ads API for Meta (Facebook/Instagram),
Google Ads, TikTok, LinkedIn, Pinterest and X.

One server-wide key (settings.ZERNIO_API_KEY, `Authorization: Bearer <key>`)
serves every company; each company works inside its own Zernio profile (see
services/zernio_service.py, which also enforces that every id belongs to it).
Zernio holds the platform tokens (managed OAuth); we never see them.

Every call goes through base_adapter.http, so httpx.MockTransport in tests and
dev_fakes (META_FAKE_TRANSPORT=true) intercept it. The key is never logged.

API reference: https://zernio.com/openapi.json (v1.244, read 2026-10-08).
Errors are {"error": "<message>", "type", "code", "param", "details"}.
Money: Zernio takes budgets and bids in WHOLE currency units (USD 50 = $50.00),
not cents; callers pass Decimal major units.
"""
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.integrations.base_adapter import PlatformError, short

TIMEOUT = 30.0
LONG_TIMEOUT = 120.0  # create / boost / video upload block on the platform


class ZernioError(PlatformError):
    def __init__(self, message: str, *, status_code: int = 502, code: str | None = None,
                 retry_after: str | None = None) -> None:
        super().__init__(message, status_code=status_code)
        self.code = code
        self.retry_after = retry_after


def configured() -> bool:
    return bool(get_settings().ZERNIO_API_KEY.get_secret_value().strip())


def _message(body: Any, fallback: str) -> tuple[str, str | None]:
    if isinstance(body, dict):
        err = body.get("error")
        code = body.get("code") if isinstance(body.get("code"), str) else None
        if isinstance(err, dict):
            return str(err.get("message") or fallback), (str(err["code"]) if err.get("code") else code)
        if isinstance(err, str) and err:
            return err, code
        if body.get("message"):
            return str(body["message"]), code
    return fallback, None


def _error(resp: httpx.Response) -> ZernioError:
    try:
        body = resp.json()
    except ValueError:
        body = None
    message, code = _message(body, f"HTTP {resp.status_code}")
    s = resp.status_code
    # Our status (SPEC-BE-084 FR13): Zernio's message is shown as is.
    if s == 401:
        # The server-wide key is the operator's to fix, not the user's.
        return ZernioError("Zernio rejected this server's API key; ask the administrator to check ZERNIO_API_KEY.",
                           status_code=503, code=code)
    if s == 501:
        return ZernioError(f"Not available on this platform: {short(message, 300)}", status_code=422, code=code)
    if s in (402, 403):
        # Zernio's own refusal (ads add-on / payment required, plan or account limits,
        # beta-only platform). Not a 403 here: the app shows every 403 as "your role
        # can't do this", which would hide Zernio's reason.
        return ZernioError(f"Zernio refused this: {short(message, 400)}", status_code=422, code=code)
    status = 422 if s in (400, 409, 422) else 404 if s == 404 else 429 if s == 429 else 502
    return ZernioError(f"Zernio: {short(message, 400)}", status_code=status, code=code,
                       retry_after=resp.headers.get("retry-after"))


def call(method: str, path: str, *, timeout: float = TIMEOUT, idempotency_key: str | None = None,
         **kwargs: Any) -> Any:
    """One API call -> the parsed JSON body ({} for an empty answer)."""
    from app.integrations.base_adapter import http

    st = get_settings()
    key = st.ZERNIO_API_KEY.get_secret_value().strip()
    if not key:
        raise ZernioError("Zernio isn't set up on this server (ZERNIO_API_KEY is empty).", status_code=503)
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:255]
    try:
        resp = http(method, f"{st.ZERNIO_BASE_URL.rstrip('/')}{path}", headers=headers, timeout=timeout, **kwargs)
    except PlatformError as exc:
        raise ZernioError(exc.message.replace("The platform", "Zernio"), status_code=exc.status_code) from None
    if resp.status_code >= 400:
        raise _error(resp)
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        raise ZernioError("Zernio returned an unreadable answer.") from None


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v not in (None, "", [], {})}


def money(value: Decimal) -> float:
    """Decimal major units -> the JSON number Zernio takes (whole units, not cents)."""
    return float(value)


# ---------------------------------------------------------------------------
# Platform rules (from the POST /ads/create schema; the frontend's options come
# only from here, via GET /zernio/platforms)
# ---------------------------------------------------------------------------
META_CTAS = [
    "LEARN_MORE", "SHOP_NOW", "SIGN_UP", "BOOK_TRAVEL", "CONTACT_US", "DOWNLOAD", "GET_OFFER", "GET_QUOTE",
    "SUBSCRIBE", "WATCH_MORE", "ADD_TO_CART", "APPLY_NOW", "BOOK_NOW", "BUY_TICKETS", "DONATE", "DONATE_NOW",
    "GET_DIRECTIONS", "GET_SHOWTIMES", "LISTEN_NOW", "ORDER_NOW", "PLAY_GAME", "REQUEST_TIME", "SEE_MENU",
    "START_ORDER", "INSTALL_MOBILE_APP", "USE_APP",
]
LINKEDIN_CTAS = ["LEARN_MORE", "SIGN_UP", "DOWNLOAD", "SUBSCRIBE", "REGISTER", "JOIN", "ATTEND", "REQUEST_DEMO",
                 "VIEW_QUOTE", "APPLY", "SEE_MORE", "SHOP_NOW", "BUY_NOW"]
# TikTok passes the CTA through to the creative; this is the common subset of
# Zernio's enum that TikTok also offers.
TIKTOK_CTAS = ["LEARN_MORE", "SHOP_NOW", "SIGN_UP", "DOWNLOAD", "CONTACT_US", "BOOK_NOW", "APPLY_NOW", "ORDER_NOW",
               "WATCH_MORE", "SUBSCRIBE", "GET_QUOTE"]
SPECIAL_AD_CATEGORIES = ["HOUSING", "EMPLOYMENT", "CREDIT", "FINANCIAL_PRODUCTS_SERVICES", "ISSUES_ELECTIONS_POLITICS",
                         "ONLINE_GAMBLING_AND_GAMING"]
BID_STRATEGIES = ["LOWEST_COST_WITHOUT_CAP", "LOWEST_COST_WITH_BID_CAP", "COST_CAP", "LOWEST_COST_WITH_MIN_ROAS"]
INCOME_TIERS = ["top_5", "top_10", "top_10_25", "top_25_50"]
PLACEMENTS = {
    "publisher_platforms": ["facebook", "instagram", "threads", "messenger", "audience_network", "whatsapp"],
    "facebook_positions": ["feed", "right_hand_column", "marketplace", "video_feeds", "story", "search", "instream_video",
                           "facebook_reels", "facebook_reels_overlay", "profile_feed", "notification"],
    "instagram_positions": ["stream", "story", "explore", "explore_home", "reels", "profile_feed", "ig_search",
                            "profile_reels"],
    "messenger_positions": ["messenger_home", "sponsored_messages", "story"],
    "audience_network_positions": ["classic", "rewarded_video"],
    "threads_positions": ["threads_stream"],
    "whatsapp_positions": ["status"],
    "device_platforms": ["mobile", "desktop"],
}

GOAL_LABELS = {
    "awareness": "Awareness: show the ad to as many people as possible",
    "traffic": "Traffic: send people to a website",
    "engagement": "Engagement: likes, comments and shares",
    "video_views": "Video views",
    "lead_generation": "Leads with an instant form (needs a lead form id)",
    "lead_conversion": "Website leads tracked by your pixel",
    "conversions": "Sales / conversions tracked by your pixel",
    "app_promotion": "App installs",
    "page_likes": "Page likes",
    "page_visits": "Page visits and followers",
}

# Goals per platform. Meta, LinkedIn and Google follow Zernio's documented
# lists; for TikTok, Pinterest and X Zernio's docs don't enumerate every goal,
# so these are the standard objectives and Zernio's own message is shown if
# the platform refuses one. catalog_sales and job_applicants need catalogs /
# job postings, which are out of phase 1 (SPEC-BE-084 D4).
_META_GOALS = ["awareness", "traffic", "engagement", "video_views", "lead_generation", "lead_conversion",
               "conversions", "app_promotion", "page_likes", "page_visits"]
# Targeting fields: the portable ones (countries, age, gender, languages) plus
# platform-only ones per Zernio's TargetingSpec notes.
_GEO = ["countries", "regions", "cities", "zips", "metros"]
PLATFORMS: dict[str, dict[str, Any]] = {
    "facebook": {
        "label": "Facebook", "ads_account": "metaads", "tree": "facebook", "family": "meta",
        "goals": _META_GOALS, "ctas": META_CTAS, "media": ["image", "video"],
        "targeting": _GEO + ["city_radius", "custom_locations", "excluded_locations", "age", "gender", "languages",
                             "interests", "behaviors", "income_tier", "placements", "special_ad_categories"],
        "limits": {"headline": 255, "description": 255}, "bid": True, "validate": True, "preview": True,
    },
    "instagram": {
        "label": "Instagram", "ads_account": "metaads", "tree": "instagram", "family": "meta",
        "goals": _META_GOALS, "ctas": META_CTAS, "media": ["image", "video"],
        "targeting": _GEO + ["city_radius", "custom_locations", "excluded_locations", "age", "gender", "languages",
                             "interests", "behaviors", "income_tier", "placements", "special_ad_categories"],
        "limits": {"headline": 255, "description": 255}, "bid": True, "validate": True, "preview": True,
    },
    "tiktok": {
        # TikTok ads are video-only (Zernio's imageUrl carries the video URL).
        "label": "TikTok", "ads_account": "tiktokads", "tree": "tiktok", "family": "tiktok",
        "goals": ["awareness", "traffic", "engagement", "video_views", "lead_generation", "conversions",
                  "app_promotion"],
        "ctas": TIKTOK_CTAS, "media": ["video"],
        "targeting": _GEO + ["age", "gender", "languages", "interests", "behaviors", "income_tier"],
        "limits": {"body": 100}, "bid": False, "validate": False, "preview": False,
    },
    "linkedin": {
        "label": "LinkedIn", "ads_account": "linkedinads", "tree": "linkedin", "family": "linkedin",
        "goals": ["awareness", "traffic", "engagement", "video_views", "lead_generation"],
        "ctas": LINKEDIN_CTAS, "media": ["image", "video"],
        "targeting": _GEO + ["age", "gender", "languages", "interests", "behaviors"],
        "limits": {"headline": 400}, "bid": False, "validate": False, "preview": False,
    },
    "pinterest": {
        "label": "Pinterest", "ads_account": "pinterestads", "tree": "pinterest", "family": "pinterest",
        "goals": ["awareness", "traffic", "engagement", "video_views", "conversions"],
        "ctas": [], "media": ["image"],
        "targeting": _GEO + ["age", "gender", "languages", "interests"],
        "limits": {"headline": 100, "body": 500}, "bid": False, "validate": False, "preview": False,
    },
    "twitter": {
        # X: an image website card = image + headline (title, max 70) + link.
        "label": "X (Twitter)", "ads_account": "xads", "tree": "twitter", "family": "x",
        "goals": ["awareness", "traffic", "engagement"],
        "ctas": [], "media": ["image"],
        "targeting": _GEO + ["age", "gender", "languages", "interests"],
        "limits": {"headline": 70, "body": 280}, "bid": False, "validate": False, "preview": False,
    },
    "googleads": {
        # Display needs a landscape (1.91:1) + square (1:1) image; Search needs keywords, no media.
        "label": "Google Ads", "ads_account": "googleads", "tree": "google", "family": "google",
        "goals": ["awareness", "traffic", "conversions"],
        "ctas": [], "media": ["image"], "campaign_types": ["display", "search"],
        "targeting": _GEO + ["custom_locations", "excluded_locations", "age", "gender", "languages", "interests",
                             "income_tier", "keywords"],
        "limits": {"headline": 30, "long_headline": 90, "body": 90}, "bid": True, "validate": False, "preview": False,
    },
}
# Zernio's own platform name for each posting/ads account kind.
ADS_ACCOUNT_KINDS = {p["ads_account"] for p in PLATFORMS.values()}


# ---------------------------------------------------------------------------
# Profiles and accounts
# ---------------------------------------------------------------------------
def create_profile(name: str, timezone_name: str | None, idempotency_key: str) -> dict[str, Any]:
    body = call("POST", "/profiles", json=_clean({"name": name[:100], "timezone": timezone_name}),
                idempotency_key=idempotency_key)
    profile = body.get("profile") if isinstance(body, dict) else None
    return profile if isinstance(profile, dict) else {}


def list_accounts(profile_id: str) -> list[dict[str, Any]]:
    body = call("GET", "/accounts", params={"profileId": profile_id})
    rows = body.get("accounts") if isinstance(body, dict) else None
    return [a for a in rows if isinstance(a, dict)] if isinstance(rows, list) else []


def connect_ads(platform: str, profile_id: str, redirect_url: str, account_id: str | None = None) -> dict[str, Any]:
    """{alreadyConnected, accountId, authUrl, state}. Same-token platforms reuse
    the posting account's token; TikTok/X/Google run their own OAuth."""
    body = call("GET", f"/connect/{platform}/ads",
                params=_clean({"profileId": profile_id, "redirect_url": redirect_url, "accountId": account_id}))
    return body if isinstance(body, dict) else {}


def connect_posting(platform: str, profile_id: str, redirect_url: str) -> dict[str, Any]:
    """{authUrl, state}: the posting account X ads need first."""
    body = call("GET", f"/connect/{platform}", params={"profileId": profile_id, "redirect_url": redirect_url})
    return body if isinstance(body, dict) else {}


def disconnect(account_id: str) -> None:
    call("DELETE", f"/accounts/{quote(account_id, safe='')}")


def ad_accounts(account_id: str) -> list[dict[str, Any]]:
    body = call("GET", "/ads/accounts", params={"accountId": account_id})
    rows = body.get("accounts") if isinstance(body, dict) else None
    return [a for a in rows if isinstance(a, dict)] if isinstance(rows, list) else []


def tiktok_identities(account_id: str, ad_account_id: str) -> list[dict[str, Any]]:
    body = call("GET", "/ads/tiktok-identities", params={"accountId": account_id, "adAccountId": ad_account_id})
    rows = body.get("identities") if isinstance(body, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def meta_identities(account_id: str, ad_account_id: str) -> dict[str, Any]:
    body = call("GET", "/ads/instagram-accounts", params={"accountId": account_id, "adAccountId": ad_account_id})
    return body if isinstance(body, dict) else {}


def account_posts(account_id: str) -> list[dict[str, Any]]:
    body = call("GET", f"/accounts/{quote(account_id, safe='')}/posts")
    rows = body.get("posts") if isinstance(body, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


# ---------------------------------------------------------------------------
# Targeting and media
# ---------------------------------------------------------------------------
def targeting_search(account_id: str, q: str, dimension: str, geo_type: str | None, country: str | None,
                     ad_account_id: str | None) -> list[dict[str, Any]]:
    body = call("GET", "/ads/targeting/search", params=_clean({
        "accountId": account_id, "q": q, "dimension": dimension, "geoType": geo_type, "countryCode": country,
        "adAccountId": ad_account_id, "limit": 25}))
    rows = body.get("results") if isinstance(body, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def reach_estimate(account_id: str, ad_account_id: str, spec: dict[str, Any], optimization_goal: str | None) -> dict[str, Any]:
    body = call("POST", "/ads/targeting/reach-estimate", json=_clean({
        "accountId": account_id, "adAccountId": ad_account_id, "spec": spec, "optimizationGoal": optimization_goal}))
    return body if isinstance(body, dict) else {}


def upload_image_base64(account_id: str, ad_account_id: str, b64: str, filename: str) -> str:
    """Meta only: image bytes -> a Meta-hosted URL usable as imageUrl."""
    body = call("POST", "/ads/images", timeout=LONG_TIMEOUT,
                json={"accountId": account_id, "adAccountId": ad_account_id, "imageBase64": b64, "filename": filename})
    image = body.get("image") if isinstance(body, dict) else None
    url = image.get("url") if isinstance(image, dict) else None
    if not url:
        raise ZernioError("Zernio didn't return a URL for the uploaded image.")
    return str(url)


# ---------------------------------------------------------------------------
# Create, validate, preview, boost
# ---------------------------------------------------------------------------
def create_ad(payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    body = call("POST", "/ads/create", json=payload, timeout=LONG_TIMEOUT, idempotency_key=idempotency_key)
    return body if isinstance(body, dict) else {}


def validate_ad(payload: dict[str, Any]) -> dict[str, Any]:
    body = call("POST", "/ads/create", json={**payload, "validateOnly": True}, timeout=LONG_TIMEOUT)
    return body if isinstance(body, dict) else {}


def preview(account_id: str, ad_account_id: str, creative_spec: dict[str, Any], formats: list[str]) -> list[dict[str, Any]]:
    body = call("POST", "/ads/preview", json={"accountId": account_id, "adAccountId": ad_account_id,
                                              "creativeSpec": creative_spec, "formats": formats})
    rows = body.get("previews") if isinstance(body, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def boost(payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    body = call("POST", "/ads/boost", json=payload, timeout=LONG_TIMEOUT, idempotency_key=idempotency_key)
    return body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------
# Campaign tree and management
# ---------------------------------------------------------------------------
def tree(profile_id: str, **params: Any) -> dict[str, Any]:
    body = call("GET", "/ads/tree", params=_clean({"profileId": profile_id, **params}))
    return body if isinstance(body, dict) else {}


def set_campaign_status(campaign_id: str, platform: str, status: str) -> dict[str, Any]:
    body = call("PUT", f"/ads/campaigns/{quote(campaign_id, safe='')}/status", json={"status": status, "platform": platform})
    return body if isinstance(body, dict) else {}


def set_ad_set_status(ad_set_id: str, platform: str, status: str) -> dict[str, Any]:
    body = call("PUT", f"/ads/ad-sets/{quote(ad_set_id, safe='')}/status", json={"status": status, "platform": platform})
    return body if isinstance(body, dict) else {}


def set_ad_status(ad_id: str, status: str) -> dict[str, Any]:
    body = call("PUT", f"/ads/{quote(ad_id, safe='')}/status", json={"status": status})
    return body if isinstance(body, dict) else {}


def update_campaign(campaign_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = call("PUT", f"/ads/campaigns/{quote(campaign_id, safe='')}", json=payload)
    return body if isinstance(body, dict) else {}


def delete_campaign(campaign_id: str, platform: str) -> dict[str, Any]:
    body = call("DELETE", f"/ads/campaigns/{quote(campaign_id, safe='')}", json={"platform": platform})
    return body if isinstance(body, dict) else {}


def campaign_analytics(campaign_id: str, platform: str, start: str, end: str, breakdowns: str | None) -> tuple[int, dict[str, Any]]:
    """(status, body): 202 = Zernio is still backfilling results."""
    from app.integrations.base_adapter import http

    st = get_settings()
    key = st.ZERNIO_API_KEY.get_secret_value().strip()
    if not key:
        raise ZernioError("Zernio isn't set up on this server (ZERNIO_API_KEY is empty).", status_code=503)
    try:
        resp = http("GET", f"{st.ZERNIO_BASE_URL.rstrip('/')}/ads/campaigns/{quote(campaign_id, safe='')}/analytics",
                    headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=TIMEOUT,
                    params=_clean({"platform": platform, "fromDate": start, "toDate": end, "breakdowns": breakdowns}))
    except PlatformError as exc:
        raise ZernioError(exc.message.replace("The platform", "Zernio"), status_code=exc.status_code) from None
    if resp.status_code >= 400:
        raise _error(resp)
    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        raise ZernioError("Zernio returned an unreadable answer.") from None
    return resp.status_code, body if isinstance(body, dict) else {}
