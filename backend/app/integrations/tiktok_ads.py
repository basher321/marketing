"""TikTok Ads adapter (SPEC-BE-063): TikTok API for Business v1.3.

Every response is {code, message, data}; code != 0 is an error even on HTTP
200. Money is sent in the ad account's currency (major units). Times are sent
as "YYYY-MM-DD HH:MM:SS" in UTC. Field names follow the v1.3 docs as of
2026-10; they're kept in one place here so a version bump is one edit.
"""
import hashlib
from datetime import datetime, timezone
from typing import Any

from app.integrations.base_adapter import PlatformError, Rollback, http, ids, issue, short, unresolved

BASE = "https://business-api.tiktok.com/open_api/v1.3"
# Token invalid / expired / revoked -> reconnect; 40100 = too many requests.
AUTH_CODES = {40102, 40104, 40105}
RATE_LIMIT_CODE = 40100

# objective -> (default optimisation goal, billing event, promotion type)
OBJECTIVES: dict[str, tuple[str, str, str]] = {
    "REACH": ("REACH", "CPM", "WEBSITE"),
    "TRAFFIC": ("CLICK", "CPC", "WEBSITE"),
    "VIDEO_VIEWS": ("ENGAGED_VIEW", "CPV", "WEBSITE"),
    "ENGAGEMENT": ("FOLLOWERS", "OCPM", "WEBSITE"),
    "LEAD_GENERATION": ("LEAD_GENERATION", "OCPM", "LEAD_GENERATION"),
    "APP_PROMOTION": ("INSTALL", "OCPM", "APP_ANDROID"),
    "WEB_CONVERSIONS": ("CONVERT", "OCPM", "WEBSITE"),
}
AGE_BUCKETS = ((13, 17, "AGE_13_17"), (18, 24, "AGE_18_24"), (25, 34, "AGE_25_34"), (35, 44, "AGE_35_44"), (45, 54, "AGE_45_54"), (55, 100, "AGE_55_100"))
CTA = {"LEARN_MORE", "SHOP_NOW", "SIGN_UP", "DOWNLOAD", "CONTACT_US", "ORDER_NOW", "BOOK_NOW", "APPLY_NOW"}
# Minimum daily budgets in USD; other currencies are checked by TikTok itself.
MIN_CAMPAIGN_DAILY_USD = 50
MIN_GROUP_DAILY_USD = 20


def _call(conn: dict[str, Any], method: str, path: str, **kwargs: Any) -> Any:
    token = conn["fields"].get("access_token", "")
    resp = http(method, f"{BASE}/{path}", headers={"Access-Token": token}, **kwargs)
    try:
        body = resp.json()
    except ValueError:
        raise PlatformError(f"TikTok answered HTTP {resp.status_code}.", 502) from None
    code = body.get("code")
    if resp.status_code >= 400 or code not in (0, None):
        message = short(body.get("message") or body)
        auth = code in AUTH_CODES or resp.status_code == 401
        status = 409 if auth else 429 if code == RATE_LIMIT_CODE or resp.status_code == 429 else 502
        raise PlatformError(f"TikTok: {message}", status, auth=auth)
    return body.get("data") or {}


def _adv(conn: dict[str, Any]) -> str:
    return str(conn["fields"].get("advertiser_id", ""))


def verify_account(fields: dict[str, str]) -> dict[str, Any]:
    data = _call({"fields": fields}, "GET", "advertiser/info/", params={"advertiser_ids": f'["{fields["advertiser_id"]}"]'})
    items = data.get("list") or []
    if not items:
        raise PlatformError("TikTok returned no advertiser for that ID.", 404)
    return {"name": items[0].get("name"), "currency": items[0].get("currency"), "timezone": items[0].get("timezone")}


def _when(iso: str | None) -> str | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ages(t: dict[str, Any]) -> list[str]:
    lo, hi = t.get("age_min"), t.get("age_max")
    if lo is None and hi is None:
        return []
    lo, hi = int(lo or 13), int(hi or 100)
    return [name for a, b, name in AGE_BUCKETS if b >= lo and a <= (100 if hi >= 65 else hi)]


def _gender(t: dict[str, Any]) -> str:
    g = set(t.get("genders") or [])
    return "GENDER_FEMALE" if g == {"female"} else "GENDER_MALE" if g == {"male"} else "GENDER_UNLIMITED"


def _budget(mode: str, amount: float | None) -> dict[str, Any]:
    if mode == "daily" and amount:
        return {"budget_mode": "BUDGET_MODE_DAY", "budget": amount}
    if mode == "total" and amount:
        return {"budget_mode": "BUDGET_MODE_TOTAL", "budget": amount}
    return {"budget_mode": "BUDGET_MODE_INFINITE"}


