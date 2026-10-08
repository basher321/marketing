"""Pinterest Ads adapter (SPEC-BE-068): Pinterest API v5.

OAuth2 bearer token; on a 401 it is refreshed once from the stored refresh
token (kept in memory). Money is in micro-currency. Bulk endpoints take and
return lists ({"items": [{"data": ..., "exceptions": ...}]}). Pinterest
archives campaigns / ad groups / ads instead of deleting them, so a failed
publish archives what it created and deletes the new Pins.

Images: Pinterest has no standalone image upload, so an image Pin takes a
public https image URL (creative.image_url); videos go through the media API.
Age targeting still uses AGE_BUCKET; switch to min/max age when Pinterest
retires buckets (announced for 2026).
"""
import base64
from datetime import datetime
from typing import Any

from app.integrations.base_adapter import PlatformError, Rollback, http, ids, issue, micros, short, unresolved

BASE = "https://api.pinterest.com/v5"
_tokens: dict[str, str] = {}
AGE_BUCKETS = ((18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 49, "45-49"), (50, 54, "50-54"), (55, 64, "55-64"), (65, 200, "65+"))
LOOKUP = {"locations": "GEO", "languages": "LOCALE", "interests": "INTEREST"}


def _key(f: dict[str, Any]) -> str:
    return f"{f.get('client_id')}:{str(f.get('refresh_token', ''))[-12:]}"


def _refresh(f: dict[str, Any]) -> None:
    basic = base64.b64encode(f"{f.get('client_id')}:{f.get('client_secret')}".encode()).decode()
    resp = http("POST", f"{BASE}/oauth/token", headers={"Authorization": f"Basic {basic}"},
                data={"grant_type": "refresh_token", "refresh_token": f.get("refresh_token")})
    body = resp.json() if resp.content else {}
    if resp.status_code >= 400 or "access_token" not in body:
        raise PlatformError(f"Pinterest sign-in failed: {short(body.get('message') or resp.status_code)}", 409, auth=True)
    _tokens[_key(f)] = body["access_token"]


