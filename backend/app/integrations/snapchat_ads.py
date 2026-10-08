"""Snapchat Ads adapter (SPEC-BE-067): Snap Marketing API v1.

OAuth2: access tokens last ~30 minutes, so one is refreshed from the stored
refresh token on demand and cached in memory. Money is in micros. Objects are
sent wrapped in lists ({"campaigns": [...]}), and each answer carries a
per-item sub_request_status. Updates are full-object PUTs (Snap has no
partial update), so pause/resume reads the object first. Media over 32 MB
needs Snap's chunked upload, which isn't built: such files are refused with a
clear message.
"""
import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.base_adapter import PlatformError, Rollback, http, ids, issue, micros, short, unresolved

BASE = "https://adsapi.snapchat.com/v1"
TOKEN_URL = "https://accounts.snapchat.com/login/oauth2/access_token"
SIMPLE_UPLOAD_MAX = 32 * 1024 * 1024
MIN_SQUAD_DAILY_USD = 5
_tokens: dict[str, tuple[str, float]] = {}

GOALS = {"AWARENESS_AND_ENGAGEMENT": "IMPRESSIONS", "TRAFFIC": "SWIPES", "LEADS": "LEADS", "APP_PROMOTION": "APP_INSTALLS", "SALES": "PIXEL_PURCHASE"}


def _token(f: dict[str, Any]) -> str:
    key = f"{f.get('client_id')}:{str(f.get('refresh_token', ''))[-12:]}"
    cached = _tokens.get(key)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    resp = http("POST", TOKEN_URL, data={"grant_type": "refresh_token", "client_id": f.get("client_id"),
                                         "client_secret": f.get("client_secret"), "refresh_token": f.get("refresh_token")})
    body = resp.json() if resp.content else {}
    if resp.status_code >= 400 or "access_token" not in body:
        raise PlatformError(f"Snapchat sign-in failed: {short(body.get('error_description') or body.get('error') or resp.status_code)}", 409, auth=True)
    _tokens[key] = (body["access_token"], time.time() + int(body.get("expires_in", 1800)))
    return str(body["access_token"])


