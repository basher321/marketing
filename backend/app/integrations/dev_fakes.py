"""Dev-only fake transport for Meta / Shopify / WooCommerce (SPEC-FE-039 open
decision, approved 2026-10-01), and since SPEC-BE-063..068 for TikTok, Google
Ads (+YouTube), LinkedIn, X, Snapchat and Pinterest too.

With META_FAKE_TRANSPORT=true (refused when APP_ENV=production, see
config.py) every Meta Graph, Shopify Admin and WooCommerce REST call is
answered in-process by `httpx.MockTransport` from the fixtures below, so the
builder, shipping sync and results import can be exercised end to end without
real accounts. Nothing here runs unless that flag is set; it never touches the
network. Fake objects live in memory for the life of the process.
"""
import itertools
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

_ids = itertools.count(120000000000001)
_adset_campaign: dict[str, str] = {}
_ad_campaign: dict[str, str] = {}
_status: dict[str, str] = {}


def _new_id() -> str:
    return str(next(_ids))


def _json(data: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


def _form(request: httpx.Request) -> dict[str, str]:
    ctype = request.headers.get("content-type", "")
    if "multipart" in ctype:
        return {}
    body = request.content.decode() if request.content else ""
    return {k: v[0] for k, v in parse_qs(body).items()}


# Organic publishing fakes (SPEC-BE-075): Facebook Page posts and the
# Instagram container flow. A video container answers IN_PROGRESS for
# IG_VIDEO_POLLS status reads, then FINISHED; IG_QUOTA_USED is the account's
# rolling-24h API post count (100 = limit reached).
_ig_containers: dict[str, int] = {}
IG_VIDEO_POLLS = 1
IG_QUOTA_USED = {"value": 0}


def _meta_organic(request: httpx.Request, path: str, params: dict[str, str], form: dict[str, str]) -> httpx.Response | None:
    method = request.method
    fields = params.get("fields", "")
    if path == "me/accounts":
        return None  # answered by _meta (ads and social sign-in share it)
    if path == "me/permissions":
        granted = ["pages_manage_posts", "pages_read_engagement", "instagram_basic", "instagram_content_publish"]
        return _json({"data": [{"permission": p, "status": "granted"} for p in granted]})
    if method == "POST" and path.endswith("/feed"):
        return _json({"id": f"{path.split('/')[0]}_{_new_id()}"})
    if method == "POST" and path.endswith("/photos"):
        new = _new_id()
        return _json({"id": new, "post_id": f"{path.split('/')[0]}_{new}"})
    if method == "POST" and path.endswith("/videos"):
        return _json({"id": _new_id()})
    if method == "POST" and path.endswith("/media_publish"):
        if form.get("creation_id") not in _ig_containers:
            return _json({"error": {"message": "Fake IG: unknown container", "code": 100}}, 400)
        return _json({"id": _new_id()})
    if method == "POST" and path.endswith("/media"):
        cid = _new_id()
        is_video = form.get("media_type") in ("REELS", "VIDEO") or "video_url" in form
        _ig_containers[cid] = IG_VIDEO_POLLS if is_video else 0
        return _json({"id": cid})
    if method == "GET" and path.endswith("/content_publishing_limit"):
        return _json({"data": [{"quota_usage": IG_QUOTA_USED["value"], "config": {"quota_total": 100, "quota_duration": 86400}}]})
    if method == "GET" and path.endswith("/insights") and "metric" in params:
        names = params["metric"].split(",")
        return _json({"data": [{"name": n, "values": [{"value": 10 * (i + 1)}]} for i, n in enumerate(names)]})
    # Ad setup "Use existing post" (SPEC-BE-082): a first page with a cursor, then a last page.
    if method == "GET" and path.endswith("/published_posts"):
        page = path.split("/")[0]
        if params.get("after"):
            return _json({"data": [{"id": f"{page}_7000003", "message": "Older fake post", "created_time": "2026-09-01T10:00:00+0000",
                                    "permalink_url": f"https://www.facebook.com/{page}/posts/7000003"}], "paging": {}})
        return _json({"data": [{"id": f"{page}_7000001", "message": "New arrivals are here!", "full_picture": "https://scontent.xx.fbcdn.net/fake-post1.jpg",
                                "created_time": "2026-10-01T10:00:00+0000", "permalink_url": f"https://www.facebook.com/{page}/posts/7000001"},
                               {"id": f"{page}_7000002", "message": "Weekend sale: 20% off", "created_time": "2026-09-20T10:00:00+0000",
                                "permalink_url": f"https://www.facebook.com/{page}/posts/7000002"}],
                      "paging": {"cursors": {"after": "fake-after"}, "next": "https://graph.facebook.com/fake-next"}})
    if method == "GET" and path.endswith("/media") and "caption" in fields:
        return _json({"data": [{"id": "8000001", "caption": "Fake IG photo", "media_type": "IMAGE", "media_url": "https://scontent.cdninstagram.com/fake1.jpg",
                                "permalink": "https://www.instagram.com/p/fake8000001/", "timestamp": "2026-10-02T09:00:00+0000"},
                               {"id": "8000002", "caption": "Fake IG reel", "media_type": "VIDEO", "media_url": "https://scontent.cdninstagram.com/fake2.mp4",
                                "thumbnail_url": "https://scontent.cdninstagram.com/fake2.jpg", "permalink": "https://www.instagram.com/reel/fake8000002/",
                                "timestamp": "2026-09-28T09:00:00+0000"}], "paging": {}})
    if method == "GET" and "status_code" in fields:
        left = _ig_containers.get(path, 0)
        if left > 0:
            _ig_containers[path] = left - 1
            return _json({"id": path, "status_code": "IN_PROGRESS"})
        return _json({"id": path, "status_code": "FINISHED"})
    if method == "GET" and "permalink" in fields:
        return _json({"id": path, "permalink": f"https://www.instagram.com/p/fake{path}/"})
    if method == "GET" and "reactions" in fields:
        return _json({"id": path, "reactions": {"summary": {"total_count": 12}}, "comments": {"summary": {"total_count": 3}}, "shares": {"count": 2}})
    if method == "GET" and "access_token" in fields:
        return _json({"id": path, "name": "Fake Page", "access_token": "fake-page-token"})
    if method == "GET" and "profile_picture_url" in fields:
        return _json({"id": path, "username": "fake_shop", "name": "Fake Shop", "profile_picture_url": "https://example.invalid/ig.jpg"})
    # "status,picture" is the ad video status poll, answered by _meta's numeric-id fixture.
    if method == "GET" and "picture" in fields and "status" not in fields:
        return _json({"id": path, "name": "Fake Page", "username": "fakepage", "link": "https://www.facebook.com/fakepage",
                      "picture": {"data": {"url": "https://example.invalid/page.jpg"}}})
    return None


def _meta(request: httpx.Request) -> httpx.Response:
    currency = get_settings().META_FAKE_CURRENCY
    path = request.url.path.split("/", 2)[-1] if request.url.path.count("/") >= 2 else ""
    params = dict(request.url.params)
    form = _form(request)
    method = request.method
    organic = _meta_organic(request, path, params, form)
    if organic is not None:
        return organic
    if path.startswith("oauth/access_token"):
        # Social sign-in (SPEC-BE-080): code "bad" is rejected; the
        # fb_exchange_token step returns a long-lived user token.
        if params.get("code") == "bad":
            return _json({"error": {"message": "Invalid verification code format.", "type": "OAuthException", "code": 100}}, 400)
        if params.get("grant_type") == "fb_exchange_token":
            return _json({"access_token": "fake-long-lived-user-token", "token_type": "bearer", "expires_in": 5183944})
        return _json({"access_token": "fake-system-user-token"})
    if path == "me":
        return _json({"id": "9000001", "name": "Fake system user"})
    if path == "me/adaccounts":
        return _json({"data": [{"id": "act_1000001", "account_id": "1000001", "name": "Fake ad account", "currency": currency, "account_status": 1}]})
    if path == "me/accounts":
        return _json({"data": [{"id": "2000001", "name": "Fake Page", "access_token": "fake-page-token",
                                "picture": {"data": {"url": "https://example.invalid/page.jpg"}},
                                "instagram_business_account": {"id": "3000001", "username": "fake_shop",
                                                               "profile_picture_url": "https://example.invalid/ig.jpg"}}]})
    if path.endswith("/adspixels"):
        return _json({"data": [{"id": "4000001", "name": "Fake pixel"}]})
    if path.endswith("/customaudiences"):
        return _json({"data": [{"id": "5000001", "name": "Past buyers", "subtype": "CUSTOM", "approximate_count_lower_bound": 1200},
                               {"id": "5000002", "name": "Lookalike (BD, 1%)", "subtype": "LOOKALIKE", "approximate_count_lower_bound": 900000}]})
    if path.endswith("/advertisable_applications"):
        return _json({"data": []})
    if path.endswith("/leadgen_forms"):
        return _json({"data": [{"id": "6000001", "name": "Fake lead form", "status": "ACTIVE"}]})
    if path.endswith("/delivery_estimate"):
        return _json({"data": [{"estimate_mau_lower_bound": 410000, "estimate_mau_upper_bound": 520000,
                                "daily_outcomes_curve": [{"reach": 1800}, {"reach": 5200}]}]})
    if path.endswith("/generatepreviews"):
        return _json({"data": [{"body": '<iframe src="https://www.facebook.com/ads/api/preview_iframe.php?d=fake&amp;t=1" width="320" height="500"></iframe>'}]})
    if path.endswith("/adimages") and method == "POST":
        return _json({"images": {"upload": {"hash": f"fakehash{_new_id()}", "url": "https://scontent.xx.fbcdn.net/fake.jpg"}}})
    if path.endswith("/advideos") and method == "POST":
        return _json({"id": _new_id()})
    if path == "search":
        q = params.get("q", "").title()
        kind = params.get("type")
        if kind == "adgeolocation":
            return _json({"data": [{"key": "BD", "name": "Bangladesh", "type": "country", "country_code": "BD"},
                                   {"key": "2390", "name": f"{q or 'Dhaka'} Division", "type": "region", "country_code": "BD"},
                                   {"key": "1012345", "name": q or "Dhaka", "type": "city", "country_code": "BD"}]})
        if kind == "adlocale":
            return _json({"data": [{"key": 6, "name": "English (US)"}, {"key": 45, "name": "Bengali"}]})
        return _json({"data": [{"id": "6003107902433", "name": q or "Fashion", "audience_size_lower_bound": 1000000},
                               {"id": "6003020834693", "name": f"{q or 'Online'} shopping", "audience_size_lower_bound": 800000}]})
    if path.startswith("act_") and path.count("/") == 0 and method == "GET":
        return _json({"name": "Fake ad account", "currency": currency, "account_status": 1, "timezone_name": "Asia/Dhaka",
                      "business": {"id": "9100001", "name": "Fake business"}})
    # Product-set carousels (SPEC-BE-082): one owned catalog with two sets.
    if path == "9100001/owned_product_catalogs":
        return _json({"data": [{"id": "9200001", "name": "Fake catalog"}]})
    if path == "9100001/client_product_catalogs":
        return _json({"data": []})
    if path.endswith("/product_sets"):
        return _json({"data": [{"id": "9300001", "name": "All products", "product_count": 42},
                               {"id": "9300002", "name": "Best sellers", "product_count": 8}]})
    if path.startswith("act_") and method == "POST":
        if form.get("execution_options"):
            return _json({"success": True})
        edge = path.split("/", 1)[1]
        new = _new_id()
        if edge == "adsets":
            _adset_campaign[new] = form.get("campaign_id", "")
        if edge == "ads":
            _ad_campaign[new] = _adset_campaign.get(form.get("adset_id", ""), "")
        _status[new] = form.get("status", "PAUSED")
        return _json({"id": new})
    if path.endswith("/insights"):
        campaign = path.split("/")[0]
        ads = [a for a, c in _ad_campaign.items() if c == campaign]
        tr = json.loads(params.get("time_range", "{}") or "{}")
        start = date.fromisoformat(tr.get("since", date.today().isoformat()))
        end = date.fromisoformat(tr.get("until", date.today().isoformat()))
        rows = []
        day = start
        while day <= end:
            for i, ad in enumerate(ads):
                n = (day.toordinal() + i) % 5 + 1
                rows.append({"ad_id": ad, "date_start": day.isoformat(), "spend": f"{n * 120}.50", "impressions": str(n * 1500),
                             "reach": str(n * 1100), "clicks": str(n * 40), "inline_link_clicks": str(n * 31),
                             "actions": [{"action_type": "purchase", "value": str(n)}],
                             "action_values": [{"action_type": "purchase", "value": f"{n * 900}.00"}]})
            day += timedelta(days=1)
        return _json({"data": rows, "paging": {}})
    if path in ("", "/") and "ids" in params:
        out = {}
        for oid in params["ids"].split(","):
            if "ad_review_feedback" in params.get("fields", ""):
                out[oid] = {"id": oid}
            else:
                out[oid] = {"id": oid, "effective_status": _status.get(oid, "ACTIVE"), "configured_status": _status.get(oid, "ACTIVE")}
        return _json(out)
    if method == "POST" and path.isdigit():
        if "status" in form:
            _status[path] = form["status"]
        return _json({"success": True})
    if method == "DELETE":
        return _json({"success": True})
    if method == "GET" and path.isdigit():
        return _json({"id": path, "status": {"video_status": "ready"}, "picture": "https://scontent.xx.fbcdn.net/fake-thumb.jpg"})
    logger.warning("dev_fake_meta_unhandled", path=path, method=method)
    return _json({"error": {"message": f"Fake Meta has no fixture for {method} {path}", "code": 100}}, 400)


def _shopify(request: httpx.Request) -> httpx.Response:
    currency = get_settings().META_FAKE_CURRENCY
    if request.url.path.endswith("/oauth/access_token"):
        return _json({"access_token": "fake-shopify-token", "expires_in": 86399})
    if request.url.path.endswith("/shop.json"):
        return _json({"shop": {"name": "Fake Shopify store"}})
    body = json.loads(request.content or b"{}")
    if "deliveryProfileUpdate" in body.get("query", ""):
        return _json({"data": {"deliveryProfileUpdate": {"profile": {"id": "gid://shopify/DeliveryProfile/1"}, "userErrors": []}}})
    if "deliveryProfiles(first: 10)" in body.get("query", ""):
        return _json({"data": {"deliveryProfiles": {"nodes": [{"id": "gid://shopify/DeliveryProfile/1", "default": True, "profileLocationGroups": [{"locationGroup": {"id": "gid://shopify/DeliveryLocationGroup/1"}}]}]}}})
    return _json({"data": {"shop": {"currencyCode": currency}, "deliveryProfiles": {"nodes": [{
        "id": "gid://shopify/DeliveryProfile/1", "name": "General", "default": True,
        "profileLocationGroups": [{"locationGroupZones": {"nodes": [{
            "zone": {"id": "gid://shopify/DeliveryZone/1", "name": "Bangladesh", "countries": [{"code": {"countryCode": "BD", "restOfWorld": False}, "provinces": [{"code": "DH", "name": "Dhaka"}]}]},
            "methodDefinitions": {"nodes": [
                {"id": "gid://shopify/DeliveryMethodDefinition/1", "name": "Standard", "active": True, "rateProvider": {"price": {"amount": "80.0", "currencyCode": currency}}, "methodConditions": []},
                {"id": "gid://shopify/DeliveryMethodDefinition/2", "name": "Free over 2000", "active": True, "rateProvider": {"price": {"amount": "0.0", "currencyCode": currency}},
                 "methodConditions": [{"field": "TOTAL_PRICE", "operator": "GREATER_THAN_OR_EQUAL_TO", "conditionCriteria": {"amount": "2000.0", "currencyCode": currency}}]},
                {"id": "gid://shopify/DeliveryMethodDefinition/3", "name": "Courier (calculated)", "active": True,
                 "rateProvider": {"carrierService": {"id": "gid://shopify/CarrierService/1", "formattedName": "Pathao"}, "fixedFee": {"amount": "0"}, "percentageOfRateFee": 0}, "methodConditions": []},
            ]},
        }]}}],
    }]}, "carrierServices": {"nodes": []}}})


def _woo(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p.endswith("/system_status"):
        return _json({"environment": {"site_url": "https://fake-woo.example"}})
    if "woocommerce_currency" in p:
        return _json({"value": get_settings().META_FAKE_CURRENCY})
    if request.method in ("POST", "PUT"):
        return _json({"id": int(_new_id()) % 1000, "instance_id": int(_new_id()) % 1000})
    if p.endswith("/shipping/zones"):
        return _json([{"id": 0, "name": "Locations not covered by your other zones"}, {"id": 1, "name": "Dhaka"}])
    if p.endswith("/locations"):
        return _json([{"code": "BD", "type": "country"}] if "/zones/1/" in p else [])
    if p.endswith("/methods"):
        if "/zones/1/" not in p:
            return _json([])
        return _json([{"instance_id": 3, "method_id": "flat_rate", "title": "Flat rate", "enabled": True, "settings": {"cost": {"value": "60"}}},
                      {"instance_id": 4, "method_id": "free_shipping", "title": "Free shipping", "enabled": True, "settings": {"min_amount": {"value": "1500"}}},
                      {"instance_id": 6, "method_id": "local_pickup", "title": "Pickup at shop", "enabled": True, "settings": {"cost": {"value": "0"}}}])
    return _json({"message": "Fake WooCommerce has no fixture for this call"}, 404)


# ---------------------------------------------------------------------------
# Ad platforms (SPEC-BE-063..068): TikTok, Google Ads (+YouTube), LinkedIn,
# X, Snapchat, Pinterest. Each fake answers the calls its adapter makes, in
# the platform's own response shape. CALLS records (platform, method, path)
# so checks can assert rollbacks; FAIL maps a platform to a path fragment
# that answers with that platform's error (used to prove all-or-nothing).
# ---------------------------------------------------------------------------
CALLS: list[tuple[str, str, str]] = []
FAIL: dict[str, str] = {}
# Matching calls to let through before FAIL applies (e.g. Google's validate-only mutate).
FAIL_SKIP: dict[str, int] = {}
_objects: dict[str, dict[str, Any]] = {}


def _days(since: str, until: str) -> list[str]:
    start, end = date.fromisoformat(since[:10]), date.fromisoformat(until[:10])
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def _body(request: httpx.Request) -> Any:
    try:
        return json.loads(request.content or b"null")
    except ValueError:
        return None


def _tiktok(request: httpx.Request, path: str) -> httpx.Response:
    p = path.split("/open_api/v1.3/", 1)[-1]
    ok = lambda data: _json({"code": 0, "message": "OK", "data": data})  # noqa: E731
    currency = get_settings().META_FAKE_CURRENCY
    if p.startswith("advertiser/info"):
        return ok({"list": [{"name": "Fake TikTok advertiser", "currency": currency, "timezone": "Asia/Dhaka"}]})
    if p.startswith("campaign/create"):
        return ok({"campaign_id": _new_id()})
    if p.startswith("adgroup/create"):
        return ok({"adgroup_id": _new_id()})
    if p.startswith("ad/create"):
        return ok({"ad_ids": [_new_id()]})
    if "/status/update" in p:
        return ok({})
    if p.startswith("file/video"):
        return ok([{"video_id": "v" + _new_id(), "video_cover_url": "https://example.invalid/cover.jpg"}])
    if p.startswith("file/image"):
        return ok({"image_id": "i" + _new_id(), "image_url": "https://example.invalid/i.jpg"})
    if p.startswith("tool/region"):
        return ok({"region_info": [{"location_id": "1210997", "name": "Bangladesh", "region_level": "COUNTRY"}, {"location_id": "6252001", "name": "United States", "region_level": "COUNTRY"}]})
    if p.startswith("tool/language"):
        return ok({"languages": [{"code": "en", "name": "English"}, {"code": "bn", "name": "Bengali"}]})
    if p.startswith("tool/interest_category"):
        return ok({"interest_categories": [{"id": "10001", "name": "Fashion"}, {"id": "10002", "name": "Beauty"}]})
    if p.startswith("dmp/custom_audience"):
        return ok({"list": [{"audience_id": "a1", "name": "Past buyers"}]})
    if p.startswith("report/integrated"):
        params = dict(request.url.params)
        ids = json.loads(json.loads(params["filtering"])[0]["filter_value"])
        rows = [{"dimensions": {"campaign_id": cid, "stat_time_day": f"{d} 00:00:00"},
                 "metrics": {"spend": "12.50", "impressions": "5000", "clicks": "120", "conversion": "4"}}
                for cid in ids for d in _days(params["start_date"], params["end_date"])]
        return ok({"list": rows})
    return _json({"code": 40404, "message": f"Fake TikTok: unknown path {p}"})


_GOOGLE_RESULT = {
    "campaignBudgetOperation": ("campaignBudgetResult", "campaignBudgets"), "campaignOperation": ("campaignResult", "campaigns"),
    "adGroupOperation": ("adGroupResult", "adGroups"), "adGroupAdOperation": ("adGroupAdResult", "adGroupAds"),
    "assetGroupOperation": ("assetGroupResult", "assetGroups"), "assetOperation": ("assetResult", "assets"),
    "campaignCriterionOperation": ("campaignCriterionResult", "campaignCriteria"), "adGroupCriterionOperation": ("adGroupCriterionResult", "adGroupCriteria"),
    "assetGroupAssetOperation": ("assetGroupAssetResult", "assetGroupAssets"),
}


def _google(request: httpx.Request, path: str) -> httpx.Response:
    if request.url.host == "oauth2.googleapis.com":
        return _json({"access_token": "fake-google-token", "expires_in": 3600})
    body = _body(request) or {}
    cid = path.split("/customers/", 1)[-1].split("/", 1)[0] if "/customers/" in path else "1234567890"
    currency = get_settings().META_FAKE_CURRENCY
    if path.endswith("geoTargetConstants:suggest"):
        return _json({"geoTargetConstantSuggestions": [{"geoTargetConstant": {"id": "2050", "name": "Bangladesh", "canonicalName": "Bangladesh", "targetType": "Country"}}]})
    if path.endswith("googleAds:searchStream"):
        q = body.get("query", "")
        if "FROM customer" in q:
            return _json([{"results": [{"customer": {"descriptiveName": "Fake Google Ads account", "currencyCode": currency, "timeZone": "Asia/Dhaka"}}]}])
        if "FROM language_constant" in q:
            return _json([{"results": [{"languageConstant": {"id": "1000", "name": "English"}}]}])
        if "FROM user_list" in q:
            return _json([{"results": [{"userList": {"id": "55", "name": "Website visitors"}}]}])
        if "FROM topic_constant" in q:
            return _json([{"results": [{"topicConstant": {"id": "18", "path": ["Shopping", "Apparel"]}}]}])
        if "FROM campaign" in q:
            names = [part.strip(" '") for part in q.split("IN (", 1)[1].split(")", 1)[0].split(",")]
            span = q.split("BETWEEN '", 1)[1]
            since, until = span.split("'", 1)[0], span.split("AND '", 1)[1].split("'", 1)[0]
            return _json([{"results": [{"campaign": {"resourceName": n}, "segments": {"date": d},
                                        "metrics": {"costMicros": "8000000", "impressions": "3000", "clicks": "90", "conversions": 3.0, "conversionsValue": 120.0}}
                                       for n in names for d in _days(since, until)]}])
        return _json([{"results": []}])
    if path.endswith("googleAds:mutate"):
        if body.get("validateOnly"):
            return _json({})
        temp: dict[str, str] = {}
        out = []
        for op in body.get("mutateOperations") or []:
            kind = next(iter(op))
            result_key, collection = _GOOGLE_RESULT.get(kind, ("result", "objects"))
            inner = op[kind]
            if "create" in inner:
                given = str(inner["create"].get("resourceName") or "")
                name = f"customers/{cid}/{collection}/{_new_id()}"
                if collection == "adGroupAds":
                    group = temp.get(inner["create"].get("adGroup"), inner["create"].get("adGroup", ""))
                    name = f"customers/{cid}/adGroupAds/{group.rsplit('/', 1)[-1]}~{_new_id()}"
                if given:
                    temp[given] = name
            else:
                name = inner.get("update", {}).get("resourceName") or inner.get("remove") or ""
            out.append({result_key: {"resourceName": name}})
        return _json({"mutateOperationResponses": out})
    return _json({"error": {"code": 404, "message": f"Fake Google: unknown path {path}", "status": "NOT_FOUND"}}, 404)


def _linkedin(request: httpx.Request, path: str) -> httpx.Response:
    if request.url.host == "www.linkedin.com" and "accessToken" in path:
        # Social sign-in (SPEC-BE-080): code / refresh token "bad" -> invalid_grant.
        form = _form(request)
        if "bad" in (form.get("code"), form.get("refresh_token")):
            return _json({"error": "invalid_grant", "error_description": "The authorization code or refresh token is invalid or expired."}, 400)
        return _json({"access_token": "fake-linkedin-token", "expires_in": 5184000, "refresh_token": "fake-linkedin-refresh",
                      "refresh_token_expires_in": 31536000, "scope": "r_organization_admin,w_organization_social,r_organization_social"})
    if request.method == "GET" and path.endswith("/rest/organizationAcls"):
        return _json({"elements": [{"organization": "urn:li:organization:7000001", "role": "ADMINISTRATOR", "state": "APPROVED"}]})
    if "dms-uploads" in path:
        return httpx.Response(201, headers={"etag": "fake-etag"})
    p = path.split("/rest/", 1)[-1]
    method = request.method
    currency = get_settings().META_FAKE_CURRENCY
    created = lambda urn: httpx.Response(201, headers={"x-restli-id": urn})  # noqa: E731
    if method == "GET" and p.startswith("adAccounts/") and p.count("/") == 1:
        return _json({"id": p.split("/")[1], "name": "Fake LinkedIn ad account", "currency": currency, "status": "ACTIVE"})
    if method == "POST" and p.endswith("/adCampaignGroups"):
        return created(_new_id())
    if method == "POST" and p.endswith("/adCampaigns"):
        return created(_new_id())
    if method == "POST" and p == "posts":
        return created(f"urn:li:share:{_new_id()}")
    # Organic (SPEC-BE-075): the company page and post statistics.
    if method == "GET" and p.startswith("organizations/"):
        return _json({"id": int(p.split("/")[1]), "localizedName": "Fake Company", "vanityName": "fake-company"})
    if method == "GET" and p.startswith("organizationalEntityShareStatistics"):
        return _json({"elements": [{"totalShareStatistics": {"impressionCount": 900, "uniqueImpressionsCount": 700, "clickCount": 21,
                                                             "likeCount": 14, "commentCount": 3, "shareCount": 1}}]})
    if method == "POST" and p.endswith("/creatives"):
        return created(f"urn:li:sponsoredCreative:{_new_id()}")
    if method in ("POST", "DELETE"):
        if "initializeUpload" in str(request.url):
            return _json({"value": {"uploadUrl": "https://www.linkedin.com/dms-uploads/fake", "image": f"urn:li:image:{_new_id()}",
                                    "document": f"urn:li:document:{_new_id()}", "video": f"urn:li:video:{_new_id()}", "uploadToken": "",
                                    "uploadInstructions": [{"uploadUrl": "https://www.linkedin.com/dms-uploads/fake", "firstByte": 0, "lastByte": 10**9}]}})
        return httpx.Response(204)
    if p.startswith("adTargetingEntities"):
        return _json({"elements": [{"urn": "urn:li:geo:106215326", "name": "Bangladesh"}, {"urn": "urn:li:title:9", "name": "Marketing Manager"}]})
    if p.startswith("adAnalytics"):
        url = str(request.url)
        groups = [g.rsplit("%3A", 1)[-1].rsplit(":", 1)[-1] for g in url.split("campaignGroups=List(", 1)[1].split(")", 1)[0].split(",")]
        s = url.split("start:(year:", 1)[1]
        e = url.split("end:(year:", 1)[1]

        def ymd(seg: str) -> str:
            y, rest = seg.split(",month:", 1)
            m, rest = rest.split(",day:", 1)
            return f"{int(y):04d}-{int(m):02d}-{int(rest.split(')', 1)[0]):02d}"

        elements = [{"pivotValues": [f"urn:li:sponsoredCampaignGroup:{g}"], "dateRange": {"start": {"year": int(d[:4]), "month": int(d[5:7]), "day": int(d[8:10])}},
                     "costInLocalCurrency": "9.75", "impressions": 2000, "clicks": 40, "externalWebsiteConversions": 2, "oneClickLeads": 1}
                    for g in groups for d in _days(ymd(s), ymd(e))]
        return _json({"elements": elements})
    return _json({"message": f"Fake LinkedIn: unknown path {p}", "status": 404}, 404)


def _snap(request: httpx.Request, path: str) -> httpx.Response:
    if request.url.host == "accounts.snapchat.com":
        return _json({"access_token": "fake-snap-token", "expires_in": 1800})
    p = path.split("/v1/", 1)[-1]
    body = _body(request) or {}
    method = request.method
    currency = get_settings().META_FAKE_CURRENCY

    def wrap(key: str, kind: str) -> httpx.Response:
        items = []
        for obj in body.get(key) or []:
            obj = {**obj, "id": obj.get("id") or _new_id()}
            _objects[obj["id"]] = {"key": key, "kind": kind, "obj": obj}
            items.append({"sub_request_status": "SUCCESS", kind: obj})
        return _json({"request_status": "SUCCESS", key: items})

    if method == "GET" and p.startswith("adaccounts/") and p.count("/") == 1:
        return _json({"request_status": "SUCCESS", "adaccounts": [{"sub_request_status": "SUCCESS", "adaccount": {"id": p.split("/")[1], "name": "Fake Snapchat account", "currency": currency, "timezone": "Asia/Dhaka"}}]})
    for suffix, key, kind in (("/campaigns", "campaigns", "campaign"), ("/adsquads", "adsquads", "adsquad"), ("/creatives", "creatives", "creative"), ("/ads", "ads", "ad"), ("/media", "media", "media")):
        if p.endswith(suffix) and method in ("POST", "PUT"):
            return wrap(key, kind)
    if p.endswith("/upload"):
        return _json({"request_status": "SUCCESS"})
    if method == "GET" and "/stats" in p:
        cid = p.split("/")[1]
        params = dict(request.url.params)
        series = [{"start_time": f"{d}T00:00:00.000-00:00", "stats": {"impressions": 4000, "swipes": 70, "spend": 6_000_000, "conversion_purchases": 2, "conversion_purchases_value": 50_000_000}}
                  for d in _days(params["start_time"], params["end_time"])]
        return _json({"request_status": "SUCCESS", "timeseries_stats": [{"timeseries_stat": {"id": cid, "timeseries": series}}]})
    if method == "GET" and p.count("/") == 1 and p.split("/")[1] in _objects:
        stored = _objects[p.split("/")[1]]
        return _json({"request_status": "SUCCESS", stored["key"]: [{"sub_request_status": "SUCCESS", stored["kind"]: stored["obj"]}]})
    if method == "DELETE":
        return _json({"request_status": "SUCCESS"})
    if p.startswith("targeting/geo/country"):
        return _json({"request_status": "SUCCESS", "targeting_dimensions": [{"country": {"country_code": "bd", "name": "Bangladesh"}}, {"country": {"country_code": "us", "name": "United States"}}]})
    if p.startswith("targeting/interests"):
        return _json({"request_status": "SUCCESS", "targeting_dimensions": [{"scls": {"id": "SLC_1", "name": "Fashion & Style Gurus"}}]})
    if p.startswith("targeting/demographics/languages"):
        return _json({"request_status": "SUCCESS", "targeting_dimensions": [{"languages": {"id": "en", "name": "English"}}]})
    if p.endswith("/segments"):
        return _json({"request_status": "SUCCESS", "segments": []})
    return _json({"request_status": "ERROR", "debug_message": f"Fake Snapchat: unknown path {p}"}, 404)


def _pinterest(request: httpx.Request, path: str) -> httpx.Response:
    if "pinterest-media-upload" in (request.url.host or ""):
        return httpx.Response(204)
    p = path.split("/v5/", 1)[-1]
    method = request.method
    currency = get_settings().META_FAKE_CURRENCY
    if p == "oauth/token":
        return _json({"access_token": "fake-pinterest-token"})
    if method == "GET" and p.startswith("ad_accounts/") and p.count("/") == 1:
        return _json({"id": p.split("/")[1], "name": "Fake Pinterest account", "currency": currency})
    if method in ("POST", "PATCH") and p.split("/")[-1] in ("campaigns", "ad_groups", "ads"):
        items = _body(request) or []
        return _json({"items": [{"data": {**i, "id": i.get("id") or _new_id()}, "exceptions": []} for i in items]})
    if method == "POST" and p == "pins":
        return _json({"id": _new_id()})
    if method == "DELETE" and p.startswith("pins/"):
        return httpx.Response(204)
    if method == "POST" and p == "media":
        return _json({"media_id": _new_id(), "upload_url": "https://pinterest-media-upload.s3-accelerate.amazonaws.com/", "upload_parameters": {"key": "fake"}})
    if p.startswith("resources/targeting/"):
        return _json([{"id": "BD", "name": "Bangladesh"}, {"id": "US", "name": "United States"}, {"id": "en-US", "name": "English (US)"}, {"id": "935541271955", "name": "Fashion"}])
    if p.endswith("/audiences"):
        return _json({"items": []})
    if p.endswith("campaigns/analytics"):
        params = dict(request.url.params)
        return _json([{"CAMPAIGN_ID": cid, "DATE": d, "SPEND_IN_MICRO_DOLLAR": 7_000_000, "IMPRESSION_1": 2500, "CLICKTHROUGH_1": 55,
                       "TOTAL_CONVERSIONS": 2, "TOTAL_CONVERSIONS_VALUE_IN_MICRO_DOLLAR": 40_000_000}
                      for cid in params["campaign_ids"].split(",") for d in _days(params["start_date"], params["end_date"])])
    return _json({"code": 404, "message": f"Fake Pinterest: unknown path {p}"}, 404)


def _x(request: httpx.Request, path: str) -> httpx.Response:
    host = request.url.host or ""
    method = request.method
    params = dict(request.url.params)
    currency = get_settings().META_FAKE_CURRENCY
    if host == "upload.x.com":
        form = _form(request)
        command = form.get("command") or params.get("command")
        if command == "INIT":
            return _json({"media_id_string": _new_id()})
        if command == "FINALIZE":
            return _json({"media_key": f"3_{_new_id()}"})
        return httpx.Response(204)
    if host == "api.x.com":
        return _json({"data": {"deleted": True}})
    p = path.split("/12/", 1)[-1]
    if p.endswith("/funding_instruments"):
        return _json({"data": [{"id": "fi1", "currency": currency, "entity_status": "ACTIVE"}]})
    if method == "GET" and p.startswith("accounts/") and p.count("/") == 1:
        return _json({"data": {"id": p.split("/")[1], "name": "Fake X ads account", "timezone": "Asia/Dhaka"}})
    if p.startswith("targeting_criteria/"):
        return _json({"data": [{"name": "Bangladesh", "targeting_value": "b3a9c9d2c1c1a1a1", "location_type": "COUNTRIES"}, {"name": "English", "targeting_value": "en"}]})
    if p.startswith("stats/accounts/"):
        n = (datetime.fromisoformat(params["end_time"].replace("Z", "+00:00")) - datetime.fromisoformat(params["start_time"].replace("Z", "+00:00"))).days
        return _json({"data": [{"id": cid, "id_data": [{"metrics": {"impressions": [1500] * n, "clicks": [30] * n, "billed_charge_local_micro": [5_000_000] * n}}]}
                               for cid in params["entity_ids"].split(",")]})
    if method == "POST" and p.endswith("/promoted_tweets"):
        return _json({"data": [{"id": _new_id(), "tweet_id": params.get("tweet_ids")}]})
    if method == "POST" and p.endswith("/tweet"):
        return _json({"data": {"id_str": _new_id()}})
    if method == "POST" and p.endswith("/cards"):
        return _json({"data": {"card_uri": f"card://{_new_id()}"}})
    if method == "POST":
        return _json({"data": {"id": _new_id(), **params}})
    if p.endswith("/custom_audiences"):
        return _json({"data": []})
    return _json({"data": {"id": p.rsplit("/", 1)[-1], **params}})


def _png(width: int, height: int, rgb: tuple[int, int, int] = (79, 70, 229)) -> bytes:
    """A real (viewable) solid-colour PNG for the image fakes."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    row = b"\x00" + bytes(rgb) * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


_RATIO_SIZE = {"1:1": (240, 240), "2:3": (200, 300), "3:2": (300, 200), "3:4": (210, 280), "4:3": (280, 210), "4:5": (200, 250),
               "5:4": (250, 200), "9:16": (180, 320), "16:9": (320, 180), "21:9": (420, 180)}


def _gemini_image(request: httpx.Request, path: str) -> httpx.Response:
    """SPEC-BE-070 image provider fake: Gemini image generation answers with a
    PNG in the requested aspect ratio (text Gemini calls don't come here)."""
    import base64

    body = _body(request) or {}
    ratio = ((body.get("generationConfig") or {}).get("imageConfig") or {}).get("aspectRatio") or "1:1"
    w, h = _RATIO_SIZE.get(ratio, (240, 240))
    data = base64.b64encode(_png(w, h)).decode()
    return _json({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": data}}]}}]})


def _example_page(request: httpx.Request, path: str) -> httpx.Response:
    """example.com (RFC 2606, reserved for examples) answers as a reachable
    landing page, for the Autopilot's landing-page check."""
    return httpx.Response(200, text="<html><body>Example landing page</body></html>", headers={"content-type": "text/html"})


# TikTok Content Posting API (SPEC-BE-075): a publish answers
# PROCESSING_UPLOAD for TIKTOK_POLLS status reads, then PUBLISH_COMPLETE.
TIKTOK_POLLS = 1
_tiktok_publishes: dict[str, int] = {}


def _tiktok_organic(request: httpx.Request, path: str) -> httpx.Response:
    ok = lambda data: _json({"data": data, "error": {"code": "ok", "message": ""}})  # noqa: E731
    if request.url.host == "open-upload.tiktokapis.com":
        return httpx.Response(201)
    if path.endswith("/oauth/token/"):
        # Social sign-in (SPEC-BE-080). TikTok answers a rejected grant with
        # HTTP 200 and an "error" field; code / refresh token "bad" does that.
        form = _form(request)
        if "bad" in (form.get("code"), form.get("refresh_token")):
            return _json({"error": "invalid_grant", "error_description": "Authorization code is expired.", "log_id": "fake"})
        return _json({"access_token": f"act.fake{_new_id()}", "expires_in": 86400, "open_id": "fake-open-id",
                      "refresh_token": f"rft.fake{_new_id()}", "refresh_expires_in": 31536000,
                      "scope": "user.info.basic,video.publish,video.upload,video.list", "token_type": "Bearer"})
    if path.endswith("/creator_info/query/"):
        return ok({"creator_username": "fake_tiktok", "creator_nickname": "Fake TikTok", "creator_avatar_url": "https://example.invalid/tt.jpg",
                   "privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
                   "comment_disabled": False, "duet_disabled": False, "stitch_disabled": True, "max_video_post_duration_sec": 600})
    if path.endswith("/video/init/") or path.endswith("/content/init/"):
        pid = f"v_pub_fake~{_new_id()}"
        _tiktok_publishes[pid] = TIKTOK_POLLS
        return ok({"publish_id": pid, "upload_url": f"https://open-upload.tiktokapis.com/video/?upload_id={pid}"})
    if path.endswith("/status/fetch/"):
        pid = (_body(request) or {}).get("publish_id", "")
        left = _tiktok_publishes.get(pid, 0)
        if left > 0:
            _tiktok_publishes[pid] = left - 1
            return ok({"status": "PROCESSING_UPLOAD"})
        return ok({"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [int(_new_id())]})
    if path.endswith("/video/query/"):
        ids = ((_body(request) or {}).get("filters") or {}).get("video_ids") or []
        return ok({"videos": [{"id": i, "like_count": 40, "comment_count": 5, "share_count": 2, "view_count": 1500} for i in ids]})
    return _json({"data": {}, "error": {"code": "invalid_params", "message": f"Fake TikTok organic: unknown path {path}"}}, 400)


# Video generation fakes (SPEC-BE-077): a started job answers "running" for
# VIDEO_POLLS status reads, then done with a tiny MP4.
VIDEO_POLLS = 1
_video_jobs: dict[str, int] = {}


def fake_mp4(seconds: int = 8, width: int = 720, height: int = 1280) -> bytes:
    import struct

    def box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", 8 + len(payload)) + kind + payload

    mvhd = box(b"mvhd", bytes(12) + struct.pack(">II", 1000, seconds * 1000) + bytes(80))
    tkhd = box(b"tkhd", bytes(76) + struct.pack(">II", width << 16, height << 16))
    return box(b"ftyp", b"isom" + bytes(8)) + box(b"moov", mvhd + box(b"trak", tkhd)) + box(b"mdat", bytes(64))


def _video_left(job: str) -> int:
    left = _video_jobs.get(job, 0)
    if left > 0:
        _video_jobs[job] = left - 1
    return left


def fake_embedding(text: str, dims: int) -> list[float]:
    """SPEC-BE-087: a deterministic hashed bag-of-words vector. Texts that
    share words are similar; it is not semantic (tests only)."""
    import hashlib

    vector = [0.0] * dims
    for word in re.findall(r"\w+", text.lower()):
        word = word[:-1] if len(word) > 3 and word.endswith("s") else word
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % dims] += 1.0 if digest[4] % 2 else -1.0
    return vector


def _embedding_api(request: httpx.Request, path: str) -> httpx.Response:
    """SPEC-BE-087: Voyage (/v1/embeddings), Mistral (/v1/embeddings, 1024
    dims) and Cohere (/v2/embed) embedding fakes."""
    body = _body(request) or {}
    host = request.url.host or ""
    if host == "api.cohere.com" and path == "/v2/embed":
        dims = int(body.get("output_dimension") or 1536)
        return _json({"id": "fake", "embeddings": {"float": [fake_embedding(str(t), dims) for t in body.get("texts") or []]}})
    if path == "/v1/embeddings":
        dims = 1024 if host == "api.mistral.ai" else int(body.get("output_dimension") or 1024)
        raw = body.get("input")
        texts: list[Any] = raw if isinstance(raw, list) else [raw or ""]
        return _json({"data": [{"index": i, "embedding": fake_embedding(str(t), dims)} for i, t in enumerate(texts)]})
    return _json({"error": {"message": f"Fake embeddings API: unknown path {path}"}}, 404)


# Voice commands (SPEC-BE-095): every speech-to-text fake answers this
# transcript (tests may change it); text-to-speech answers a short MP3 / PCM.
VOICE_TRANSCRIPT: dict[str, str] = {"text": "Show products low on stock", "language": "english"}
FAKE_MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 400


def _whisper_fake(request: httpx.Request, path: str) -> httpx.Response:
    return _json({"text": VOICE_TRANSCRIPT["text"], "language": VOICE_TRANSCRIPT["language"], "duration": 2.0})


def _openai(request: httpx.Request, path: str) -> httpx.Response:
    """Sora (/v1/videos), image generation/edit, embeddings and voice fakes."""
    import base64

    if path == "/v1/audio/transcriptions":
        return _whisper_fake(request, path)
    if path == "/v1/audio/speech":
        return httpx.Response(200, content=FAKE_MP3, headers={"content-type": "audio/mpeg"})
    if path == "/v1/embeddings":
        body = _body(request) or {}
        dims = int(body.get("dimensions") or 768)
        raw = body.get("input")
        texts: list[Any] = raw if isinstance(raw, list) else [raw or ""]
        return _json({"data": [{"index": i, "embedding": fake_embedding(str(t), dims)} for i, t in enumerate(texts)]})
    if path == "/v1/videos" and request.method == "POST":
        jid = f"video_fake{_new_id()}"
        _video_jobs[jid] = VIDEO_POLLS
        return _json({"id": jid, "object": "video", "status": "queued"})
    if path.startswith("/v1/videos/") and path.endswith("/content"):
        return httpx.Response(200, content=fake_mp4(8), headers={"content-type": "video/mp4"})
    if path.startswith("/v1/videos/"):
        jid = path.rsplit("/", 1)[1]
        return _json({"id": jid, "status": "in_progress" if _video_left(jid) > 0 else "completed", "progress": 50})
    if path in ("/v1/images/generations", "/v1/images/edits"):
        return _json({"data": [{"b64_json": base64.b64encode(_png(256, 256)).decode()}]})
    return _json({"error": {"message": f"Fake OpenAI: unknown path {path}"}}, 404)


def _gemini(request: httpx.Request, path: str) -> httpx.Response:
    """Gemini image generation (SPEC-BE-070), Veo video (SPEC-BE-077) and
    embeddings (SPEC-BE-087)."""
    if path.endswith(":batchEmbedContents"):
        reqs = (_body(request) or {}).get("requests") or []
        return _json({"embeddings": [
            {"values": fake_embedding(" ".join(p.get("text", "") for p in (r.get("content") or {}).get("parts") or []),
                                      int(r.get("outputDimensionality") or 768))}
            for r in reqs]})
    if path.endswith(":predictLongRunning"):
        op = f"models/veo-fake/operations/{_new_id()}"
        _video_jobs[op] = VIDEO_POLLS
        return _json({"name": op})
    if "/operations/" in path:
        op = path.split("/v1beta/", 1)[-1]
        if _video_left(op) > 0:
            return _json({"name": op, "done": False})
        uri = f"https://generativelanguage.googleapis.com/v1beta/files/fake{_new_id()}:download?alt=media"
        return _json({"name": op, "done": True, "response": {"generateVideoResponse": {"generatedSamples": [{"video": {"uri": uri}}]}}})
    if path.startswith("/v1beta/files/"):
        return httpx.Response(200, content=fake_mp4(8, 720, 1280), headers={"content-type": "video/mp4"})
    if path.endswith("-tts:generateContent"):  # SPEC-BE-095 voice reply: 16-bit PCM
        import base64

        pcm = base64.b64encode(b"\x00\x01" * 4800).decode()
        return _json({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000", "data": pcm}}]}}]})
    parts = (((_body(request) or {}).get("contents") or [{}])[0].get("parts")) or []
    if any(isinstance(p_, dict) and p_.get("inline_data") for p_ in parts):  # SPEC-BE-095 transcription
        text = json.dumps({"text": VOICE_TRANSCRIPT["text"], "language": "bn" if VOICE_TRANSCRIPT["language"] == "bengali" else "en"})
        return _json({"candidates": [{"content": {"parts": [{"text": text}]}}]})
    return _gemini_image(request, path)


# SocialAPI.ai (SPEC-BE-083): accounts, brands, connect (the auth_url points
# straight back at our redirect_uri, as a finished sign-in would), posts,
# media, metrics, analytics and the inbox. The key "sapi_key_bad" answers 401.
_sapi: dict[str, Any] = {}


def _sapi_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sapi_state() -> dict[str, Any]:
    if not _sapi:
        now = _sapi_now()
        _sapi.update({
            "brands": [],
            "accounts": [
                {"id": "acc_fake_ig", "platform": "instagram", "name": "Fake Shop", "username": "fakeshop", "status": "active"},
                {"id": "acc_fake_fb", "platform": "facebook", "name": "Fake Shop Page", "username": "fakeshop", "status": "active",
                 "page_name": "Fake Shop Page", "login_id": "login_fake_facebook"},
                {"id": "acc_fake_gbp", "platform": "google", "name": "Fake Shop Dhaka", "username": None, "status": "active"},
                {"id": "acc_fake_pin", "platform": "pinterest", "name": "Fake Shop Pins", "username": "fakeshoppins", "status": "active"},
            ],
            "posts": {},
            "conversations": [
                {"id": "conv_fake_1", "account_id": "acc_fake_ig", "platform": "instagram", "participant_name": "Sarah Ahmed",
                 "last_message": "Is the blue kurta available in M?", "last_message_at": now, "unread_count": 1, "status": "active"},
            ],
            "messages": {"conv_fake_1": [
                {"id": "msg_fake_1", "conversation_id": "conv_fake_1", "sender_name": "Sarah Ahmed", "direction": "inbound",
                 "text": "Is the blue kurta available in M?", "created_at": now, "status": "received"},
            ]},
            "commented": [
                {"id": "ip_fake_1", "platform_id": "17895695668004550", "account_id": "acc_fake_ig", "platform": "instagram",
                 "content": "New arrivals are here!", "comment_count": 1, "published_at": now,
                 "permalink": "https://www.instagram.com/p/fake/"},
            ],
            "comments": {"17895695668004550": [
                {"id": "sapi_cmt_fake1", "platform_id": "1789", "platform": "instagram", "text": "How much is shipping to Chittagong?",
                 "author_name": "Rafi", "author_username": "rafi.k", "created_at": now, "like_count": 0, "reply_count": 0,
                 "is_hidden": False, "is_owner": False,
                 "capabilities": {"can_reply": True, "can_delete": True, "can_hide": True, "can_like": True}},
            ]},
            "reviews": {"acc_fake_gbp": [
                {"id": "sapi_rev_fake1", "author": {"name": "Nadia"}, "rating": 5, "text": "Great quality and fast delivery!",
                 "created_at": now},
            ]},
        })
    return _sapi


def _sapi_post(body: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    now = _sapi_now()
    status = "published" if body.get("publish_now") else "scheduled" if body.get("scheduled_at") else "draft"
    accounts = {a["id"]: a for a in state["accounts"]}
    pid = f"post_fake_{_new_id()}"
    targets = []
    for t in body.get("targets") or []:
        acct = accounts.get(t.get("account_id"), {})
        target = {"account_id": t.get("account_id"), "platform": acct.get("platform"), "status": status,
                  "scheduled_at": body.get("scheduled_at")}
        if status == "published":
            ext = _new_id()
            target.update({"platform_post_id": ext, "published_at": now,
                           "permalink": f"https://example.com/{acct.get('platform')}/{ext}",
                           "metrics": {"likes": 3, "comments": 1, "shares": 0, "saves": 1}, "metrics_synced_at": now})
        targets.append(target)
    return {"id": pid, "status": status, "text": body.get("text"), "title": body.get("title"), "media": body.get("media") or [],
            "created_at": now, "updated_at": now, "scheduled_at": body.get("scheduled_at"),
            "published_at": now if status == "published" else None, "targets": targets}


def _socialapi(request: httpx.Request, path: str) -> httpx.Response:
    if request.headers.get("authorization") == "Bearer sapi_key_bad":
        return _json({"error": {"code": "auth.invalid_key", "message": "Invalid API key"}, "request_id": "fake"}, 401)
    st = _sapi_state()
    path = path.removeprefix("/v1")
    method, body = request.method, _body(request) or {}
    page = {"has_more": False, "next_cursor": ""}
    parts = path.strip("/").split("/")
    if path == "/accounts" and method == "GET":
        return _json({"count": len(st["accounts"]), "data": st["accounts"]})
    if path == "/brands":
        if method == "POST":
            brand = {"id": f"brand_fake_{_new_id()}", "name": body.get("name")}
            st["brands"].append(brand)
            return _json(brand, 201)
        return _json({"data": st["brands"]})
    if path == "/accounts/connect":
        platform = body.get("platform")
        q = {"platform": platform, "state": body.get("state", "")}
        if platform in ("facebook", "google"):
            cid = f"pc_fake_{_new_id()}"
            st.setdefault("pending", {})[cid] = platform
            q.update({"status": "selection_required", "connection_id": cid})
        else:
            acct = {"id": f"acc_fake_{_new_id()}", "platform": platform, "name": f"Fake {platform}", "username": "fake", "status": "active"}
            st["accounts"].append(acct)
            q.update({"status": "success", "account_id": acct["id"]})
        return _json({"auth_url": str(httpx.URL(body.get("redirect_uri", "http://localhost:3000/")).copy_merge_params(q))}, 202)
    if parts[:2] == ["accounts", "pending"] and len(parts) >= 3:
        platform = st.get("pending", {}).get(parts[2])
        if platform is None:  # unknown, used or expired (single-use, 30 minutes)
            return _json({"error": {"code": "resource.not_found", "message": "Pending connection not found"}}, 404)
        if method == "GET":
            if platform == "facebook":
                return _json({"connection_id": parts[2], "platform": platform, "login_id": "login_fake_facebook", "lost_access": [],
                              "pages": [{"platform_page_id": "fake-1", "name": "Fake facebook one", "category": "Shopping", "assignable": True},
                                        {"platform_page_id": "fake-2", "name": "Fake facebook two", "category": "Shopping", "assignable": True}]})
            return _json({"connection_id": parts[2], "platform": platform, "login_id": "login_fake_google",
                          "profiles": [{"platform_account_id": "accounts/1/locations/fake-1", "display_name": "Fake google one"},
                                       {"platform_account_id": "accounts/1/locations/fake-2", "display_name": "Fake google two"}]})
        st["pending"].pop(parts[2])
        name = f"Fake {platform} page"
        acct = {"id": f"acc_fake_{_new_id()}", "platform": platform, "name": name, "status": "active",
                "page_name": name if platform == "facebook" else None, "login_id": f"login_fake_{platform}"}
        st["accounts"].append(acct)
        return _json({"account_id": acct["id"], "display_name": name, "platform": platform, "username": ""}, 201)
    if parts[:1] == ["platforms"] and len(parts) >= 5:
        platform, kind = parts[1], parts[4]
        if method == "GET":
            id_field = "platform_page_id" if kind == "pages" else "platform_account_id"
            return _json({"count": 2, "login_id": parts[3], kind: [
                {"name": f"Fake {platform} one", id_field: "fake-1", "category": "Shopping", "assignable": True},
                {"name": f"Fake {platform} two", id_field: "fake-2", "category": "Shopping", "assignable": True},
            ]})
        same_login = next((a for a in st["accounts"] if a.get("login_id") == parts[3]), None)
        if same_login is not None:  # a Page chosen for an already connected login
            same_login["page_name"] = f"Fake {platform} {'one' if parts[5] == 'fake-1' else 'two'}"
            return _json({"account_id": same_login["id"], "brand_id": body.get("brand_id"), "platform_page_id": parts[5]}, 201)
        acct = {"id": f"acc_fake_{_new_id()}", "platform": platform, "name": f"Fake {platform} page", "status": "active"}
        st["accounts"].append(acct)
        return _json({"account_id": acct["id"], "brand_id": body.get("brand_id")}, 201)
    if parts[0] == "accounts" and len(parts) >= 2:
        if method == "DELETE":
            st["accounts"] = [a for a in st["accounts"] if a["id"] != parts[1]]
            return httpx.Response(204)
        if parts[-1] == "boards":
            return _json({"data": [{"id": "brd_fake_1", "board_id": "9001", "name": "Summer looks", "privacy": "PUBLIC"}]})
        if parts[-1] == "analytics":
            params = dict(request.url.params)
            days = _days(params.get("from") or date.today().isoformat(), params.get("to") or date.today().isoformat())
            return _json({"data": {"from": days[0], "to": days[-1], "series": [
                {"metric": "followers", "kind": "gauge", "points": [{"day": d, "value": 1200 + i} for i, d in enumerate(days)]},
                {"metric": "impressions", "kind": "counter", "points": [{"day": d, "value": 300 + 7 * i} for i, d in enumerate(days)]},
            ]}})
    if path == "/media/upload":
        return _json({"media_id": f"med_fake_{_new_id()}"}, 201)
    if path == "/media/upload-url":
        mid = f"med_fake_{_new_id()}"
        return _json({"media_id": mid, "upload_url": f"https://api.social-api.ai/v1/fake-storage/{mid}",
                      "expires_at": _sapi_now()})
    if parts[0] == "fake-storage" and method == "PUT":
        return httpx.Response(200)
    if parts[0] == "media" and parts[-1] == "verify":
        return _json({"success": True})
    if path == "/posts/validate" and method == "GET":
        return _json({"data": {
            "instagram": {"text": {"max_length": 2200}, "carousel": {"supported": True, "max_items": 10},
                          "media": {"max_video_duration_sec": 900}, "scheduling": {"supported": True}},
            "facebook": {"text": {"max_length": 63206}, "carousel": {"supported": True, "max_items": 10},
                         "media": {"max_video_duration_sec": 14400}, "scheduling": {"supported": True}},
        }})
    if path == "/posts":
        if method == "POST":
            post = _sapi_post(body, st)
            st["posts"][post["id"]] = post
            return _json(post, 201)
        items = sorted(st["posts"].values(), key=lambda p: p["created_at"], reverse=True)
        wanted = request.url.params.get("status")
        return _json({"data": [p for p in items if not wanted or p["status"] == wanted], "pagination": page})
    if parts[0] == "posts" and len(parts) >= 2:
        post = st["posts"].get(parts[1])
        if post is None:
            return _json({"error": {"code": "post.not_found", "message": "Post not found"}}, 404)
        if method == "DELETE":
            st["posts"].pop(parts[1])
            return _json({"success": True, "results": [{"account_id": t["account_id"], "status": "deleted"} for t in post["targets"]]})
        if parts[-1] in ("publish", "retry"):
            published = _sapi_post({**post, "publish_now": True, "targets": post["targets"]}, st)
            post.update({k: published[k] for k in ("status", "published_at", "targets")})
            return _json(post if parts[-1] == "publish" else {"success": True}, 201 if parts[-1] == "publish" else 200)
        if parts[-1] == "metrics":
            return _json({"data": {"post_id": post["id"], "targets": post["targets"]}})
        return _json(post)
    if path == "/inbox/conversations":
        return _json({"data": st["conversations"], "pagination": page, "sync_state": "idle"})
    if parts[:2] == ["inbox", "conversations"] and parts[-1] == "messages":
        thread = st["messages"].setdefault(parts[2], [])
        if method == "POST":
            mid = f"msg_fake_{_new_id()}"
            thread.append({"id": mid, "direction": "outbound", "text": body.get("text"), "sender_name": "You",
                           "created_at": _sapi_now(), "status": "sent"})
            return _json({"success": True, "message_ids": [mid]})
        return _json({"data": list(reversed(thread)), "pagination": page})
    if path == "/inbox/comments":
        return _json({"data": st["commented"], "pagination": page})
    if parts[:2] == ["inbox", "comments"] and len(parts) >= 3:
        thread = st["comments"].setdefault(parts[2], [])
        if len(parts) == 3 and method == "POST":
            cid = f"sapi_cmt_fake{_new_id()}"
            thread.append({"id": cid, "text": body.get("text"), "author_name": "You", "parent_id": body.get("comment_id"),
                           "is_owner": True, "created_at": _sapi_now()})
            return _json({"success": True, "comment_id": cid})
        if len(parts) == 3:
            return _json({"data": thread, "pagination": page})
        for c in thread:
            if c["id"] == parts[3] and len(parts) == 5:
                c["is_hidden"] = parts[4] == "hide"
        if method == "DELETE":
            st["comments"][parts[2]] = [c for c in thread if c["id"] != parts[3]]
        return _json({"success": True})
    if parts[:2] == ["inbox", "reviews"] and len(parts) >= 3:
        if parts[-1] == "reply":
            for rows in st["reviews"].values():
                for r in rows:
                    if r["id"] == parts[2]:
                        r["reply"] = {"text": body.get("text"), "state": "PENDING"}
            return _json({"success": True, "reply_id": f"r_{_new_id()}", "state": "PENDING"})
        rows = st["reviews"].get(parts[2], [])
        return _json({"data": rows, "pagination": page,
                      "summary": {"average_rating": 5.0 if rows else None, "total_count": len(rows)}})
    return _json({"error": {"code": "fake.unknown", "message": f"Fake SocialAPI: no fixture for {method} {path}"}}, 404)


# Zernio (SPEC-BE-084): profiles, accounts, connect (the authUrl points straight
# back at our redirect_url, as a finished hosted sign-in would, and the account
# exists at once), ad accounts, identities, targeting, reach, media, create /
# validate / preview / boost (Idempotency-Key replays), the campaign tree,
# status, update, delete and analytics. The key "zernio_bad" answers 401.
_zer: dict[str, Any] = {}
_ZER_ADS_KIND = {"facebook": "metaads", "instagram": "metaads", "tiktok": "tiktokads", "linkedin": "linkedinads",
                 "pinterest": "pinterestads", "twitter": "xads", "googleads": "googleads"}
_ZER_TREE = {"metaads": None, "tiktokads": "tiktok", "linkedinads": "linkedin", "pinterestads": "pinterest",
             "xads": "twitter", "googleads": "google"}


def _zer_state() -> dict[str, Any]:
    if not _zer:
        _zer.update({"profiles": [], "accounts": [], "campaigns": [], "idem": {}})
    return _zer


def _zer_hex() -> str:
    return f"{int(_new_id()):024x}"


def _zer_metrics(seed: int) -> dict[str, Any]:
    return {"spend": round(12.5 + seed, 2), "impressions": 1000 + 10 * seed, "reach": 800 + seed, "clicks": 40 + seed,
            "ctr": 4.0, "cpc": 0.31, "cpm": 12.5, "conversions": 3}


def _zernio(request: httpx.Request, path: str) -> httpx.Response:
    if request.headers.get("authorization") == "Bearer zernio_bad":
        return _json({"error": "Invalid API key", "type": "authentication_error"}, 401)
    st = _zer_state()
    path = path.removeprefix("/api/v1")
    method, body, params = request.method, _body(request) or {}, dict(request.url.params)
    parts = path.strip("/").split("/")
    idem = request.headers.get("idempotency-key")
    if idem and method == "POST" and (method, path, idem) in st["idem"]:
        status, answer = st["idem"][(method, path, idem)]
        return _json(answer, status)

    def remember(status: int, answer: dict[str, Any]) -> httpx.Response:
        if idem:
            st["idem"][(method, path, idem)] = (status, answer)
        return _json(answer, status)

    if path == "/profiles":
        if method == "POST":
            if any(p["name"] == body.get("name") for p in st["profiles"]):
                existing = next(p for p in st["profiles"] if p["name"] == body.get("name"))
                return _json({"error": "A profile with this name already exists", "type": "invalid_request_error",
                              "details": {"existingProfileId": existing["_id"]}}, 409)
            profile = {"_id": _zer_hex(), "name": body.get("name"), "timezone": body.get("timezone")}
            st["profiles"].append(profile)
            return remember(201, {"message": "Profile created", "profile": profile})
        return _json({"profiles": st["profiles"], "total": len(st["profiles"])})
    if path == "/accounts" and method == "GET":
        rows = [a for a in st["accounts"] if not params.get("profileId") or a["profileId"] == params["profileId"]]
        return _json({"accounts": rows, "hasAnalyticsAccess": True})
    if parts[0] == "connect" and method == "GET":
        platform, ads = parts[1], len(parts) > 2 and parts[2] == "ads"
        kind = _ZER_ADS_KIND.get(platform, platform) if ads else platform
        pid = params.get("profileId")
        existing = next((a for a in st["accounts"] if a["profileId"] == pid and a["platform"] == kind), None)
        if existing is not None and ads:
            return _json({"alreadyConnected": True, "accountId": existing["_id"], "platform": kind})
        acct = {"_id": _zer_hex(), "platform": kind, "profileId": pid, "username": f"fake_{platform}",
                "displayName": f"Fake {platform}{' ads' if ads else ''}", "isActive": True, "needsReconnection": False,
                "parentAccountId": params.get("accountId")}
        st["accounts"].append(acct)
        back = {"connected": kind, "profileId": pid, "accountId": acct["_id"], "username": acct["username"]}
        target = str(httpx.URL(params.get("redirect_url", "http://localhost:3000/")).copy_merge_params(back))
        return _json({"authUrl": target, "state": "fake"})
    if parts[0] == "accounts" and len(parts) == 2 and method == "DELETE":
        before = len(st["accounts"])
        st["accounts"] = [a for a in st["accounts"] if a["_id"] != parts[1]]
        return _json({"message": "Disconnected"}) if len(st["accounts"]) < before else _json({"error": "Account not found"}, 404)
    if parts[0] == "accounts" and len(parts) == 3 and parts[2] == "posts":
        return _json({"status": "success", "posts": [
            {"id": "post_fake_1", "platform": "facebook", "message": "Eid collection is live!", "createdTime": "2026-10-01T10:00:00Z",
             "permalink": "https://example.com/p/1", "mediaType": "image"},
            {"id": "post_fake_2", "platform": "facebook", "message": "Free delivery this week", "createdTime": "2026-10-03T10:00:00Z",
             "permalink": "https://example.com/p/2", "mediaType": "video"}]})
    if path == "/ads/accounts":
        currency = get_settings().META_FAKE_CURRENCY
        return _json({"accounts": [
            {"id": "act_fake_1", "name": "Fake Shop Ads", "currency": currency, "timezoneName": "Asia/Dhaka",
             "status": "ACTIVE", "selectable": True, "minimumDailyBudget": 1, "businessName": "Fake Shop"},
            {"id": "act_fake_blocked", "name": "Old account", "currency": currency, "timezoneName": "Asia/Dhaka",
             "status": "DISABLED", "selectable": False, "unusableReason": ["No payment method"]}], "stale": False})
    if path == "/ads/instagram-accounts":
        return _json({"accounts": [], "pages": [{"pageId": "pg_fake_1", "name": "Fake Shop Page",
                                                  "instagramBusinessAccount": {"id": "ig_fake_1", "username": "fakeshop"}}],
                      "resolved": {"pageId": "pg_fake_1", "igUserId": "ig_fake_1", "source": "page"}})
    if path == "/ads/tiktok-identities":
        return _json({"adAccountId": params.get("adAccountId"), "identities": [
            {"identityId": "tt_id_1", "identityType": "CUSTOMIZED_USER", "displayName": "Fake Shop", "username": "fakeshop"}]})
    if path == "/ads/targeting/search":
        q, dim = params.get("q", ""), params.get("dimension", "geo")
        if dim == "interest":
            rows = [{"id": "6003107902433", "name": f"{q.title()} (interest)", "type": "interests", "audienceSize": 1200000}]
        elif dim == "behavior":
            rows = [{"id": "6002714895372", "name": "Frequent Travelers", "type": "behaviors"}]
        else:
            rows = [{"id": "2295", "name": q.title() or "Dhaka", "type": "city", "countryCode": "BD", "path": ["Bangladesh", "Dhaka"]},
                    {"id": "BD", "name": "Bangladesh", "type": "country", "countryCode": "BD"}]
        return _json({"results": rows})
    if path == "/ads/targeting/reach-estimate":
        kind = next((a["platform"] for a in st["accounts"] if a["_id"] == body.get("accountId")), "")
        if kind in ("tiktokads", "googleads"):
            return _json({"available": False, "lower": None, "upper": None})
        return _json({"available": True, "lower": 120000, "upper": 350000, "daily": 9000})
    if path == "/ads/images":
        return _json({"adAccountId": body.get("adAccountId"), "image": {"hash": "fakehash", "url": "https://scontent.example.com/fake.jpg"}}, 201)
    if path == "/ads/preview":
        return _json({"previews": [{"format": f, "html": f'<iframe src="https://www.facebook.com/ads/api/preview_iframe.php?d=fake&amp;t={f}" width="540" height="690"></iframe>'}
                                   for f in body.get("formats") or []]})
    if path in ("/ads/create", "/ads/boost") and method == "POST":
        account = next((a for a in st["accounts"] if a["_id"] == body.get("accountId")), None)
        if account is None:
            return _json({"error": "Account not found", "type": "not_found"}, 404)
        if body.get("validateOnly"):
            if "rejectme" in str(body.get("name", "")):
                return _json({"error": "Fake Meta: the headline breaks policy", "type": "platform_error"}, 400)
            return _json({"validateOnly": True, "results": [{"node": n, "status": "ok"} for n in ("campaign", "adSet", "creative", "ad")]})
        kind = account["platform"]
        # A posting account (boost) is its own platform; a metaads account reports facebook.
        platform = kind if kind in ("facebook", "instagram", "tiktok", "linkedin", "pinterest", "twitter") \
            else _ZER_TREE.get(kind) or "facebook"
        n = int(_new_id())
        cid, sid, aid = f"{9000 + n}", f"{19000 + n}", f"{29000 + n}"
        status = "paused" if body.get("status") == "PAUSED" else "active"
        budget = {"amount": body.get("budgetAmount"), "type": body.get("budgetType")}
        ad = {"_id": _zer_hex(), "platformAdId": aid, "name": body.get("adName") or body.get("name"), "status": status,
              "reviewStatus": "in_review", "metrics": _zer_metrics(n)}
        campaign = {"platformCampaignId": cid, "platform": platform, "campaignName": body.get("campaignName") or f"{body.get('name')} - Campaign",
                    "createdTime": _sapi_now(), "status": status, "reviewStatus": "in_review", "budget": budget,
                    "currency": get_settings().META_FAKE_CURRENCY, "metrics": _zer_metrics(n),
                    "platformAdAccountId": body.get("adAccountId"), "platformAdAccountName": "Fake Shop Ads",
                    "accountId": account["_id"], "profileId": account["profileId"], "platformObjective": body.get("goal"),
                    "adSets": [{"platformAdSetId": sid, "adSetName": body.get("adSetName") or f"{body.get('name')} - Ad Set",
                                "status": "active", "adSetBudget": budget, "metrics": _zer_metrics(n), "ads": [ad]}],
                    "_request": body}
        st["campaigns"].append(campaign)
        return remember(201, {"ad": {**ad, "platform": platform, "platformCampaignId": cid, "platformAdSetId": sid,
                                     "adType": "boost" if path == "/ads/boost" else "standalone", "goal": body.get("goal"),
                                     "budget": budget}})
    if path == "/ads/tree":
        rows = [c for c in st["campaigns"] if c["profileId"] == params.get("profileId")]
        if params.get("platform"):
            rows = [c for c in rows if c["platform"] == params["platform"]]
        if params.get("status"):
            rows = [c for c in rows if c["status"] == params["status"]]
        if params.get("campaignId"):
            wanted = set(params["campaignId"].split(","))
            rows = [c for c in rows if c["platformCampaignId"] in wanted]
        if params.get("search"):
            q = params["search"].lower()
            rows = [c for c in rows if q in (c["campaignName"] or "").lower() or q == c["platformCampaignId"]
                    or any(q == s_["platformAdSetId"] or any(q in (a["platformAdId"], a["_id"]) for a in s_["ads"]) for s_ in c["adSets"])]
        out = [{k: v for k, v in c.items() if k != "_request"} for c in reversed(rows)]
        return _json({"campaigns": out, "pagination": {"page": 1, "limit": 20, "total": len(out), "pages": 1},
                      "backfillPending": False})

    def find_campaign(cid: str) -> dict[str, Any] | None:
        return next((c for c in st["campaigns"] if c["platformCampaignId"] == cid), None)

    if parts[:2] == ["ads", "campaigns"] and len(parts) >= 3:
        found = find_campaign(parts[2])
        if found is None:
            return _json({"error": "Campaign not found", "type": "not_found"}, 404)
        campaign = found
        if len(parts) == 4 and parts[3] == "status":
            campaign["status"] = body.get("status")
            return _json({"status": body.get("status"), "platformCampaignStatus": body.get("status", "").upper(), "updated": 1, "skipped": 0})
        if len(parts) == 4 and parts[3] == "analytics":
            days = _days((date.today() - timedelta(days=6)).isoformat(), date.today().isoformat())
            breakdowns = {}
            for dim in (params.get("breakdowns") or "").split(","):
                if dim == "age":
                    breakdowns["age"] = [{"value": "18-24", "spend": 4.0, "impressions": 300, "clicks": 12},
                                         {"value": "25-34", "spend": 8.5, "impressions": 700, "clicks": 28}]
                elif dim == "gender":
                    breakdowns["gender"] = [{"value": "female", "spend": 7.0, "impressions": 600, "clicks": 25}]
            return _json({"backfillPending": False, "campaign": {"id": parts[2], "name": campaign["campaignName"],
                                                                  "platform": campaign["platform"], "currency": campaign["currency"]},
                          "analytics": {"summary": campaign["metrics"],
                                        "daily": [{"date": d, "spend": 1.5 + i, "impressions": 100 + i, "clicks": 4 + i}
                                                  for i, d in enumerate(days)], "breakdowns": breakdowns}})
        if len(parts) == 3 and method == "PUT":
            if body.get("name"):
                campaign["campaignName"] = body["name"]
            if body.get("budget"):
                campaign["budget"] = body["budget"]
            return _json({"updated": True})
        if len(parts) == 3 and method == "DELETE":
            st["campaigns"] = [c for c in st["campaigns"] if c is not campaign]
            return _json({"deleted": True, "adCount": sum(len(s_["ads"]) for s_ in campaign["adSets"])})
    if parts[:2] == ["ads", "ad-sets"] and len(parts) == 4 and parts[3] == "status":
        for c in st["campaigns"]:
            for s_ in c["adSets"]:
                if s_["platformAdSetId"] == parts[2]:
                    s_["status"] = body.get("status")
                    return _json({"status": body.get("status"), "updated": 1, "skipped": 0})
        return _json({"error": "Ad set not found", "type": "not_found"}, 404)
    if parts[0] == "ads" and len(parts) == 3 and parts[2] == "status":
        for c in st["campaigns"]:
            for s_ in c["adSets"]:
                for a in s_["ads"]:
                    if parts[1] in (a["platformAdId"], a["_id"]):
                        a["status"] = body.get("status")
                        return _json({"updated": 1, "skipped": 0, "status": body.get("status"), "configuredStatus": body.get("status", "").upper()})
        return _json({"error": "Ad not found", "type": "not_found"}, 404)
    return _json({"error": f"Fake Zernio: no fixture for {method} {path}", "type": "not_found"}, 404)


_AD_HOSTS = (
    ("zernio.com", "zernio", _zernio),
    ("api.social-api.ai", "socialapi", _socialapi),
    ("generativelanguage.googleapis.com", "gemini", _gemini),
    ("api.openai.com", "openai", _openai),
    ("api.groq.com", "groq", _whisper_fake),  # SPEC-BE-095 voice transcription
    ("api.voyageai.com", "voyage", _embedding_api), ("api.mistral.ai", "mistral", _embedding_api),
    ("api.cohere.com", "cohere", _embedding_api),
    ("open.tiktokapis.com", "tiktok_organic", _tiktok_organic), ("open-upload.tiktokapis.com", "tiktok_organic", _tiktok_organic),
    ("example.com", "example", _example_page), ("shop.example.com", "example", _example_page), ("www.example.com", "example", _example_page),
    ("business-api.tiktok.com", "tiktok", _tiktok), ("googleads.googleapis.com", "google", _google), ("oauth2.googleapis.com", "google", _google),
    ("api.linkedin.com", "linkedin", _linkedin), ("www.linkedin.com", "linkedin", _linkedin),
    ("adsapi.snapchat.com", "snapchat", _snap), ("accounts.snapchat.com", "snapchat", _snap),
    ("api.pinterest.com", "pinterest", _pinterest), ("pinterest-media-upload.s3-accelerate.amazonaws.com", "pinterest", _pinterest),
    ("ads-api.x.com", "x", _x), ("upload.x.com", "x", _x), ("api.x.com", "x", _x),
)
_FAIL_ANSWER = {
    "tiktok": lambda: _json({"code": 40002, "message": "Fake TikTok: rejected by the injected failure (invalid parameter)"}),
    "google": lambda: _json({"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "Request contains an invalid argument.",
                                       "details": [{"errors": [{"message": "Fake Google: rejected by the injected failure",
                                                                "location": {"fieldPathElements": [{"fieldName": "mutate_operations", "index": 3}]}}]}]}}, 400),
    "linkedin": lambda: _json({"message": "Fake LinkedIn: rejected by the injected failure", "status": 422}, 422),
    "snapchat": lambda: _json({"request_status": "ERROR", "debug_message": "Fake Snapchat: rejected by the injected failure"}, 400),
    "pinterest": lambda: _json({"code": 2, "message": "Fake Pinterest: rejected by the injected failure"}, 400),
    "x": lambda: _json({"errors": [{"message": "Fake X: rejected by the injected failure"}]}, 400),
    "tiktok_organic": lambda: _json({"data": {}, "error": {"code": "spam_risk_too_many_posts", "message": "Fake TikTok: rejected by the injected failure"}}, 403),
    "openai": lambda: _json({"error": {"message": "Fake OpenAI: rejected by the injected failure"}}, 400),
    "gemini": lambda: _json({"error": {"message": "Fake Gemini: rejected by the injected failure"}}, 400),
    "groq": lambda: _json({"error": {"message": "Fake Groq: rejected by the injected failure"}}, 400),
    "voyage": lambda: _json({"detail": "Fake Voyage: rejected by the injected failure"}, 400),
    "mistral": lambda: _json({"message": "Fake Mistral: rejected by the injected failure"}, 400),
    "cohere": lambda: _json({"message": "Fake Cohere: rejected by the injected failure"}, 400),
    "socialapi": lambda: _json({"error": {"code": "validation.failed", "message": "Fake SocialAPI: rejected by the injected failure"}}, 400),
    "zernio": lambda: _json({"error": "Fake Zernio: rejected by the injected failure", "type": "invalid_request_error"}, 400),
}
# Meta Graph (ads and organic) failure injection: FAIL["meta"] = path
# fragment; the answer uses META_FAIL_ERROR (code 2 = transient, 190 = expired
# token, 100 = permanent; HTTP status alongside).
META_FAIL_ERROR: dict[str, int] = {"code": 100, "status": 400}


def ad_platform_handler(request: httpx.Request) -> httpx.Response | None:
    host = request.url.host or ""
    for suffix, platform, handler in _AD_HOSTS:
        if host == suffix:
            path = request.url.path
            CALLS.append((platform, request.method, f"{path}?{request.url.query.decode()}" if request.url.query else path))
            if FAIL.get(platform) and FAIL[platform] in str(request.url) and request.method in ("POST", "PUT", "PATCH"):
                if FAIL_SKIP.get(platform, 0) > 0:
                    FAIL_SKIP[platform] -= 1
                else:
                    return _FAIL_ANSWER[platform]()
            return handler(request, path)
    return None


def _handler(request: httpx.Request) -> httpx.Response:
    platform_answer = ad_platform_handler(request)
    if platform_answer is not None:
        return platform_answer
    host = request.url.host or ""
    if host.endswith("facebook.com"):
        CALLS.append(("meta", request.method, str(request.url.path)))
        if FAIL.get("meta") and FAIL["meta"] in str(request.url) and request.method in ("POST", "PUT"):
            if FAIL_SKIP.get("meta", 0) > 0:
                FAIL_SKIP["meta"] -= 1
            else:
                code = META_FAIL_ERROR["code"]
                return _json({"error": {"message": "Fake Meta: rejected by the injected failure", "code": code,
                                        "is_transient": code in (1, 2)}}, META_FAIL_ERROR["status"])
        return _meta(request)
    if host.endswith("myshopify.com") or "/admin/" in request.url.path:
        return _shopify(request)
    if "/wp-json/" in request.url.path:
        return _woo(request)
    return _json({"error": "Fake transport: unknown host"}, 404)


def install() -> None:
    """Swaps the HTTP client factories (and the SSRF DNS check, which would
    otherwise resolve fake hosts) for the in-process fixtures."""
    from app.ai import embeddings
    from app.integrations import base_adapter, meta_ads, verify

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(_handler), timeout=20.0)

    meta_ads.client_factory = factory
    verify.client_factory = factory
    base_adapter.client_factory = factory  # every ad platform adapter
    embeddings.client_factory = factory  # SPEC-BE-087 knowledge embeddings
    verify._require_public_host = lambda host: None
    logger.warning("dev_fake_transport_enabled", note="Meta/Shopify/WooCommerce and ad platform calls are answered by fixtures")
