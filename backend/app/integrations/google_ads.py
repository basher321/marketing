"""Google Ads adapter (SPEC-BE-064), also used for YouTube ads (registry key
`youtube`, published as Demand Gen video campaigns).

REST, not the gRPC client library (no new dependency). Auth: an OAuth access
token refreshed from the stored refresh token (cached in memory until it
expires) + the developer token header (+ login-customer-id for a manager
account). Money is in micros. A publish is ONE googleAds:mutate with
temporary resource names and partialFailure=false, which Google applies
atomically: a failure creates nothing. The campaign is created PAUSED and
enabled by a second mutate; if that fails, the campaign is removed.
"""
import base64
import re
import time
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal
from typing import Any

from app.config import get_settings
from app.integrations.base_adapter import PlatformError, entries, http, ids, issue, micros, short, unresolved

TOKEN_URL = "https://oauth2.googleapis.com/token"
_tokens: dict[str, tuple[str, float]] = {}

CHANNEL = {"SEARCH": "SEARCH", "PERFORMANCE_MAX": "PERFORMANCE_MAX", "DISPLAY": "DISPLAY", "DEMAND_GEN": "DEMAND_GEN"}
# YouTube ad format -> Demand Gen channel control.
YT_CHANNEL = {"skippable_in_stream": "youtubeInStream", "in_feed": "youtubeInFeed", "shorts": "youtubeShorts"}
YT_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")


def _base() -> str:
    return f"https://googleads.googleapis.com/{get_settings().GOOGLE_ADS_API_VERSION}"


def _cid(fields: dict[str, Any]) -> str:
    return re.sub(r"\D", "", str(fields.get("customer_id", "")))


def _error(resp: Any) -> PlatformError:
    try:
        err = resp.json().get("error") or {}
    except ValueError:
        return PlatformError(f"Google Ads answered HTTP {resp.status_code}.", 502)
    message = err.get("message") or ""
    path = None
    for detail in err.get("details") or []:
        for e in detail.get("errors") or []:
            message = e.get("message") or message
            fields = [p.get("fieldName", "") + (f"[{p['index']}]" if "index" in p else "") for p in (e.get("location") or {}).get("fieldPathElements") or []]
            path = ".".join(fields) or None
            break
    auth = resp.status_code == 401 or err.get("status") == "UNAUTHENTICATED"
    return PlatformError(f"Google Ads: {short(message or err)}", 409 if auth else 502, path=path, auth=auth)


def _access_token(fields: dict[str, Any]) -> str:
    key = f"{fields.get('client_id')}:{str(fields.get('refresh_token', ''))[-12:]}"
    cached = _tokens.get(key)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    resp = http("POST", TOKEN_URL, data={"grant_type": "refresh_token", "client_id": fields.get("client_id"),
                                         "client_secret": fields.get("client_secret"), "refresh_token": fields.get("refresh_token")})
    body = resp.json() if resp.content else {}
    if resp.status_code >= 400 or "access_token" not in body:
        raise PlatformError(f"Google sign-in failed: {short(body.get('error_description') or body.get('error') or resp.status_code)}", 409, auth=True)
    _tokens[key] = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
    return str(body["access_token"])


def _headers(fields: dict[str, Any]) -> dict[str, str]:
    h = {"Authorization": f"Bearer {_access_token(fields)}", "developer-token": str(fields.get("developer_token", ""))}
    login = re.sub(r"\D", "", str(fields.get("login_customer_id") or ""))
    if login:
        h["login-customer-id"] = login
    return h


def _search(fields: dict[str, Any], query: str) -> list[dict[str, Any]]:
    resp = http("POST", f"{_base()}/customers/{_cid(fields)}/googleAds:searchStream", headers=_headers(fields), json={"query": query})
    if resp.status_code >= 400:
        raise _error(resp)
    body = resp.json()
    batches = body if isinstance(body, list) else [body]
    return [r for b in batches for r in (b.get("results") or [])]


def _mutate(fields: dict[str, Any], operations: list[dict[str, Any]], validate_only: bool = False) -> list[dict[str, Any]]:
    resp = http("POST", f"{_base()}/customers/{_cid(fields)}/googleAds:mutate", headers=_headers(fields),
                json={"mutateOperations": operations, "partialFailure": False, "validateOnly": validate_only})
    if resp.status_code >= 400:
        raise _error(resp)
    return list(resp.json().get("mutateOperationResponses") or [])