def _call(conn: dict[str, Any], method: str, path: str, **kwargs: Any) -> Any:
    f = conn["fields"]
    for attempt in (0, 1):
        token = _tokens.get(_key(f)) or f.get("access_token", "")
        resp = http(method, f"{BASE}/{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs)
        if resp.status_code == 401 and attempt == 0 and f.get("refresh_token"):
            _refresh(f)
            continue
        break
    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        raise PlatformError(f"Pinterest answered HTTP {resp.status_code}.", 502) from None
    if resp.status_code >= 400:
        auth = resp.status_code == 401
        raise PlatformError(f"Pinterest: {short(body.get('message') or body)}", 409 if auth else 502, auth=auth)
    return body


def _bulk_id(body: Any, what: str) -> str:
    items = (body or {}).get("items") or []
    item = items[0] if items else {}
    if item.get("exceptions"):
        raise PlatformError(f"Pinterest: {short(item['exceptions'][0].get('message') or item['exceptions'])}", 502)
    found = (item.get("data") or {}).get("id")
    if not found:
        raise PlatformError(f"Pinterest didn't return the new {what}.", 502)
    return str(found)


def _acct(conn: dict[str, Any]) -> str:
    return str(conn["fields"].get("ad_account_id", ""))


def verify_account(fields: dict[str, str]) -> dict[str, Any]:
    data = _call({"fields": fields}, "GET", f"ad_accounts/{fields['ad_account_id']}")
    return {"name": data.get("name"), "currency": data.get("currency")}


def _unix(iso: str | None) -> int | None:
    return int(datetime.fromisoformat(iso).timestamp()) if iso else None


def _targeting(t: dict[str, Any]) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    for key, name in (("locations", "GEO"), ("languages", "LOCALE"), ("interests", "INTEREST"), ("audiences", "AUDIENCE_INCLUDE")):
        if ids(t, key):
            spec[name] = ids(t, key)
    genders = set(t.get("genders") or [])
    if len(genders) == 1:
        spec["GENDER"] = ["female" if "female" in genders else "male"]
    if t.get("age_min") or t.get("age_max"):
        lo, hi = int(t.get("age_min") or 18), int(t.get("age_max") or 200)
        spec["AGE_BUCKET"] = [n for a, b, n in AGE_BUCKETS if b >= lo and a <= (200 if hi >= 65 else hi)]
    return spec


# ---------------------------------------------------------------------------
def validate(conn: dict[str, Any], tree: dict[str, Any]) -> list[dict[str, Any]]:
    out = unresolved(tree, ("locations", "languages", "interests", "audiences"), "Pinterest")
    c = tree["campaign"]
    try:
        account = verify_account(conn["fields"])
        if account.get("currency") and account["currency"] != c["currency"]:
            out.append(issue("campaign", c["id"], "campaign.currency", f"Your Pinterest ad account bills in {account['currency']}, but this campaign is in {c['currency']}."))
    except PlatformError as exc:
        out.append(issue("campaign", c["id"], "connection", exc.message))
    for gi, g in enumerate(tree["groups"]):
        f = g["fields"]
        if f.get("bid_strategy") in ("MAX_BID", "TARGET_AVG") and not f.get("bid_amount"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.bid_amount", "Set a bid amount."))
        if c["objective"] == "WEB_CONVERSION" and not f.get("conversion_tag_id"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.conversion_tag_id", "Conversions need your Pinterest tag ID."))
        for ai, ad in enumerate(g["ads"]):
            cr = ad["creative"]
            path = f"groups[{gi}].ads[{ai}]"
            fmt = cr.get("format")
            if fmt == "existing_pin":
                if not cr.get("existing_pin_id"):
                    out.append(issue("ad", ad["id"], f"{path}.existing_pin_id", "Add the Pin ID to promote."))
                continue
            if not cr.get("board_id"):
                out.append(issue("ad", ad["id"], f"{path}.board_id", "Choose the board for the new Pin."))
            if fmt == "image_pin" and not str(cr.get("image_url") or "").startswith("https://"):
                out.append(issue("ad", ad["id"], f"{path}.image_url", "Add a public https image URL (2:3 recommended)."))
            if fmt == "video_pin" and not any(m.get("kind") == "video" for m in cr.get("media") or []):
                out.append(issue("ad", ad["id"], f"{path}.media", "Upload the video (4 s to 15 min)."))
            if not cr.get("destination_url"):
                out.append(issue("ad", ad["id"], f"{path}.destination_url", "Add the destination URL."))
    return out


def lookup(conn: dict[str, Any], kind: str, q: str) -> list[dict[str, Any]]:
    ql = q.lower()
    if kind == "audiences":
        body = _call(conn, "GET", f"ad_accounts/{_acct(conn)}/audiences", params={"page_size": 100})
        rows = [(str(a.get("id")), a.get("name") or "") for a in body.get("items") or []]
    elif kind in LOOKUP:
        body = _call(conn, "GET", f"resources/targeting/{LOOKUP[kind]}")
        items = body if isinstance(body, list) else (body.get("items") or body.get("data") or [])
        rows = [(str(i.get("id") or i.get("key") or ""), str(i.get("name") or i.get("label") or "")) if isinstance(i, dict) else (str(i), str(i)) for i in items]
    else:
        raise PlatformError(f"Pinterest has no {kind} list.", 404)
    return [{"id": i, "name": n} for i, n in rows if i and ql in n.lower()][:50]


def upload_media(conn: dict[str, Any], filename: str, content: bytes) -> dict[str, Any]:
    if filename.lower().rsplit(".", 1)[-1] not in ("mp4", "mov", "m4v"):
        raise PlatformError("Pinterest takes images as a public image URL: paste it in the Image URL field.", 422)
    reg = _call(conn, "POST", "media", json={"media_type": "video"})
    params = reg.get("upload_parameters") or {}
    resp = http("POST", reg.get("upload_url", ""), data=params, files={"file": (filename, content)})
    if resp.status_code >= 400:
        raise PlatformError("Pinterest rejected the video upload.", 502)
    return {"media_id": str(reg.get("media_id")), "kind": "video", "name": filename, "thumbnail_url": None}


# ---------------------------------------------------------------------------
def _archive(conn: dict[str, Any], kind: str, object_id: str) -> None:
    _call(conn, "PATCH", f"ad_accounts/{_acct(conn)}/{kind}", json=[{"id": object_id, "status": "ARCHIVED"}])


def publish(conn: dict[str, Any], tree: dict[str, Any], mode: str) -> dict[str, Any]:
    acct = _acct(conn)
    c = tree["campaign"]
    undo = Rollback("pinterest")
    path = "campaign"
    try:
        cbody: dict[str, Any] = {"ad_account_id": acct, "name": c["name"][:255], "status": "PAUSED", "objective_type": c["objective"],
                                 "is_campaign_budget_optimization": bool(c["fields"].get("budget_optimization")) and c["budget_mode"] != "none"}
        if c["budget_mode"] != "none" and c["budget"]:
            cbody["lifetime_spend_cap" if c["budget_mode"] == "total" else "daily_spend_cap"] = micros(c["budget"])
        if c.get("starts_at"):
            cbody["start_time"] = _unix(c["starts_at"])
        if c.get("ends_at"):
            cbody["end_time"] = _unix(c["ends_at"])
        campaign = _bulk_id(_call(conn, "POST", f"ad_accounts/{acct}/campaigns", json=[cbody]), "campaign")
        undo.add(f"campaign {campaign}", lambda: _archive(conn, "campaigns", campaign))
        groups: dict[str, str] = {}
        ads: dict[str, str] = {}
        for gi, g in enumerate(tree["groups"]):
            path = f"groups[{gi}]"
            f = g["fields"]
            gbody: dict[str, Any] = {"ad_account_id": acct, "campaign_id": campaign, "name": g["name"][:255], "status": "ACTIVE",
                                     "billable_event": "CLICKTHROUGH" if c["objective"] == "CONSIDERATION" else "IMPRESSION",
                                     "bid_strategy_type": f.get("bid_strategy") or "AUTOMATIC_BID", "placement_group": f.get("placement") or "ALL",
                                     "targeting_spec": _targeting(g["targeting"])}
            if g["budget"] and g["budget_mode"] != "none":
                gbody.update(budget_in_micro_currency=micros(g["budget"]), budget_type="LIFETIME" if g["budget_mode"] == "total" else "DAILY")
            if f.get("bid_amount"):
                gbody["bid_in_micro_currency"] = micros(f["bid_amount"])
            if f.get("conversion_tag_id"):
                gbody["optimization_goal_metadata"] = {"conversion_tag_v3_goal_metadata": {"conversion_tag_id": f["conversion_tag_id"], "conversion_event": "CHECKOUT"}}
            if g.get("starts_at"):
                gbody["start_time"] = _unix(g["starts_at"])
            if g.get("ends_at"):
                gbody["end_time"] = _unix(g["ends_at"])
            group = _bulk_id(_call(conn, "POST", f"ad_accounts/{acct}/ad_groups", json=[gbody]), "ad group")
            groups[g["id"]] = group
            undo.add(f"ad group {group}", lambda gid=group: _archive(conn, "ad_groups", gid))
            for ai, ad in enumerate(g["ads"]):
                path = f"groups[{gi}].ads[{ai}]"
                cr = ad["creative"]
                pin_id = cr.get("existing_pin_id")
                creative_type = "REGULAR"
                if cr.get("format") != "existing_pin":
                    if cr.get("format") == "video_pin":
                        video = next(m["media_id"] for m in cr.get("media") or [] if m.get("kind") == "video")
                        source: dict[str, Any] = {"source_type": "video_id", "media_id": video}
                        creative_type = "VIDEO"
                    else:
                        source = {"source_type": "image_url", "url": cr.get("image_url")}
                    pin = _call(conn, "POST", "pins", json={"board_id": cr.get("board_id"), "title": cr.get("title"), "description": cr.get("description"),
                                                            "link": cr.get("destination_url"), "alt_text": cr.get("alt_text"), "media_source": source})
                    pin_id = str(pin.get("id"))
                    undo.add(f"pin {pin_id}", lambda p=pin_id: _call(conn, "DELETE", f"pins/{p}"))
                ad_id = _bulk_id(_call(conn, "POST", f"ad_accounts/{acct}/ads", json=[{
                    "ad_group_id": group, "creative_type": creative_type, "pin_id": pin_id, "status": "ACTIVE", "name": ad["name"][:255],
                    **({"destination_url": cr["destination_url"]} if cr.get("destination_url") else {}),
                }]), "ad")
                ads[ad["id"]] = ad_id
                undo.add(f"ad {ad_id}", lambda a=ad_id: _archive(conn, "ads", a))
        if mode == "active":
            path = "campaign"
            set_status(conn, "campaign", campaign, True)
    except PlatformError as exc:
        undo.run()
        raise PlatformError(exc.message, exc.status_code, path=path, auth=exc.auth) from None
    except StopIteration:
        undo.run()
        raise PlatformError("Upload the video first.", 422, path=path) from None
    return {"campaign": campaign, "groups": groups, "ads": ads, "url": f"https://ads.pinterest.com/advertiser/{acct}/reporting/campaigns/?campaignIds={campaign}"}


def set_status(conn: dict[str, Any], level: str, external_id: str, active: bool) -> None:
    kind = {"campaign": "campaigns", "group": "ad_groups", "ad": "ads"}[level]
    _call(conn, "PATCH", f"ad_accounts/{_acct(conn)}/{kind}", json=[{"id": external_id, "status": "ACTIVE" if active else "PAUSED"}])


def import_results(conn: dict[str, Any], campaign_ids: list[str], since: str, until: str) -> list[dict[str, Any]]:
    if not campaign_ids:
        return []
    body = _call(conn, "GET", f"ad_accounts/{_acct(conn)}/campaigns/analytics", params={
        "start_date": since, "end_date": until, "campaign_ids": ",".join(campaign_ids), "granularity": "DAY",
        "columns": "SPEND_IN_MICRO_DOLLAR,IMPRESSION_1,CLICKTHROUGH_1,TOTAL_CONVERSIONS,TOTAL_CONVERSIONS_VALUE_IN_MICRO_DOLLAR"})
    out = []
    for r in body if isinstance(body, list) else []:
        out.append({"campaign_id": str(r.get("CAMPAIGN_ID")), "date": str(r.get("DATE", ""))[:10],
                    "spend": (r.get("SPEND_IN_MICRO_DOLLAR") or 0) / 1_000_000, "impressions": r.get("IMPRESSION_1"), "clicks": r.get("CLICKTHROUGH_1"),
                    "conversions": r.get("TOTAL_CONVERSIONS"),
                    "conversion_value": (r["TOTAL_CONVERSIONS_VALUE_IN_MICRO_DOLLAR"] / 1_000_000) if r.get("TOTAL_CONVERSIONS_VALUE_IN_MICRO_DOLLAR") is not None else None})
    return out