def _call(conn: dict[str, Any], method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    resp = http(method, f"{BASE}/{path}", headers={"Authorization": f"Bearer {_token(conn['fields'])}"}, **kwargs)
    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        raise PlatformError(f"Snapchat answered HTTP {resp.status_code}.", 502) from None
    if resp.status_code >= 400 or body.get("request_status") == "ERROR":
        message = body.get("debug_message") or body.get("display_message") or body
        for key in ("campaigns", "adsquads", "ads", "creatives", "media"):
            for item in body.get(key) or []:
                if item.get("sub_request_status") == "ERROR":
                    message = item.get("sub_request_error_reason") or message
        auth = resp.status_code == 401
        raise PlatformError(f"Snapchat: {short(message)}", 409 if auth else 502, auth=auth)
    return body


def _first(body: dict[str, Any], key: str, kind: str) -> dict[str, Any]:
    items = body.get(key) or []
    if not items or not (items[0].get(kind) or {}).get("id"):
        raise PlatformError(f"Snapchat didn't return the new {kind.replace('adsquad', 'ad squad')}.", 502)
    return dict(items[0][kind])


def _acct(conn: dict[str, Any]) -> str:
    return str(conn["fields"].get("ad_account_id", ""))


def verify_account(fields: dict[str, str]) -> dict[str, Any]:
    acct = _first(_call({"fields": fields}, "GET", f"adaccounts/{fields['ad_account_id']}"), "adaccounts", "adaccount")
    return {"name": acct.get("name"), "currency": acct.get("currency"), "timezone": acct.get("timezone")}


def _iso(value: str | None) -> str | None:
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") if value else None


def _targeting(t: dict[str, Any]) -> dict[str, Any]:
    demo: dict[str, Any] = {}
    if t.get("age_min"):
        demo["min_age"] = str(t["age_min"])
    if t.get("age_max") and int(t["age_max"]) < 65:
        demo["max_age"] = str(t["age_max"])
    genders = set(t.get("genders") or [])
    if len(genders) == 1:
        demo["gender"] = "FEMALE" if "female" in genders else "MALE"
    if ids(t, "languages"):
        demo["languages"] = ids(t, "languages")
    out: dict[str, Any] = {"geos": [{"country_code": c.lower()} for c in ids(t, "locations")]}
    if demo:
        out["demographics"] = [demo]
    if ids(t, "interests"):
        out["interests"] = [{"category_id": ids(t, "interests")}]
    if ids(t, "audiences"):
        out["segments"] = [{"segment_id": ids(t, "audiences")}]
    return out


# ---------------------------------------------------------------------------
def validate(conn: dict[str, Any], tree: dict[str, Any]) -> list[dict[str, Any]]:
    out = unresolved(tree, ("locations", "languages", "interests", "audiences"), "Snapchat")
    c = tree["campaign"]
    if not conn["fields"].get("public_profile_id"):
        out.append(issue("campaign", c["id"], "connection.public_profile_id", "Add your Snapchat public profile ID in Integrations; ads run from it."))
    try:
        account = verify_account(conn["fields"])
        if account.get("currency") and account["currency"] != c["currency"]:
            out.append(issue("campaign", c["id"], "campaign.currency", f"Your Snapchat ad account bills in {account['currency']}, but this campaign is in {c['currency']}."))
    except PlatformError as exc:
        out.append(issue("campaign", c["id"], "connection", exc.message))
    for gi, g in enumerate(tree["groups"]):
        f = g["fields"]
        if c["currency"] == "USD" and g["budget_mode"] == "daily" and (g["budget"] or 0) < MIN_SQUAD_DAILY_USD:
            out.append(issue("group", g["id"], f"groups[{gi}].budget", f"Snapchat's minimum ad squad daily budget is {MIN_SQUAD_DAILY_USD} USD."))
        if g["budget_mode"] == "none" and c["budget_mode"] != "none":
            out.append(issue("group", g["id"], f"groups[{gi}].budget", "Snapchat budgets are set per ad squad; set one here (the campaign budget becomes a spend cap)."))
        if (f.get("optimization_goal") or GOALS.get(c["objective"])) == "PIXEL_PURCHASE" and not f.get("pixel_id"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.pixel_id", "Purchases need your Snap Pixel ID."))
        if f.get("bid_strategy") in ("LOWEST_COST_WITH_MAX_BID", "TARGET_COST") and not f.get("bid_amount"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.bid_amount", "Set a bid amount."))
        for ai, ad in enumerate(g["ads"]):
            cr = ad["creative"]
            path = f"groups[{gi}].ads[{ai}]"
            if not cr.get("media"):
                out.append(issue("ad", ad["id"], f"{path}.media", "Upload a vertical (9:16) image or video."))
            for key in ("brand_name", "headline"):
                if not str(cr.get(key) or "").strip():
                    out.append(issue("ad", ad["id"], f"{path}.{key}", f"Add the {key.replace('_', ' ')}."))
            if c["objective"] in ("TRAFFIC", "SALES", "LEADS") and not cr.get("destination_url"):
                out.append(issue("ad", ad["id"], f"{path}.destination_url", "Add the website URL."))
    return out


def lookup(conn: dict[str, Any], kind: str, q: str) -> list[dict[str, Any]]:
    ql = q.lower()
    if kind == "locations":
        body = _call(conn, "GET", "targeting/geo/country")
        rows = [((d.get("country") or {}).get("country_code") or "", (d.get("country") or {}).get("name") or "") for d in body.get("targeting_dimensions") or []]
    elif kind == "interests":
        body = _call(conn, "GET", "targeting/interests/scls")
        rows = [(str((d.get("scls") or {}).get("id") or ""), (d.get("scls") or {}).get("name") or "") for d in body.get("targeting_dimensions") or []]
    elif kind == "languages":
        body = _call(conn, "GET", "targeting/demographics/languages")
        rows = [(str((d.get("languages") or {}).get("id") or ""), (d.get("languages") or {}).get("name") or "") for d in body.get("targeting_dimensions") or []]
    elif kind == "audiences":
        body = _call(conn, "GET", f"adaccounts/{_acct(conn)}/segments")
        rows = [(str((s.get("segment") or {}).get("id") or ""), (s.get("segment") or {}).get("name") or "") for s in body.get("segments") or []]
    else:
        raise PlatformError(f"Snapchat has no {kind} list.", 404)
    return [{"id": i, "name": n} for i, n in rows if i and ql in n.lower()][:50]


def upload_media(conn: dict[str, Any], filename: str, content: bytes) -> dict[str, Any]:
    if len(content) > SIMPLE_UPLOAD_MAX:
        raise PlatformError("Snapchat files over 32 MB need a chunked upload, which isn't supported yet; compress the video below 32 MB.", 413)
    video = filename.lower().rsplit(".", 1)[-1] in ("mp4", "mov")
    media = _first(_call(conn, "POST", f"adaccounts/{_acct(conn)}/media",
                         json={"media": [{"name": filename[:100], "type": "VIDEO" if video else "IMAGE", "ad_account_id": _acct(conn)}]}), "media", "media")
    _call(conn, "POST", f"media/{media['id']}/upload", files={"file": (filename, content)})
    return {"media_id": media["id"], "kind": "video" if video else "image", "name": filename, "thumbnail_url": None}


# ---------------------------------------------------------------------------
def publish(conn: dict[str, Any], tree: dict[str, Any], mode: str) -> dict[str, Any]:
    acct = _acct(conn)
    c = tree["campaign"]
    undo = Rollback("snapchat")
    path = "campaign"
    try:
        cbody: dict[str, Any] = {"name": c["name"][:375], "ad_account_id": acct, "status": "PAUSED",
                                 "start_time": _iso(c.get("starts_at")) or _iso(datetime.now(timezone.utc).isoformat()),
                                 "objective_v2_properties": {"objective_v2_type": c["objective"]}}
        if c.get("ends_at"):
            cbody["end_time"] = _iso(c["ends_at"])
        if c["budget_mode"] != "none" and c["budget"]:
            cbody["lifetime_spend_cap_micro" if c["budget_mode"] == "total" else "daily_budget_micro"] = micros(c["budget"])
        campaign = _first(_call(conn, "POST", f"adaccounts/{acct}/campaigns", json={"campaigns": [cbody]}), "campaigns", "campaign")["id"]
        undo.add(f"campaign {campaign}", lambda: _call(conn, "DELETE", f"campaigns/{campaign}"))
        groups: dict[str, str] = {}
        ads: dict[str, str] = {}
        for gi, g in enumerate(tree["groups"]):
            path = f"groups[{gi}]"
            f = g["fields"]
            sbody: dict[str, Any] = {
                "campaign_id": campaign, "name": g["name"][:375], "type": "SNAP_ADS", "status": "ACTIVE", "billing_event": "IMPRESSION",
                "optimization_goal": f.get("optimization_goal") or GOALS.get(c["objective"], "IMPRESSIONS"),
                "bid_strategy": f.get("bid_strategy") or "AUTO_BID", "targeting": _targeting(g["targeting"]),
                "placement_v2": {"config": "AUTOMATIC"} if f.get("placement") != "CONTENT" else {"config": "CUSTOM", "platforms": ["SNAPCHAT"], "snapchat_positions": ["INTERSTITIAL_CONTENT"]},
                "start_time": _iso(g.get("starts_at") or c.get("starts_at")) or _iso(datetime.now(timezone.utc).isoformat()),
            }
            if g.get("ends_at") or c.get("ends_at"):
                sbody["end_time"] = _iso(g.get("ends_at") or c.get("ends_at"))
            if g["budget"]:
                sbody["lifetime_budget_micro" if g["budget_mode"] == "total" else "daily_budget_micro"] = micros(g["budget"])
            if f.get("bid_amount"):
                sbody["bid_micro"] = micros(f["bid_amount"])
            if f.get("pixel_id"):
                sbody["pixel_id"] = f["pixel_id"]
            squad = _first(_call(conn, "POST", f"campaigns/{campaign}/adsquads", json={"adsquads": [sbody]}), "adsquads", "adsquad")["id"]
            groups[g["id"]] = squad
            undo.add(f"squad {squad}", lambda s=squad: _call(conn, "DELETE", f"adsquads/{s}"))
            for ai, ad in enumerate(g["ads"]):
                path = f"groups[{gi}].ads[{ai}]"
                cr = ad["creative"]
                web = bool(cr.get("destination_url"))
                creative = _first(_call(conn, "POST", f"adaccounts/{acct}/creatives", json={"creatives": [{
                    "ad_account_id": acct, "name": ad["name"][:375], "type": "WEB_VIEW" if web else "SNAP_AD", "shareable": True,
                    "brand_name": cr.get("brand_name"), "headline": cr.get("headline"), "top_snap_media_id": (cr.get("media") or [{}])[0].get("media_id"),
                    "profile_properties": {"profile_id": conn["fields"].get("public_profile_id")},
                    **({"call_to_action": cr.get("cta") or "MORE", "web_view_properties": {"url": cr["destination_url"]}} if web else {}),
                }]}), "creatives", "creative")["id"]
                undo.add(f"creative {creative}", lambda cid=creative: _call(conn, "DELETE", f"creatives/{cid}"))
                ad_id = _first(_call(conn, "POST", f"adsquads/{squad}/ads", json={"ads": [{
                    "ad_squad_id": squad, "creative_id": creative, "name": ad["name"][:375], "type": "REMOTE_WEBPAGE" if web else "SNAP_AD", "status": "ACTIVE",
                }]}), "ads", "ad")["id"]
                ads[ad["id"]] = ad_id
                undo.add(f"ad {ad_id}", lambda a=ad_id: _call(conn, "DELETE", f"ads/{a}"))
        if mode == "active":
            path = "campaign"
            set_status(conn, "campaign", campaign, True)
    except PlatformError as exc:
        undo.run()
        raise PlatformError(exc.message, exc.status_code, path=path, auth=exc.auth) from None
    return {"campaign": campaign, "groups": groups, "ads": ads, "url": f"https://ads.snapchat.com/{acct}/campaigns/{campaign}"}


def set_status(conn: dict[str, Any], level: str, external_id: str, active: bool) -> None:
    key, kind = {"campaign": ("campaigns", "campaign"), "group": ("adsquads", "adsquad"), "ad": ("ads", "ad")}[level]
    obj = _first(_call(conn, "GET", f"{key}/{external_id}"), key, kind)
    obj["status"] = "ACTIVE" if active else "PAUSED"
    parent = {"campaign": f"adaccounts/{obj.get('ad_account_id') or _acct(conn)}/campaigns",
              "group": f"campaigns/{obj.get('campaign_id')}/adsquads", "ad": f"adsquads/{obj.get('ad_squad_id')}/ads"}[level]
    _call(conn, "PUT", parent, json={key: [obj]})


def import_results(conn: dict[str, Any], campaign_ids: list[str], since: str, until: str) -> list[dict[str, Any]]:
    out = []
    for cid in campaign_ids:
        body = _call(conn, "GET", f"campaigns/{cid}/stats", params={
            "granularity": "DAY", "fields": "impressions,swipes,spend,conversion_purchases,conversion_purchases_value",
            "start_time": f"{since}T00:00:00.000Z", "end_time": f"{until}T23:59:59.000Z"})
        for stat in body.get("timeseries_stats") or []:
            for point in (stat.get("timeseries_stat") or {}).get("timeseries") or []:
                s = point.get("stats") or {}
                out.append({"campaign_id": cid, "date": str(point.get("start_time", ""))[:10], "spend": (s.get("spend") or 0) / 1_000_000,
                            "impressions": s.get("impressions"), "clicks": s.get("swipes"), "conversions": s.get("conversion_purchases"),
                            "conversion_value": (s["conversion_purchases_value"] / 1_000_000) if s.get("conversion_purchases_value") is not None else None})
    return out