def verify_account(fields: dict[str, str]) -> dict[str, Any]:
    rows = _search(fields, "SELECT customer.descriptive_name, customer.currency_code, customer.time_zone FROM customer LIMIT 1")
    if not rows:
        raise PlatformError("Google Ads returned no customer for that ID.", 404)
    cust = rows[0].get("customer") or {}
    return {"name": cust.get("descriptiveName"), "currency": cust.get("currencyCode"), "timezone": cust.get("timeZone")}


# ---------------------------------------------------------------------------
# Building the mutate operations
# ---------------------------------------------------------------------------
def youtube_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    found = YT_ID.search(text)
    return found.group(1) if found else None


def _daily_micros(mode: str, amount: float | None, start: str | None, end: str | None) -> int | None:
    """Google budgets are daily: a total budget is spread evenly over the days."""
    if not amount or mode == "none":
        return None
    if mode == "daily":
        return micros(amount)
    days = 1
    if start and end:
        delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
        days = max(1, int((Decimal(delta.total_seconds()) / 86400).to_integral_value(rounding=ROUND_CEILING)))
    return micros(Decimal(str(amount)) / days)


def _bidding(c: dict[str, Any]) -> dict[str, Any]:
    f = c["fields"]
    bidding = f.get("bidding") or ("MAXIMIZE_CLICKS" if c.get("campaign_type") == "SEARCH" else "MAXIMIZE_CONVERSIONS")
    if bidding == "MAXIMIZE_CONVERSIONS":
        return {"maximizeConversions": {"targetCpaMicros": str(micros(f["target_cpa"]))} if f.get("target_cpa") else {}}
    if bidding == "MAXIMIZE_CONVERSION_VALUE":
        return {"maximizeConversionValue": {"targetRoas": float(f["target_roas"]) / 100} if f.get("target_roas") else {}}
    if bidding == "TARGET_IMPRESSION_SHARE":
        return {"targetImpressionShare": {"location": "ANYWHERE_ON_PAGE", "locationFractionMicros": "500000"}}
    return {"targetSpend": {}}  # Maximize clicks


class _Temp:
    def __init__(self, cid: str) -> None:
        self.cid, self.n = cid, 0

    def __call__(self, kind: str) -> str:
        self.n -= 1
        return f"customers/{self.cid}/{kind}/{self.n}"


def _text_assets(values: list[str]) -> list[dict[str, str]]:
    return [{"text": v} for v in values if isinstance(v, str) and v.strip()]