# ---------------------------------------------------------------------------
# Validation (on top of the builder's generic checks)
# ---------------------------------------------------------------------------
def validate(conn: dict[str, Any], tree: dict[str, Any]) -> list[dict[str, Any]]:
    out = unresolved(tree, ("locations", "languages", "interests", "audiences"), "TikTok")
    c = tree["campaign"]
    objective = c["objective"]
    try:
        account = verify_account(conn["fields"])
    except PlatformError as exc:
        return out + [issue("campaign", c["id"], "connection", exc.message)]
    if account.get("currency") and account["currency"] != c["currency"]:
        out.append(issue("campaign", c["id"], "campaign.currency", f"Your TikTok ad account bills in {account['currency']}, but this campaign is in {c['currency']}."))
    usd = c["currency"] == "USD"
    if usd and c["budget_mode"] == "daily" and (c["budget"] or 0) < MIN_CAMPAIGN_DAILY_USD:
        out.append(issue("campaign", c["id"], "campaign.budget", f"TikTok's minimum campaign daily budget is {MIN_CAMPAIGN_DAILY_USD} USD."))
    for gi, g in enumerate(tree["groups"]):
        f = g["fields"]
        if usd and g["budget_mode"] == "daily" and (g["budget"] or 0) < MIN_GROUP_DAILY_USD:
            out.append(issue("group", g["id"], f"groups[{gi}].budget", f"TikTok's minimum ad group daily budget is {MIN_GROUP_DAILY_USD} USD."))
        if objective == "WEB_CONVERSIONS" and not (f.get("pixel_id") and f.get("optimization_event")):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.pixel_id", "Website conversions need a TikTok pixel ID and an optimisation event."))
        if objective == "APP_PROMOTION" and not f.get("app_id"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.app_id", "App promotion needs an app ID."))
        if f.get("bid_strategy") in ("COST_CAP", "BID_CAP") and not f.get("bid_amount"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.bid_amount", "Set a bid amount for a cost or bid cap."))
        if f.get("placement") == "SELECT" and not f.get("placements"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.placements", "Choose at least one placement."))
        for ai, ad in enumerate(g["ads"]):
            cr = ad["creative"]
            path = f"groups[{gi}].ads[{ai}]"
            if not cr.get("identity_id"):
                out.append(issue("ad", ad["id"], f"{path}.identity_id", "Choose the TikTok identity the ad shows as."))
            if cr.get("format") == "spark_ad":
                if not cr.get("existing_post_id"):
                    out.append(issue("ad", ad["id"], f"{path}.existing_post_id", "A Spark Ad needs the TikTok post ID."))
            else:
                if not cr.get("media"):
                    out.append(issue("ad", ad["id"], f"{path}.media", "Upload a video or image."))
                if not (cr.get("ad_text") or "").strip():
                    out.append(issue("ad", ad["id"], f"{path}.ad_text", "Write the ad text."))
            if objective in ("TRAFFIC", "WEB_CONVERSIONS") and not cr.get("destination_url"):
                out.append(issue("ad", ad["id"], f"{path}.destination_url", "Add the landing page URL."))
            if cr.get("cta") and cr["cta"] not in CTA:
                out.append(issue("ad", ad["id"], f"{path}.cta", "Choose a call to action from the list."))
    return out


# ---------------------------------------------------------------------------
# Lookups and media
# ---------------------------------------------------------------------------
def lookup(conn: dict[str, Any], kind: str, q: str) -> list[dict[str, Any]]:
    adv = _adv(conn)
    ql = q.lower()
    if kind == "locations":
        data = _call(conn, "GET", "tool/region/", params={"advertiser_id": adv, "placements": '["PLACEMENT_TIKTOK"]', "objective_type": "TRAFFIC"})
        rows = [{"id": str(r.get("location_id")), "name": r.get("name"), "type": r.get("region_level")} for r in data.get("region_info") or []]
    elif kind == "languages":
        data = _call(conn, "GET", "tool/language/", params={"advertiser_id": adv})
        rows = [{"id": r.get("code"), "name": r.get("name")} for r in data.get("languages") or []]
    elif kind == "interests":
        data = _call(conn, "GET", "tool/interest_category/", params={"advertiser_id": adv})
        rows = [{"id": str(r.get("id")), "name": r.get("name")} for r in data.get("interest_categories") or []]
    elif kind == "audiences":
        data = _call(conn, "GET", "dmp/custom_audience/list/", params={"advertiser_id": adv, "page_size": 100})
        rows = [{"id": str(r.get("audience_id")), "name": r.get("name")} for r in data.get("list") or []]
    else:
        raise PlatformError(f"TikTok has no {kind} list.", 404)
    return [r for r in rows if r["id"] and r["name"] and ql in str(r["name"]).lower()][:50]


def upload_media(conn: dict[str, Any], filename: str, content: bytes) -> dict[str, Any]:
    video = filename.lower().rsplit(".", 1)[-1] in ("mp4", "mov", "mpeg", "avi", "webm")
    sig = hashlib.md5(content, usedforsecurity=False).hexdigest()
    form = {"advertiser_id": _adv(conn), "upload_type": "UPLOAD_BY_FILE"}
    if video:
        data = _call(conn, "POST", "file/video/ad/upload/", data={**form, "video_signature": sig}, files={"video_file": (filename, content)})
        row = data[0] if isinstance(data, list) else data
        return {"media_id": str(row.get("video_id")), "kind": "video", "name": filename, "thumbnail_url": row.get("video_cover_url")}
    data = _call(conn, "POST", "file/image/ad/upload/", data={**form, "image_signature": sig}, files={"image_file": (filename, content)})
    return {"media_id": str(data.get("image_id")), "kind": "image", "name": filename, "thumbnail_url": data.get("image_url")}


# ---------------------------------------------------------------------------
# Publish: campaign (disabled) -> ad groups -> ads -> enable. All-or-nothing.
# ---------------------------------------------------------------------------
def _group_body(adv: str, campaign_id: str, objective: str, g: dict[str, Any]) -> dict[str, Any]:
    f, t = g["fields"], g["targeting"]
    goal, billing, promotion = OBJECTIVES.get(objective, ("CLICK", "CPC", "WEBSITE"))
    body: dict[str, Any] = {
        "advertiser_id": adv, "campaign_id": campaign_id, "adgroup_name": g["name"][:100],
        "promotion_type": promotion, "operation_status": "ENABLE",
        "placement_type": "PLACEMENT_TYPE_NORMAL" if f.get("placement") == "SELECT" else "PLACEMENT_TYPE_AUTOMATIC",
        "location_ids": ids(t, "locations"), "languages": ids(t, "languages"),
        "interest_category_ids": ids(t, "interests"), "audience_ids": ids(t, "audiences"),
        "age_groups": _ages(t), "gender": _gender(t),
        "optimization_goal": f.get("optimization_goal") or goal, "billing_event": billing,
        "bid_type": "BID_TYPE_CUSTOM" if f.get("bid_strategy") in ("COST_CAP", "BID_CAP") else "BID_TYPE_NO_BID",
        **_budget(g["budget_mode"], g["budget"]),
    }
    if f.get("placement") == "SELECT":
        body["placements"] = [f"PLACEMENT_{p}" for p in f.get("placements") or []]
    if f.get("bid_strategy") == "COST_CAP":
        body["conversion_bid_price"] = f.get("bid_amount")
    elif f.get("bid_strategy") == "BID_CAP":
        body["bid_price"] = f.get("bid_amount")
    if f.get("pixel_id"):
        body["pixel_id"] = f["pixel_id"]
        body["optimization_event"] = f.get("optimization_event")
    if f.get("app_id"):
        body["app_id"] = f["app_id"]
    start, end = _when(g.get("starts_at")), _when(g.get("ends_at"))
    if start and end:
        body.update(schedule_type="SCHEDULE_START_END", schedule_start_time=start, schedule_end_time=end)
    else:
        body.update(schedule_type="SCHEDULE_FROM_NOW", schedule_start_time=start or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    return {k: v for k, v in body.items() if v not in (None, [], "")}


def _creative(ad: dict[str, Any]) -> dict[str, Any]:
    cr = ad["creative"]
    out: dict[str, Any] = {
        "ad_name": ad["name"][:100], "identity_id": cr.get("identity_id"),
        "identity_type": "TT_USER" if cr.get("format") == "spark_ad" else "CUSTOMIZED_USER",
        "ad_text": cr.get("ad_text"), "call_to_action": cr.get("cta") or "LEARN_MORE",
        "landing_page_url": cr.get("destination_url"), "display_name": cr.get("display_name"),
    }
    media = cr.get("media") or []
    if cr.get("format") == "spark_ad":
        out.update(ad_format="SINGLE_VIDEO", tiktok_item_id=cr.get("existing_post_id"))
    elif cr.get("format") == "single_image":
        out.update(ad_format="SINGLE_IMAGE", image_ids=[m["media_id"] for m in media if m.get("kind") == "image"])
    else:
        video = next((m["media_id"] for m in media if m.get("kind") == "video"), None)
        cover = next((m["media_id"] for m in media if m.get("kind") == "image"), None)
        out.update(ad_format="SINGLE_VIDEO", video_id=video, image_ids=[cover] if cover else None)
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def _set(conn: dict[str, Any], level: str, object_ids: list[str], status: str) -> None:
    key = {"campaign": "campaign_ids", "group": "adgroup_ids", "ad": "ad_ids"}[level]
    path = {"campaign": "campaign", "group": "adgroup", "ad": "ad"}[level]
    _call(conn, "POST", f"{path}/status/update/", json={"advertiser_id": _adv(conn), key: object_ids, "operation_status": status})


def publish(conn: dict[str, Any], tree: dict[str, Any], mode: str) -> dict[str, Any]:
    adv = _adv(conn)
    c = tree["campaign"]
    undo = Rollback("tiktok")
    path = "campaign"
    try:
        data = _call(conn, "POST", "campaign/create/", json={
            "advertiser_id": adv, "campaign_name": c["name"][:100], "objective_type": c["objective"],
            "operation_status": "DISABLE", "budget_optimize_on": bool(c["fields"].get("budget_optimization")),
            **_budget(c["budget_mode"], c["budget"]),
        })
        campaign_id = str(data["campaign_id"])
        # Deleting the campaign deletes its ad groups and ads on TikTok.
        undo.add(f"campaign {campaign_id}", lambda: _set(conn, "campaign", [campaign_id], "DELETE"))
        groups: dict[str, str] = {}
        ads: dict[str, str] = {}
        for gi, g in enumerate(tree["groups"]):
            path = f"groups[{gi}]"
            gdata = _call(conn, "POST", "adgroup/create/", json=_group_body(adv, campaign_id, c["objective"], g))
            groups[g["id"]] = str(gdata["adgroup_id"])
            for ai, ad in enumerate(g["ads"]):
                path = f"groups[{gi}].ads[{ai}]"
                adata = _call(conn, "POST", "ad/create/", json={"advertiser_id": adv, "adgroup_id": groups[g["id"]], "creatives": [_creative(ad)]})
                ad_ids = adata.get("ad_ids") or []
                if not ad_ids:
                    raise PlatformError("TikTok didn't return the new ad's ID.", 502)
                ads[ad["id"]] = str(ad_ids[0])
        if mode == "active":
            path = "campaign"
            _set(conn, "campaign", [campaign_id], "ENABLE")
    except PlatformError as exc:
        undo.run()
        raise PlatformError(exc.message, exc.status_code, path=path, auth=exc.auth) from None
    return {"campaign": campaign_id, "groups": groups, "ads": ads,
            "url": f"https://ads.tiktok.com/i18n/perf/campaign?aadvid={adv}&keyword={campaign_id}"}


def set_status(conn: dict[str, Any], level: str, external_id: str, active: bool) -> None:
    _set(conn, level, [external_id], "ENABLE" if active else "DISABLE")


# ---------------------------------------------------------------------------
# Results: daily campaign-level BASIC report.
# ---------------------------------------------------------------------------
def import_results(conn: dict[str, Any], campaign_ids: list[str], since: str, until: str) -> list[dict[str, Any]]:
    """-> [{campaign_id, date, spend, impressions, clicks, conversions}] (spend in
    major units; the caller converts to cents and names the conversion metric)."""
    import json

    data = _call(conn, "GET", "report/integrated/get/", params={
        "advertiser_id": _adv(conn), "report_type": "BASIC", "data_level": "AUCTION_CAMPAIGN",
        "dimensions": json.dumps(["campaign_id", "stat_time_day"]),
        "metrics": json.dumps(["spend", "impressions", "clicks", "conversion"]),
        "start_date": since, "end_date": until, "page_size": 1000,
        "filtering": json.dumps([{"field_name": "campaign_ids", "filter_type": "IN", "filter_value": json.dumps(campaign_ids)}]),
    })
    out = []
    for row in data.get("list") or []:
        d, m = row.get("dimensions") or {}, row.get("metrics") or {}
        out.append({"campaign_id": str(d.get("campaign_id")), "date": str(d.get("stat_time_day", ""))[:10],
                    "spend": m.get("spend"), "impressions": m.get("impressions"), "clicks": m.get("clicks"), "conversions": m.get("conversion")})
    return out
