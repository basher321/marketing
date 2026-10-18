"""Meta Graph / Marketing API client and mapping rules (SPEC-BE-054).

Every call to Meta goes through `MetaClient`: httpx, a 20 s timeout, an
`appsecret_proof` on every call when the app secret is configured, and no
secret ever logged. `client_factory` is swappable in tests
(httpx.MockTransport), so no real Meta call is made there.

The mapping from our campaign model to Meta's objects is kept in pure
functions below so each rule is documented and testable on its own.
"""
import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from app.config import get_settings
from app.utils import locale_data


def _app(group: str, field: str) -> str:
    """A software credential (SPEC-BE-101): the Super admin's screen first, then backend/.env."""
    from app.services import platform_service

    return platform_service.value(group, field)

logger = structlog.get_logger(__name__)

# httpx logs every request URL at INFO ("HTTP Request: GET ...?access_token=...").
# Graph GET calls carry the access token (and, for the code exchange, the app
# secret) in the query string, so that line would leak secrets into the logs.
# Raised to WARNING process-wide; this also covers verify.py's provider tests.
logging.getLogger("httpx").setLevel(logging.WARNING)

TIMEOUT_S = 20.0


def _default_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=False)


client_factory: Callable[[], httpx.Client] = _default_client


class MetaError(Exception):
    """A failed Meta call. `message` is Meta's user-facing text when it gives one."""

    def __init__(
        self,
        message: str,
        code: int | None = None,
        status: int | None = None,
        subcode: int | None = None,
        blame_fields: list[str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.subcode = subcode
        # Meta's error_data.blame_field_specs, flattened ("targeting.geo_locations").
        self.blame_fields = blame_fields or []

    @property
    def expired(self) -> bool:
        # Graph error code 190 = invalid or expired access token.
        return self.code == 190


def _short(text: object) -> str:
    return " ".join(str(text).split())[:300]


def graph_base() -> str:
    return f"https://graph.facebook.com/{get_settings().META_GRAPH_VERSION}"


def app_configured() -> bool:
    get_settings()
    return bool(_app("meta_app", "app_id") and _app("meta_app", "app_secret") and _app("meta_app", "login_config_id"))


def login_url(redirect_uri: str, state: str) -> str:
    """Facebook Login for Business dialog; the configuration (config_id) decides
    the token type (business integration system user), assets and permissions."""
    s = get_settings()
    query = urlencode(
        {
            "client_id": _app("meta_app", "app_id"),
            "config_id": _app("meta_app", "login_config_id"),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "override_default_response_type": "true",
            "state": state,
        }
    )
    return f"https://www.facebook.com/{s.META_GRAPH_VERSION}/dialog/oauth?{query}"


def _error_from(resp: httpx.Response) -> MetaError:
    try:
        body = resp.json()
    except ValueError:
        return MetaError(_short(resp.text) or f"HTTP {resp.status_code}", status=resp.status_code)
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        message = err.get("error_user_msg") or err.get("message") or "Meta returned an error."
        code = err.get("code")
        subcode = err.get("error_subcode")
        blame: list[str] = []
        data = err.get("error_data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                data = None
        if isinstance(data, dict):
            for spec in data.get("blame_field_specs") or []:
                blame.append(".".join(str(p) for p in spec) if isinstance(spec, list) else str(spec))
        return MetaError(
            _short(message),
            code=code if isinstance(code, int) else None,
            status=resp.status_code,
            subcode=subcode if isinstance(subcode, int) else None,
            blame_fields=blame,
        )
    return MetaError(_short(body), status=resp.status_code)


def _send(
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        with client_factory() as client:
            resp = client.request(method, url, params=params, data=data, files=files)
    except httpx.TimeoutException:
        raise MetaError("Meta didn't answer within 20 seconds; try again.") from None
    except httpx.HTTPError as exc:
        raise MetaError(f"Couldn't reach Meta ({type(exc).__name__}).") from None
    if resp.status_code >= 400:
        raise _error_from(resp)
    try:
        body = resp.json()
    except ValueError:
        raise MetaError("Unexpected response from Meta.") from None
    return body if isinstance(body, dict) else {"data": body}


def exchange_code(code: str, redirect_uri: str) -> str:
    """Server-to-server code exchange -> business integration system user token."""
    get_settings()
    body = _send(
        "GET",
        f"{graph_base()}/oauth/access_token",
        params={
            "client_id": _app("meta_app", "app_id"),
            "client_secret": _app("meta_app", "app_secret"),
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise MetaError("Meta didn't return an access token.")
    return token


def _form(values: dict[str, Any]) -> dict[str, str]:
    # Graph takes form fields; nested values (targeting, object_story_spec...) are JSON.
    return {
        k: json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)
        for k, v in values.items()
        if v is not None
    }


class MetaClient:
    def __init__(self, access_token: str):
        self._token = access_token

    def _auth(self) -> dict[str, str]:
        auth = {"access_token": self._token}
        secret = _app("meta_app", "app_secret")
        if secret:
            # appsecret_proof = HMAC-SHA256(access_token, app_secret).
            auth["appsecret_proof"] = hmac.new(
                secret.encode(), self._token.encode(), hashlib.sha256
            ).hexdigest()
        return auth

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        return _send("GET", f"{graph_base()}/{path}", params={**_form(params), **self._auth()})

    def post(self, path: str, values: dict[str, Any]) -> dict[str, Any]:
        return _send("POST", f"{graph_base()}/{path}", data={**_form(values), **self._auth()})

    def delete(self, object_id: str) -> None:
        _send("DELETE", f"{graph_base()}/{object_id}", params=self._auth())

    # --- assets the token can reach (system users are user-like nodes: /me/...) ---
    def list_ad_accounts(self) -> list[dict[str, Any]]:
        body = self.get("me/adaccounts", fields="id,account_id,name,currency,account_status", limit=100)
        return list(body.get("data") or [])

    def list_pages(self) -> list[dict[str, Any]]:
        body = self.get("me/accounts", fields="id,name,instagram_business_account{id,username}", limit=100)
        return list(body.get("data") or [])

    def list_pixels(self, ad_account_id: str) -> list[dict[str, Any]]:
        body = self.get(f"act_{ad_account_id}/adspixels", fields="id,name", limit=100)
        return list(body.get("data") or [])

    def get_ad_account(self, ad_account_id: str) -> dict[str, Any]:
        return self.get(f"act_{ad_account_id}", fields="name,currency,account_status")

    def search(self, kind: str, query: str, **extra: Any) -> list[dict[str, Any]]:
        body = self.get("search", type=kind, q=query, limit=25, **extra)
        return list(body.get("data") or [])

    # --- publishing ---
    def create(self, ad_account_id: str, edge: str, values: dict[str, Any]) -> str:
        body = self.post(f"act_{ad_account_id}/{edge}", values)
        object_id = body.get("id")
        if not object_id:
            raise MetaError(f"Meta didn't return an id for the new {edge[:-1]}.")
        return str(object_id)

    def set_status(self, object_id: str, status: str) -> None:
        self.post(object_id, {"status": status})

    # --- builder (SPEC-BE-055) ---
    def validate_only(self, ad_account_id: str, edge: str, values: dict[str, Any]) -> None:
        """Meta-side validation without creating anything (execution_options)."""
        self.post(f"act_{ad_account_id}/{edge}", {**values, "execution_options": ["validate_only"]})

    def previews(self, ad_account_id: str, creative: dict[str, Any], ad_format: str) -> list[dict[str, Any]]:
        body = self.get(f"act_{ad_account_id}/generatepreviews", creative=creative, ad_format=ad_format)
        return list(body.get("data") or [])

    def upload_image(self, ad_account_id: str, filename: str, content: bytes) -> dict[str, Any]:
        body = _send(
            "POST",
            f"{graph_base()}/act_{ad_account_id}/adimages",
            data=self._auth(),
            files={"filename": (filename, content)},
        )
        images = body.get("images") or {}
        first = next(iter(images.values()), None) if isinstance(images, dict) else None
        if not first or not first.get("hash"):
            raise MetaError("Meta didn't return an image hash.")
        return {"image_hash": first["hash"], "url": first.get("url")}

    def upload_video(self, ad_account_id: str, filename: str, content: bytes) -> str:
        body = _send(
            "POST",
            f"{graph_base()}/act_{ad_account_id}/advideos",
            data={**self._auth(), "name": filename},
            files={"source": (filename, content)},
        )
        if not body.get("id"):
            raise MetaError("Meta didn't return a video id.")
        return str(body["id"])

    def video_status(self, video_id: str) -> dict[str, Any]:
        body = self.get(video_id, fields="status,picture")
        status = ((body.get("status") or {}).get("video_status")) or "processing"
        return {"status": status, "thumbnail_url": body.get("picture")}

    def custom_audiences(self, ad_account_id: str) -> list[dict[str, Any]]:
        body = self.get(
            f"act_{ad_account_id}/customaudiences",
            fields="id,name,subtype,approximate_count_lower_bound,approximate_count_upper_bound",
            limit=200,
        )
        return list(body.get("data") or [])

    def advertisable_apps(self, ad_account_id: str) -> list[dict[str, Any]]:
        body = self.get(f"act_{ad_account_id}/advertisable_applications", fields="id,name,object_store_urls", limit=50)
        return list(body.get("data") or [])

    def lead_forms(self, page_id: str) -> list[dict[str, Any]]:
        body = self.get(f"{page_id}/leadgen_forms", fields="id,name,status", limit=100)
        return list(body.get("data") or [])

    # --- ad setup (SPEC-BE-082) ---
    def product_sets(self, ad_account_id: str) -> list[dict[str, Any]]:
        """Product sets of every catalog the ad account's business owns or has client access to."""
        business = (self.get(f"act_{ad_account_id}", fields="business").get("business") or {}).get("id")
        if not business:
            return []
        catalogs: dict[str, str] = {}
        for edge in ("owned_product_catalogs", "client_product_catalogs"):
            for cat in self.get(f"{business}/{edge}", fields="id,name", limit=100).get("data") or []:
                catalogs[str(cat["id"])] = str(cat.get("name") or "")
        out = []
        for catalog_id, catalog_name in catalogs.items():
            for row in self.get(f"{catalog_id}/product_sets", fields="id,name,product_count", limit=100).get("data") or []:
                out.append({**row, "catalog_id": catalog_id, "catalog_name": catalog_name})
        return out

    def page_token(self, page_id: str) -> str:
        """The Page token the system user holds for this Page (used per call, never stored)."""
        token = self.get(page_id, fields="access_token").get("access_token")
        if not token:
            raise MetaError("Meta didn't return a Page token; check that the system user has this Page assigned.")
        return str(token)

    def page_posts(self, page_id: str, after: str | None = None) -> dict[str, Any]:
        page = MetaClient(self.page_token(page_id))
        params: dict[str, Any] = {"fields": "id,message,full_picture,permalink_url,created_time", "limit": 25}
        if after:
            params["after"] = after
        return page.get(f"{page_id}/published_posts", **params)

    def instagram_posts(self, instagram_id: str, after: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp", "limit": 25}
        if after:
            params["after"] = after
        return self.get(f"{instagram_id}/media", **params)

    def create_page_post(self, page_id: str, message: str, link: str | None, image_url: str | None) -> str:
        """Publishes a post on the Page and returns its {page_id}_{post_id}."""
        page = MetaClient(self.page_token(page_id))
        if image_url:
            body = page.post(f"{page_id}/photos", {"url": image_url, "caption": message, "published": True})
            post_id = body.get("post_id") or (f"{page_id}_{body['id']}" if body.get("id") else None)
        else:
            body = page.post(f"{page_id}/feed", {"message": message, "link": link, "published": True})
            post_id = body.get("id")
        if not post_id:
            raise MetaError("Meta didn't return an id for the new post.")
        return str(post_id)

    def delivery_estimate(self, ad_account_id: str, targeting: dict[str, Any], goal: str) -> dict[str, Any]:
        body = self.get(f"act_{ad_account_id}/delivery_estimate", targeting_spec=targeting, optimization_goal=goal)
        data = body.get("data") or []
        return data[0] if data else {}

    def get_many(self, ids: list[str], fields: str) -> dict[str, Any]:
        if not ids:
            return {}
        return self.get("", ids=",".join(ids), fields=fields)


# ---------------------------------------------------------------------------
# Mapping rules (SPEC-BE-054)
# ---------------------------------------------------------------------------
# Only these channels publish to Meta, as publisher_platforms. Other channels
# (tiktok, whatsapp, email, sms, web) stay internal-only.
META_PLATFORMS = {"facebook": "facebook", "instagram": "instagram", "messenger": "messenger"}

# Our objective -> (Meta outcome objective, ad set optimization goal).
# message_replies is not supported in v1 (needs a Messenger/WhatsApp destination).
OBJECTIVES: dict[str, tuple[str, str]] = {
    "awareness": ("OUTCOME_AWARENESS", "IMPRESSIONS"),
    "reach": ("OUTCOME_AWARENESS", "REACH"),
    "traffic": ("OUTCOME_TRAFFIC", "LINK_CLICKS"),
    "engagement": ("OUTCOME_ENGAGEMENT", "POST_ENGAGEMENT"),
    "conversions": ("OUTCOME_SALES", "OFFSITE_CONVERSIONS"),
}

# Meta "offset 1" currencies (amounts in whole units, no cents), from Meta's
# currency table (checked 2026-10-01). Every other currency is offset 100, the
# same minor units as our *_cents columns.
OFFSET_1_CURRENCIES = frozenset(
    {"CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND"}
)

# Meta accepts ages 18-65 for these ads; the audience range is clamped to it.
MIN_AGE, MAX_AGE = 18, 65

# Graph account_status values other than 1 (active), as plain words.
ACCOUNT_STATUS = {
    2: "disabled",
    3: "unsettled (a payment is due)",
    7: "pending risk review",
    8: "pending settlement",
    9: "in a grace period",
    100: "pending closure",
    101: "closed",
}

# ISO 639-1 codes whose name in Meta's locale search differs from CLDR's English
# name (CLDR says "Bangla"; Meta says "Bengali"), kept from the original curated
# list. Every other language uses CLDR's English name (SPEC-BE-072), then the code.
LANGUAGE_NAMES = {
    "ar": "Arabic", "bn": "Bengali", "de": "German", "en": "English", "es": "Spanish",
    "fr": "French", "hi": "Hindi", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "ms": "Malay", "nl": "Dutch", "pt": "Portuguese", "ru": "Russian",
    "ta": "Tamil", "th": "Thai", "tr": "Turkish", "ur": "Urdu", "vi": "Vietnamese",
    "zh": "Chinese",
}


def language_label(code: str) -> str:
    """The name to search Meta's ad locales with ("sw" -> "Swahili", "bn" -> "Bengali")."""
    key = code.lower()
    return LANGUAGE_NAMES.get(key) or locale_data.language_name(key) or code


def meta_platforms(channels: list[str]) -> list[str]:
    return [META_PLATFORMS[c] for c in channels if c in META_PLATFORMS]


def to_meta_amount(cents: int, currency: str) -> int:
    """Our integer cents -> Meta's minor units for the ad account currency."""
    if currency.upper() in OFFSET_1_CURRENCIES:
        return int((Decimal(cents) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int(cents)


def ads_manager_url(ad_account_id: str, campaign_id: str) -> str:
    return (
        "https://adsmanager.facebook.com/adsmanager/manage/campaigns"
        f"?act={ad_account_id}&selected_campaign_ids={campaign_id}"
    )


def base_targeting(targeting: dict[str, Any], platforms: list[str]) -> dict[str, Any]:
    """The parts of an audience that need no Meta lookup: countries, age and
    gender (male -> 1, female -> 2, all -> omitted), plus placements."""
    age_min = max(MIN_AGE, min(MAX_AGE, int(targeting.get("age_min") or MIN_AGE)))
    age_max = max(age_min, min(MAX_AGE, int(targeting.get("age_max") or MAX_AGE)))
    spec: dict[str, Any] = {
        "geo_locations": {"countries": [c.upper() for c in targeting.get("countries") or []]},
        "age_min": age_min,
        "age_max": age_max,
        "publisher_platforms": platforms,
    }
    genders = targeting.get("genders") or []
    if len(genders) == 1:
        spec["genders"] = [1] if genders[0] == "male" else [2]
    return spec


# ---------------------------------------------------------------------------
# Builder rules (SPEC-BE-055). The one place to update when Meta changes.
# ---------------------------------------------------------------------------
# UI objective -> our campaigns.objective value -> Meta outcome objective.
# "Sales" is stored as our existing `conversions`; awareness also covers `reach`.
BUILDER_OBJECTIVES: dict[str, dict[str, Any]] = {
    "awareness": {
        "label": "Awareness", "stored": "awareness", "meta": "OUTCOME_AWARENESS",
        "description": "Show your ads to people who are most likely to remember them.",
        "locations": {"none": ["REACH", "IMPRESSIONS", "AD_RECALL_LIFT", "THRUPLAY"]},
    },
    "traffic": {
        "label": "Traffic", "stored": "traffic", "meta": "OUTCOME_TRAFFIC",
        "description": "Send people to a destination, like your website or app.",
        "locations": {
            "website": ["LINK_CLICKS", "LANDING_PAGE_VIEWS", "REACH", "IMPRESSIONS"],
            "app": ["LINK_CLICKS", "REACH"],
        },
    },
    "engagement": {
        "label": "Engagement", "stored": "engagement", "meta": "OUTCOME_ENGAGEMENT",
        "description": "Get more messages, video views, post engagement or Page likes.",
        "locations": {"on_ad": ["POST_ENGAGEMENT", "IMPRESSIONS", "REACH"], "video": ["THRUPLAY"], "page": ["PAGE_LIKES"]},
    },
    "leads": {
        "label": "Leads", "stored": "leads", "meta": "OUTCOME_LEADS",
        "description": "Collect leads for your business or brand.",
        "locations": {"website": ["OFFSITE_CONVERSIONS"], "instant_form": ["LEAD_GENERATION", "QUALITY_LEAD"]},
    },
    "app_promotion": {
        "label": "App promotion", "stored": "app_promotion", "meta": "OUTCOME_APP_PROMOTION",
        "description": "Find new people to install your app and continue using it.",
        "locations": {"app": ["APP_INSTALLS", "LINK_CLICKS", "OFFSITE_CONVERSIONS"]},
    },
    "sales": {
        "label": "Sales", "stored": "conversions", "meta": "OUTCOME_SALES",
        "description": "Find people likely to purchase your product or service.",
        "locations": {"website": ["OFFSITE_CONVERSIONS", "VALUE", "LINK_CLICKS", "LANDING_PAGE_VIEWS"], "app": ["OFFSITE_CONVERSIONS", "LINK_CLICKS"]},
    },
}
# Destinations not offered (SPEC-BE-054 decision 3), listed with the reason.
UNAVAILABLE_LOCATIONS = {"messenger": "Messenger destinations aren't supported yet.", "whatsapp": "WhatsApp destinations aren't supported yet."}
STORED_TO_BUILDER = {"awareness": "awareness", "reach": "awareness", "traffic": "traffic", "engagement": "engagement",
                     "leads": "leads", "app_promotion": "app_promotion", "conversions": "sales"}
# Ad set destination_type per conversion location.
DESTINATION_TYPES = {"website": "WEBSITE", "app": "APP", "instant_form": "ON_AD", "on_ad": "ON_POST", "video": "ON_VIDEO", "page": "ON_PAGE"}
BID_STRATEGIES = ("LOWEST_COST_WITHOUT_CAP", "LOWEST_COST_WITH_BID_CAP", "COST_CAP", "LOWEST_COST_WITH_MIN_ROAS")
SPECIAL_AD_CATEGORIES = ("HOUSING", "EMPLOYMENT", "FINANCIAL_PRODUCTS_SERVICES", "ISSUES_ELECTIONS_POLITICS")
PLACEMENT_POSITIONS = {
    "facebook": ["feed", "right_hand_column", "marketplace", "video_feeds", "story", "search", "instream_video", "facebook_reels"],
    "instagram": ["stream", "story", "explore", "explore_home", "reels", "profile_feed", "ig_search"],
    "messenger": ["messenger_home", "story"],
    "audience_network": ["classic", "rewarded_video"],
}
PREVIEW_FORMATS = ("DESKTOP_FEED_STANDARD", "MOBILE_FEED_STANDARD", "INSTAGRAM_STANDARD", "INSTAGRAM_STORY", "FACEBOOK_STORY_MOBILE", "INSTAGRAM_REELS")
CALLS_TO_ACTION = ("SHOP_NOW", "LEARN_MORE", "SIGN_UP", "ORDER_NOW", "CONTACT_US", "BOOK_NOW", "GET_OFFER",
                   "DOWNLOAD", "INSTALL_MOBILE_APP", "USE_APP", "SUBSCRIBE", "APPLY_NOW", "GET_QUOTE", "WATCH_MORE")
EVENT_TYPES = ("PURCHASE", "LEAD", "COMPLETE_REGISTRATION", "ADD_TO_CART", "INITIATED_CHECKOUT", "CONTENT_VIEW", "SEARCH", "ADD_PAYMENT_INFO", "SUBSCRIBE", "CONTACT")


def classify(exc: MetaError) -> tuple[str, int, str]:
    """Meta error -> (class, HTTP status for us, user message) (SPEC-BE-055 rule 9)."""
    code = exc.code or 0
    if exc.expired:
        return "auth", 409, "Reconnect Meta in Integrations; Meta rejected the saved access."
    if code in (4, 17, 32, 613) or 80000 <= code <= 80014:
        return "rate_limit", 503, "Meta is rate-limiting this ad account; try again in a few minutes."
    if code in (10, 294) or 200 <= code <= 299:
        return "permission", 403, f"Your Meta connection lacks a permission for this: {exc.message}"
    if exc.status and exc.status >= 500 or exc.status is None:
        return "meta_unavailable", 502, f"Meta: {exc.message}"
    if code == 100 and exc.blame_fields:
        return "validation", 422, f"Meta: {exc.message}"
    if code == 100:
        return "unsupported", 422, f"Meta: {exc.message}"
    return "validation", 422, f"Meta: {exc.message}"


# Meta effective_status -> our campaign_status (SPEC-BE-056 status sync).
def our_status(effective: str, current: str) -> str:
    if effective == "ACTIVE":
        return "running" if current != "scheduled" else current
    if effective in ("PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED"):
        return "paused"
    if effective in ("DELETED", "ARCHIVED"):
        return "completed"
    return current


# ---------------------------------------------------------------------------
# Insights (SPEC-BE-056)
# ---------------------------------------------------------------------------
INSIGHT_FIELDS = (
    "ad_id,spend,impressions,reach,clicks,inline_link_clicks,actions,action_values,"
    "video_thruplay_watched_actions,date_start"
)


def insights(client: "MetaClient", campaign_id: str, since: str, until: str) -> list[dict[str, Any]]:
    """Daily per-ad rows for one campaign, following Meta's `after` cursors."""
    rows: list[dict[str, Any]] = []
    after: str | None = None
    for _page in range(50):
        params: dict[str, Any] = {
            "level": "ad",
            "time_increment": 1,
            "time_range": {"since": since, "until": until},
            "fields": INSIGHT_FIELDS,
            "limit": 500,
        }
        if after:
            params["after"] = after
        body = client.get(f"{campaign_id}/insights", **params)
        rows.extend(body.get("data") or [])
        cursors = ((body.get("paging") or {}).get("cursors") or {})
        after = cursors.get("after") if (body.get("paging") or {}).get("next") else None
        if not after:
            break
    return rows


def _action_sum(items: Any, preferred: tuple[str, ...]) -> Decimal | None:
    # The first action_type present wins, so e.g. 'purchase' (all sources) and
    # 'offsite_conversion.fb_pixel_purchase' (pixel) are never double counted.
    if not isinstance(items, list):
        return None
    by_type = {str(i.get("action_type")): i.get("value") for i in items if isinstance(i, dict)}
    for kind in preferred:
        if kind in by_type and by_type[kind] is not None:
            return Decimal(str(by_type[kind]))
    return None


def insight_metrics(row: dict[str, Any]) -> dict[str, Decimal]:
    """One Meta insights row -> our metric names (SPEC-BE-056 contract).
    Money is in our cents (Meta reports spend in major units for every
    currency); action metrics Meta didn't report are left out, never 0."""
    out: dict[str, Decimal] = {}
    if row.get("spend") is not None:
        out["spend_cents"] = (Decimal(str(row["spend"])) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    for ours, theirs in (("impressions", "impressions"), ("reach", "reach"), ("clicks", "clicks"), ("link_clicks", "inline_link_clicks")):
        if row.get(theirs) is not None:
            out[ours] = Decimal(str(row[theirs]))
    actions, values = row.get("actions"), row.get("action_values")
    purchases = _action_sum(actions, ("purchase", "offsite_conversion.fb_pixel_purchase"))
    if purchases is not None:
        out["purchases"] = purchases
    value = _action_sum(values, ("purchase", "offsite_conversion.fb_pixel_purchase"))
    if value is not None:
        out["purchase_value_cents"] = (value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    for ours, kinds in (("leads", ("lead", "onsite_conversion.lead_grouped")), ("app_installs", ("mobile_app_install",)), ("post_engagement", ("post_engagement",))):
        found = _action_sum(actions, kinds)
        if found is not None:
            out[ours] = found
    thru = _action_sum(row.get("video_thruplay_watched_actions"), ("video_view",))
    if thru is not None:
        out["video_thruplays"] = thru
    return out