def _lst(cr: dict[str, Any], key: str) -> list[str]:
    v = cr.get(key)
    return [x for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else ([v] if isinstance(v, str) and v.strip() else [])


def build_operations(fields: dict[str, Any], tree: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """-> (mutate operations, index map {"campaign": i, "groups": {row: i}, "ads": {row: i}})."""
    cid = _cid(fields)
    tmp = _Temp(cid)
    c = tree["campaign"]
    youtube = tree["platform"] == "youtube"
    ctype = "DEMAND_GEN" if youtube else c.get("campaign_type") or "SEARCH"
    ops: list[dict[str, Any]] = []
    index: dict[str, Any] = {"groups": {}, "ads": {}}
    budget = tmp("campaignBudgets")
    groups = tree["groups"]
    daily = _daily_micros(c["budget_mode"], c["budget"], c.get("starts_at"), c.get("ends_at"))
    if daily is None:  # budget set per ad group: Google needs one campaign budget, so sum them
        daily = sum(_daily_micros(g["budget_mode"], g["budget"], g.get("starts_at") or c.get("starts_at"), g.get("ends_at") or c.get("ends_at")) or 0 for g in groups)
    ops.append({"campaignBudgetOperation": {"create": {"resourceName": budget, "name": f"{c['name']} budget {datetime.now(timezone.utc):%Y%m%d%H%M%S}",
                                                        "amountMicros": str(daily), "deliveryMethod": "STANDARD", "explicitlyShared": False}}})
    campaign = tmp("campaigns")
    body: dict[str, Any] = {"resourceName": campaign, "name": c["name"], "status": "PAUSED", "advertisingChannelType": CHANNEL.get(ctype, ctype),
                            "campaignBudget": budget, **_bidding(c)}
    if ctype == "SEARCH":
        body["networkSettings"] = {"targetGoogleSearch": True, "targetSearchNetwork": bool(c["fields"].get("search_partners")),
                                   "targetContentNetwork": bool(c["fields"].get("display_network"))}
    if c.get("starts_at"):
        body["startDate"] = c["starts_at"][:10]
    if c.get("ends_at"):
        body["endDate"] = c["ends_at"][:10]
    index["campaign"] = len(ops)
    ops.append({"campaignOperation": {"create": body}})
    # Google targets locations/languages per campaign: the union of the ad groups'.
    seen: set[tuple[str, str]] = set()
    for key, criterion in (("locations", "location"), ("languages", "language")):
        for g in groups:
            for value in ids(g["targeting"], key):
                if (key, value) in seen:
                    continue
                seen.add((key, value))
                const = f"geoTargetConstants/{value}" if key == "locations" else f"languageConstants/{value}"
                ops.append({"campaignCriterionOperation": {"create": {"campaign": campaign, criterion: {"geoTargetConstant" if key == "locations" else "languageConstant": const}}}})
    for g in groups:
        for e in entries(g["targeting"], "negative_keywords"):
            ops.append({"campaignCriterionOperation": {"create": {"campaign": campaign, "negative": True,
                                                                   "keyword": {"text": e["name"], "matchType": e.get("match") or "BROAD"}}}})
    if ctype == "PERFORMANCE_MAX":
        _pmax(ops, tmp, campaign, tree, index)
        return ops, index
    for g in groups:
        group = tmp("adGroups")
        gbody: dict[str, Any] = {"resourceName": group, "campaign": campaign, "name": g["name"], "status": "ENABLED"}
        if ctype == "SEARCH":
            gbody["type"] = "SEARCH_STANDARD"
        elif ctype == "DISPLAY":
            gbody["type"] = "DISPLAY_STANDARD"
        if g["fields"].get("default_cpc"):
            gbody["cpcBidMicros"] = str(micros(g["fields"]["default_cpc"]))
        if youtube:
            chosen = {YT_CHANNEL[a["creative"].get("format")] for a in g["ads"] if a["creative"].get("format") in YT_CHANNEL}
            gbody["demandGenAdGroupSettings"] = {"channelControls": {"selectedChannels": {ch: ch in chosen for ch in YT_CHANNEL.values()}}}
        index["groups"][g["id"]] = len(ops)
        ops.append({"adGroupOperation": {"create": gbody}})
        for e in entries(g["targeting"], "keywords"):
            ops.append({"adGroupCriterionOperation": {"create": {"adGroup": group, "status": "ENABLED",
                                                                  "keyword": {"text": e["name"], "matchType": e.get("match") or "BROAD"}}}})
        for value in ids(g["targeting"], "audiences"):
            ops.append({"adGroupCriterionOperation": {"create": {"adGroup": group, "userList": {"userList": f"customers/{_cid(fields)}/userLists/{value}"}}}})
        if youtube:
            for value in ids(g["targeting"], "topics"):
                ops.append({"adGroupCriterionOperation": {"create": {"adGroup": group, "topic": {"topicConstant": f"topicConstants/{value}"}}}})
        for ad in g["ads"]:
            cr = ad["creative"]
            ad_body: dict[str, Any] = {"name": ad["name"], "finalUrls": [cr["destination_url"]] if cr.get("destination_url") else []}
            images = [{"asset": m["media_id"]} for m in cr.get("media") or [] if m.get("kind") == "image"]
            if ctype == "SEARCH":
                ad_body["responsiveSearchAd"] = {"headlines": _text_assets(_lst(cr, "headlines")), "descriptions": _text_assets(_lst(cr, "descriptions")),
                                                 **({"path1": cr["path1"]} if cr.get("path1") else {}), **({"path2": cr["path2"]} if cr.get("path2") else {})}
            elif ctype == "DISPLAY":
                ad_body["responsiveDisplayAd"] = {"headlines": _text_assets(_lst(cr, "headlines")), "longHeadline": {"text": (_lst(cr, "long_headlines") or [""])[0]},
                                                  "descriptions": _text_assets(_lst(cr, "descriptions")), "businessName": cr.get("business_name", ""),
                                                  "marketingImages": images[:1], "squareMarketingImages": images[1:2] or images[:1]}
            elif youtube:
                video = tmp("assets")
                ops.append({"assetOperation": {"create": {"resourceName": video, "name": f"{ad['name']} video",
                                                          "youtubeVideoAsset": {"youtubeVideoId": youtube_id(cr.get("youtube_video"))}}}})
                ad_body["demandGenVideoResponsiveAd"] = {
                    "headlines": _text_assets(_lst(cr, "headline")), "longHeadlines": _text_assets(_lst(cr, "long_headline") or _lst(cr, "headline")),
                    "descriptions": _text_assets(_lst(cr, "description")), "videos": [{"asset": video}], "logoImages": images[:1],
                    "businessName": {"text": cr.get("business_name", "")},
                    **({"callToActions": [{"text": cr["cta"].replace("_", " ").title()}]} if cr.get("cta") else {}),
                }
            else:  # Demand Gen image/video ad on Google
                ad_body["demandGenMultiAssetAd"] = {"headlines": _text_assets(_lst(cr, "headlines")), "descriptions": _text_assets(_lst(cr, "descriptions")),
                                                    "businessName": cr.get("business_name", ""), "marketingImages": images[:1],
                                                    "squareMarketingImages": images[1:2] or images[:1], "logoImages": images[2:3] or images[:1]}
            index["ads"][ad["id"]] = len(ops)
            ops.append({"adGroupAdOperation": {"create": {"adGroup": group, "status": "ENABLED", "ad": ad_body}}})
    return ops, index


def _pmax(ops: list[dict[str, Any]], tmp: _Temp, campaign: str, tree: dict[str, Any], index: dict[str, Any]) -> None:
    """Performance Max: one asset group per ad (Google has no ad groups here);
    each text, image and YouTube video becomes an asset linked to it."""
    for g in tree["groups"]:
        for ad in g["ads"]:
            cr = ad["creative"]
            group = tmp("assetGroups")
            index["ads"][ad["id"]] = len(ops)
            # Our group points at its first asset group (pause/resume works on it).
            index["groups"].setdefault(g["id"], len(ops))
            ops.append({"assetGroupOperation": {"create": {"resourceName": group, "campaign": campaign, "name": ad["name"],
                                                           "finalUrls": [cr.get("destination_url", "")], "status": "ENABLED"}}})
            links: list[tuple[str, str]] = []
            for key, field_type in (("headlines", "HEADLINE"), ("long_headlines", "LONG_HEADLINE"), ("descriptions", "DESCRIPTION"), ("business_name", "BUSINESS_NAME")):
                for text in _lst(cr, key):
                    asset = tmp("assets")
                    ops.append({"assetOperation": {"create": {"resourceName": asset, "textAsset": {"text": text}}}})
                    links.append((asset, field_type))
            images = [m["media_id"] for m in cr.get("media") or [] if m.get("kind") == "image"]
            for i, asset in enumerate(images):
                links.append((asset, ("MARKETING_IMAGE", "SQUARE_MARKETING_IMAGE", "LOGO")[min(i, 2)]))
            for link in _lst(cr, "youtube_videos"):
                asset = tmp("assets")
                ops.append({"assetOperation": {"create": {"resourceName": asset, "youtubeVideoAsset": {"youtubeVideoId": youtube_id(link)}}}})
                links.append((asset, "YOUTUBE_VIDEO"))
            for asset, field_type in links:
                ops.append({"assetGroupAssetOperation": {"create": {"assetGroup": group, "asset": asset, "fieldType": field_type}}})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
COUNTS = {  # format -> {field: (min, max)}
    "responsive_search": {"headlines": (3, 15), "descriptions": (2, 4)},
    "responsive_display": {"headlines": (1, 5), "long_headlines": (1, 1), "descriptions": (1, 5)},
    "demand_gen": {"headlines": (1, 5), "descriptions": (1, 5)},
    "asset_group": {"headlines": (3, 15), "long_headlines": (1, 5), "descriptions": (2, 5)},
}


def validate(conn: dict[str, Any], tree: dict[str, Any]) -> list[dict[str, Any]]:
    youtube = tree["platform"] == "youtube"
    label = "YouTube" if youtube else "Google Ads"
    out = unresolved(tree, ("locations", "languages", "audiences", "topics"), label)
    c = tree["campaign"]
    for gi, g in enumerate(tree["groups"]):
        if c.get("campaign_type") == "SEARCH" and not entries(g["targeting"], "keywords"):
            out.append(issue("group", g["id"], f"groups[{gi}].targeting.keywords", "A Search ad group needs at least one keyword."))
        for ai, ad in enumerate(g["ads"]):
            cr = ad["creative"]
            path = f"groups[{gi}].ads[{ai}]"
            if not cr.get("destination_url"):
                out.append(issue("ad", ad["id"], f"{path}.destination_url", "Add the final URL."))
            if youtube:
                if not youtube_id(cr.get("youtube_video")):
                    out.append(issue("ad", ad["id"], f"{path}.youtube_video", "Paste a YouTube video link or 11-character video ID."))
                for key in ("headline", "description", "business_name"):
                    if not str(cr.get(key) or "").strip():
                        out.append(issue("ad", ad["id"], f"{path}.{key}", f"Add the {key.replace('_', ' ')}."))
                if not any(m.get("kind") == "image" for m in cr.get("media") or []):
                    out.append(issue("ad", ad["id"], f"{path}.media", "Upload a square logo image (Google requires one)."))
                continue
            for key, (lo, hi) in COUNTS.get(str(cr.get("format")), {}).items():
                n = len(_lst(cr, key))
                if n < lo or n > hi:
                    out.append(issue("ad", ad["id"], f"{path}.{key}", f"{key.replace('_', ' ').capitalize()}: {lo}–{hi} needed, {n} given."))
            if cr.get("format") in ("responsive_display", "demand_gen", "asset_group"):
                if not str(cr.get("business_name") or "").strip():
                    out.append(issue("ad", ad["id"], f"{path}.business_name", "Add the business name."))
                if not any(m.get("kind") == "image" for m in cr.get("media") or []):
                    out.append(issue("ad", ad["id"], f"{path}.media", "Upload at least one image."))
            if cr.get("format") == "asset_group" and _lst(cr, "descriptions") and len(_lst(cr, "descriptions")[0]) > 60:
                out.append(issue("ad", ad["id"], f"{path}.descriptions[0]", "Performance Max needs one description of 60 characters or fewer (the first)."))
    if any(i["severity"] == "error" for i in out):
        return out
    try:
        account = verify_account(conn["fields"])
        if account.get("currency") and account["currency"] != c["currency"]:
            return out + [issue("campaign", c["id"], "campaign.currency", f"Your Google Ads account bills in {account['currency']}, but this campaign is in {c['currency']}.")]
        ops, _ = build_operations(conn["fields"], tree)
        _mutate(conn["fields"], ops, validate_only=True)
    except PlatformError as exc:
        out.append(issue("campaign", c["id"], exc.path or "campaign", exc.message))
    return out


# ---------------------------------------------------------------------------
# Lookups and media
# ---------------------------------------------------------------------------
def lookup(conn: dict[str, Any], kind: str, q: str) -> list[dict[str, Any]]:
    f = conn["fields"]
    safe = q.replace("'", "").replace("\\", "")[:80]
    if kind == "locations":
        resp = http("POST", f"{_base()}/geoTargetConstants:suggest", headers=_headers(f), json={"locale": "en", "searchTerm": q[:80]})
        if resp.status_code >= 400:
            raise _error(resp)
        return [{"id": str((s.get("geoTargetConstant") or {}).get("id")), "name": (s.get("geoTargetConstant") or {}).get("canonicalName") or (s.get("geoTargetConstant") or {}).get("name"),
                 "type": (s.get("geoTargetConstant") or {}).get("targetType")} for s in resp.json().get("geoTargetConstantSuggestions") or []][:50]
    if kind == "languages":
        rows = _search(f, f"SELECT language_constant.id, language_constant.name FROM language_constant WHERE language_constant.targetable = TRUE AND language_constant.name LIKE '%{safe}%'")
        return [{"id": str(r["languageConstant"]["id"]), "name": r["languageConstant"]["name"]} for r in rows][:50]
    if kind == "audiences":
        rows = _search(f, f"SELECT user_list.id, user_list.name FROM user_list WHERE user_list.name LIKE '%{safe}%'")
        return [{"id": str(r["userList"]["id"]), "name": r["userList"]["name"]} for r in rows][:50]
    if kind == "topics":
        rows = _search(f, "SELECT topic_constant.id, topic_constant.path FROM topic_constant")
        found = [{"id": str(r["topicConstant"]["id"]), "name": " › ".join(r["topicConstant"].get("path") or [])} for r in rows]
        return [x for x in found if q.lower() in x["name"].lower()][:50]
    raise PlatformError(f"Google Ads has no {kind} list.", 404)


def upload_media(conn: dict[str, Any], filename: str, content: bytes) -> dict[str, Any]:
    if filename.lower().rsplit(".", 1)[-1] in ("mp4", "mov", "avi", "webm", "mpeg"):
        raise PlatformError("Google Ads takes videos as YouTube links: upload the video to YouTube and paste its link.", 422)
    asset = f"customers/{_cid(conn['fields'])}/assets/-1"
    res = _mutate(conn["fields"], [{"assetOperation": {"create": {"resourceName": asset, "name": f"{filename} {int(time.time())}", "type": "IMAGE",
                                                                   "imageAsset": {"data": base64.b64encode(content).decode()}}}}])
    resource = ((res[0] if res else {}).get("assetResult") or {}).get("resourceName")
    if not resource:
        raise PlatformError("Google Ads didn't return the image asset.", 502)
    return {"media_id": resource, "kind": "image", "name": filename, "thumbnail_url": None}


# ---------------------------------------------------------------------------
# Publish / status / results
# ---------------------------------------------------------------------------
def _result_name(response: dict[str, Any]) -> str | None:
    for value in response.values():
        if isinstance(value, dict) and value.get("resourceName"):
            return str(value["resourceName"])
    return None


def publish(conn: dict[str, Any], tree: dict[str, Any], mode: str) -> dict[str, Any]:
    f = conn["fields"]
    ops, index = build_operations(f, tree)
    try:
        responses = _mutate(f, ops)
    except PlatformError as exc:
        # Atomic: nothing was created.
        raise PlatformError(exc.message, exc.status_code, path=exc.path or "campaign", auth=exc.auth) from None
    campaign = _result_name(responses[index["campaign"]]) or ""
    if mode == "active":
        try:
            _mutate(f, [{"campaignOperation": {"update": {"resourceName": campaign, "status": "ENABLED"}, "updateMask": "status"}}])
        except PlatformError as exc:
            try:
                _mutate(f, [{"campaignOperation": {"remove": campaign}}])
            except PlatformError:
                pass
            raise PlatformError(exc.message, exc.status_code, path="campaign", auth=exc.auth) from None
    groups = {row: (_result_name(responses[i]) or "") for row, i in index["groups"].items()}
    ads = {row: (_result_name(responses[i]) or "") for row, i in index["ads"].items()}
    campaign_id = campaign.rsplit("/", 1)[-1]
    return {"campaign": campaign, "groups": groups, "ads": ads,
            "url": f"https://ads.google.com/aw/campaigns?campaignId={campaign_id}&ocid={_cid(f)}"}


def set_status(conn: dict[str, Any], level: str, external_id: str, active: bool) -> None:
    status = "ENABLED" if active else "PAUSED"
    if "/assetGroups/" in external_id:
        op = {"assetGroupOperation": {"update": {"resourceName": external_id, "status": status}, "updateMask": "status"}}
    else:
        op = {{"campaign": "campaignOperation", "group": "adGroupOperation", "ad": "adGroupAdOperation"}[level]:
              {"update": {"resourceName": external_id, "status": status}, "updateMask": "status"}}
    _mutate(conn["fields"], [op])


def import_results(conn: dict[str, Any], campaign_ids: list[str], since: str, until: str) -> list[dict[str, Any]]:
    names = ", ".join(f"'{c}'" for c in campaign_ids if re.fullmatch(r"customers/\d+/campaigns/\d+", c))
    if not names:
        return []
    rows = _search(conn["fields"], "SELECT campaign.resource_name, segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks, "
                                   f"metrics.conversions, metrics.conversions_value FROM campaign WHERE campaign.resource_name IN ({names}) "
                                   f"AND segments.date BETWEEN '{since}' AND '{until}'")
    out = []
    for r in rows:
        m = r.get("metrics") or {}
        out.append({"campaign_id": (r.get("campaign") or {}).get("resourceName"), "date": (r.get("segments") or {}).get("date"),
                    "spend": Decimal(str(m.get("costMicros", 0))) / 1_000_000, "impressions": m.get("impressions"), "clicks": m.get("clicks"),
                    "conversions": m.get("conversions"), "conversion_value": m.get("conversionsValue")})
    return out
