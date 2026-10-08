"""X (Twitter) Ads adapter (SPEC-BE-066): X Ads API v12.

Ad writes need OAuth 1.0a user context, signed here with HMAC-SHA1 (no new
dependency; `sign()` reproduces X's documented example signature). Request
parameters go in the query string, so they're part of the signature. Money
is in local micros. Hierarchy: campaign -> line item -> promoted post; a new
post is created "nullcast" (promoted-only, never on the profile timeline).
Campaigns and line items are created PAUSED; on failure they and the new
posts are deleted in reverse order.
"""
import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlsplit, parse_qsl

from app.integrations.base_adapter import PlatformError, Rollback, entries, http, ids, issue, micros, short, unresolved

BASE = "https://ads-api.x.com/12"
UPLOAD = "https://upload.x.com/1.1/media/upload.json"
POSTS = "https://api.x.com/2/tweets"
CHUNK = 4 * 1024 * 1024


def _enc(value: str) -> str:
    return quote(str(value), safe="~-._")


def sign(method: str, url: str, params: dict[str, str], consumer_secret: str, token_secret: str) -> str:
    """OAuth 1.0a HMAC-SHA1 signature over method, base URL and every
    parameter (query + oauth_* + form body)."""
    pairs = sorted((_enc(k), _enc(v)) for k, v in params.items())
    param_str = "&".join(f"{k}={v}" for k, v in pairs)
    base = "&".join((method.upper(), _enc(url), _enc(param_str)))
    key = f"{_enc(consumer_secret)}&{_enc(token_secret)}"
    return base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()


def _auth_header(f: dict[str, Any], method: str, url: str, params: dict[str, str]) -> str:
    oauth = {"oauth_consumer_key": f.get("consumer_key", ""), "oauth_nonce": secrets.token_hex(16), "oauth_signature_method": "HMAC-SHA1",
             "oauth_timestamp": str(int(time.time())), "oauth_token": f.get("access_token", ""), "oauth_version": "1.0"}
    oauth["oauth_signature"] = sign(method, url, {**params, **oauth}, f.get("consumer_secret", ""), f.get("access_token_secret", ""))
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))


def _call(conn: dict[str, Any], method: str, url: str, params: dict[str, Any] | None = None, *, json_body: Any = None, form: dict[str, Any] | None = None, files: Any = None) -> Any:
    clean = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in (params or {}).items() if v not in (None, "")}
    parts = urlsplit(url)
    base_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
    signed = {**clean, **dict(parse_qsl(parts.query))}
    if form and not files:
        signed.update({k: str(v) for k, v in form.items()})
    headers = {"Authorization": _auth_header(conn["fields"], method, base_url, signed)}
    kwargs: dict[str, Any] = {"params": clean, "headers": headers}
    if json_body is not None:
        kwargs["json"] = json_body
    if form is not None:
        kwargs["data"] = form
    if files is not None:
        kwargs["files"] = files
    resp = http(method, url, **kwargs)
    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        raise PlatformError(f"X answered HTTP {resp.status_code}.", 502) from None
    if resp.status_code >= 400:
        errs = body.get("errors") or [body]
        message = "; ".join(short(e.get("message") or e.get("detail") or e) for e in errs[:3])
        auth = resp.status_code == 401
        raise PlatformError(f"X: {message}", 409 if auth else 502, auth=auth)
    return body


def _acct(conn: dict[str, Any]) -> str:
    return str(conn["fields"].get("account_id", ""))


def _funding(conn: dict[str, Any]) -> dict[str, Any]:
    wanted = conn["fields"].get("funding_instrument_id")
    items = _call(conn, "GET", f"{BASE}/accounts/{_acct(conn)}/funding_instruments").get("data") or []
    usable = [i for i in items if i.get("entity_status") == "ACTIVE" and (not wanted or i.get("id") == wanted)]
    if not usable:
        raise PlatformError("No active X funding source found for this ad account.", 409)
    return dict(usable[0])


def verify_account(fields: dict[str, str]) -> dict[str, Any]:
    conn = {"fields": fields}
    acct = _call(conn, "GET", f"{BASE}/accounts/{fields['account_id']}").get("data") or {}
    try:
        currency = _funding(conn).get("currency")
    except PlatformError:
        currency = None
    return {"name": acct.get("name"), "currency": currency, "timezone": acct.get("timezone")}


def _iso(value: str | None) -> str | None:
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


def _post_length(text: str) -> int:
    # X counts every URL as 23 characters.
    return sum(23 if w.startswith(("http://", "https://")) else len(w) for w in text.split(" ")) + max(0, text.count(" "))


# ---------------------------------------------------------------------------
def validate(conn: dict[str, Any], tree: dict[str, Any]) -> list[dict[str, Any]]:
    out = unresolved(tree, ("locations", "languages", "interests", "audiences"), "X")
    c = tree["campaign"]
    try:
        funding = _funding(conn)
        if funding.get("currency") and funding["currency"] != c["currency"]:
            out.append(issue("campaign", c["id"], "campaign.currency", f"Your X funding source bills in {funding['currency']}, but this campaign is in {c['currency']}."))
    except PlatformError as exc:
        out.append(issue("campaign", c["id"], "connection.funding", exc.message))
    if c["budget_mode"] == "none":
        out.append(issue("campaign", c["id"], "campaign.budget", "X campaigns need a daily or total budget on the campaign."))
    for gi, g in enumerate(tree["groups"]):
        f = g["fields"]
        if not ids(g["targeting"], "locations"):
            out.append(issue("group", g["id"], f"groups[{gi}].targeting.locations", "X line items need at least one location."))
        if f.get("bid_strategy") in ("MAX", "TARGET") and not f.get("bid_amount"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.bid_amount", "Set a bid amount."))
        for ai, ad in enumerate(g["ads"]):
            cr = ad["creative"]
            path = f"groups[{gi}].ads[{ai}]"
            if cr.get("existing_post_id"):
                continue
            text = str(cr.get("text") or "")
            if not text.strip():
                out.append(issue("ad", ad["id"], f"{path}.text", "Write the post text (or promote an existing post)."))
            elif _post_length(text) > 280:
                out.append(issue("ad", ad["id"], f"{path}.text", f"The post is {_post_length(text)} characters as X counts them (links = 23); X allows 280."))
            if cr.get("format") == "website_card":
                if not cr.get("destination_url") or not cr.get("card_headline"):
                    out.append(issue("ad", ad["id"], f"{path}.destination_url", "A website card needs a headline and a URL."))
                if not cr.get("media"):
                    out.append(issue("ad", ad["id"], f"{path}.media", "A website card needs an image or video."))
            if cr.get("format") in ("image", "video") and not cr.get("media"):
                out.append(issue("ad", ad["id"], f"{path}.media", "Upload the image or video."))
    return out


def lookup(conn: dict[str, Any], kind: str, q: str) -> list[dict[str, Any]]:
    if kind in ("locations", "languages", "interests"):
        body = _call(conn, "GET", f"{BASE}/targeting_criteria/{kind}", {"q": q[:80] or None, "count": 50})
        rows = [(str(d.get("targeting_value")), str(d.get("name"))) for d in body.get("data") or []]
    elif kind == "audiences":
        body = _call(conn, "GET", f"{BASE}/accounts/{_acct(conn)}/custom_audiences", {"count": 100})
        rows = [(str(d.get("id")), str(d.get("name"))) for d in body.get("data") or []]
    else:
        raise PlatformError(f"X has no {kind} list.", 404)
    return [{"id": i, "name": n} for i, n in rows if i and q.lower() in n.lower()][:50]


def upload_media(conn: dict[str, Any], filename: str, content: bytes) -> dict[str, Any]:
    video = filename.lower().rsplit(".", 1)[-1] in ("mp4", "mov")
    mime = "video/mp4" if video else "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    init = _call(conn, "POST", UPLOAD, form={"command": "INIT", "total_bytes": str(len(content)), "media_type": mime,
                                            "media_category": "amplify_video" if video else "tweet_image"})
    media_id = str(init.get("media_id_string"))
    for i in range(0, len(content), CHUNK):
        _call(conn, "POST", UPLOAD, form={"command": "APPEND", "media_id": media_id, "segment_index": str(i // CHUNK)}, files={"media": content[i: i + CHUNK]})
    done = _call(conn, "POST", UPLOAD, form={"command": "FINALIZE", "media_id": media_id})
    return {"media_id": str(done.get("media_key") or media_id), "kind": "video" if video else "image", "name": filename, "thumbnail_url": None}


# ---------------------------------------------------------------------------
def publish(conn: dict[str, Any], tree: dict[str, Any], mode: str) -> dict[str, Any]:
    acct = _acct(conn)
    c = tree["campaign"]
    undo = Rollback("x")
    path = "campaign"
    try:
        funding = _funding(conn)
        cparams: dict[str, Any] = {"name": c["name"][:255], "funding_instrument_id": funding["id"], "entity_status": "PAUSED",
                                   "start_time": _iso(c.get("starts_at")), "end_time": _iso(c.get("ends_at"))}
        cparams["daily_budget_amount_local_micro" if c["budget_mode"] == "daily" else "total_budget_amount_local_micro"] = micros(c["budget"] or 0)
        campaign = str(_call(conn, "POST", f"{BASE}/accounts/{acct}/campaigns", cparams)["data"]["id"])
        undo.add(f"campaign {campaign}", lambda: _call(conn, "DELETE", f"{BASE}/accounts/{acct}/campaigns/{campaign}"))
        groups: dict[str, str] = {}
        ads: dict[str, str] = {}
        for gi, g in enumerate(tree["groups"]):
            path = f"groups[{gi}]"
            f, t = g["fields"], g["targeting"]
            lparams: dict[str, Any] = {
                "campaign_id": campaign, "name": g["name"][:255], "objective": c["objective"], "product_type": "PROMOTED_TWEETS",
                "placements": ",".join(f.get("placements") or ["ALL_ON_TWITTER"]), "bid_strategy": f.get("bid_strategy") or "AUTO",
                "entity_status": "PAUSED", "start_time": _iso(g.get("starts_at") or c.get("starts_at")), "end_time": _iso(g.get("ends_at") or c.get("ends_at")),
            }
            if f.get("bid_amount"):
                lparams["bid_amount_local_micro"] = micros(f["bid_amount"])
            line = str(_call(conn, "POST", f"{BASE}/accounts/{acct}/line_items", lparams)["data"]["id"])
            groups[g["id"]] = line
            undo.add(f"line item {line}", lambda li=line: _call(conn, "DELETE", f"{BASE}/accounts/{acct}/line_items/{li}"))
            criteria = [("LOCATION", v) for v in ids(t, "locations")] + [("LANGUAGE", v) for v in ids(t, "languages")] + \
                       [("INTEREST", v) for v in ids(t, "interests")] + [("CUSTOM_AUDIENCE", v) for v in ids(t, "audiences")] + \
                       [("BROAD_KEYWORD", str(e["name"])) for e in entries(t, "keywords")]
            genders = set(t.get("genders") or [])
            if len(genders) == 1:
                criteria.append(("GENDER", "2" if "female" in genders else "1"))
            for kind, value in criteria:
                _call(conn, "POST", f"{BASE}/accounts/{acct}/targeting_criteria", {"line_item_id": line, "targeting_type": kind, "targeting_value": value})
            for ai, ad in enumerate(g["ads"]):
                path = f"groups[{gi}].ads[{ai}]"
                cr = ad["creative"]
                post = cr.get("existing_post_id")
                if not post:
                    media_keys = [m["media_id"] for m in cr.get("media") or []]
                    card_uri = None
                    if cr.get("format") == "website_card":
                        card = _call(conn, "POST", f"{BASE}/accounts/{acct}/cards", json_body={
                            "name": ad["name"][:80], "components": [{"type": "MEDIA", "media_key": media_keys[0]},
                                                                    {"type": "DETAILS", "title": cr.get("card_headline"), "destination": {"type": "WEBSITE", "url": cr.get("destination_url")}}]})
                        card_uri = (card.get("data") or {}).get("card_uri")
                        media_keys = []
                    created = _call(conn, "POST", f"{BASE}/accounts/{acct}/tweet", {
                        "text": cr.get("text"), "nullcast": True, "card_uri": card_uri, "media_keys": ",".join(media_keys) or None})
                    post = str((created.get("data") or {}).get("id_str") or (created.get("data") or {}).get("id"))
                    undo.add(f"post {post}", lambda p=post: _call(conn, "DELETE", f"{POSTS}/{p}"))
                promoted = _call(conn, "POST", f"{BASE}/accounts/{acct}/promoted_tweets", {"line_item_id": line, "tweet_ids": post})
                data = promoted.get("data")
                ads[ad["id"]] = str((data[0] if isinstance(data, list) else data or {}).get("id"))
        if mode == "active":
            path = "campaign"
            for line in groups.values():
                set_status(conn, "group", line, True)
            set_status(conn, "campaign", campaign, True)
    except PlatformError as exc:
        undo.run()
        raise PlatformError(exc.message, exc.status_code, path=path, auth=exc.auth) from None
    return {"campaign": campaign, "groups": groups, "ads": ads, "url": f"https://ads.x.com/campaign_form/{acct}/campaign/{campaign}"}


def set_status(conn: dict[str, Any], level: str, external_id: str, active: bool) -> None:
    acct = _acct(conn)
    if level == "ad":
        # Promoted posts are paused with `paused`, not entity_status.
        _call(conn, "PUT", f"{BASE}/accounts/{acct}/promoted_tweets/{external_id}", {"paused": not active})
        return
    kind = "campaigns" if level == "campaign" else "line_items"
    _call(conn, "PUT", f"{BASE}/accounts/{acct}/{kind}/{external_id}", {"entity_status": "ACTIVE" if active else "PAUSED"})


def import_results(conn: dict[str, Any], campaign_ids: list[str], since: str, until: str) -> list[dict[str, Any]]:
    """Synchronous stats allow at most 7 days per request: the window is split."""
    out: list[dict[str, Any]] = []
    if not campaign_ids:
        return out
    start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(until).replace(tzinfo=timezone.utc) + timedelta(days=1)
    while start < end:
        stop = min(start + timedelta(days=7), end)
        body = _call(conn, "GET", f"{BASE}/stats/accounts/{_acct(conn)}", {
            "entity": "CAMPAIGN", "entity_ids": ",".join(campaign_ids), "granularity": "DAY", "placement": "ALL_ON_TWITTER",
            "metric_groups": "ENGAGEMENT,BILLING,WEB_CONVERSION", "start_time": _iso(start.isoformat()), "end_time": _iso(stop.isoformat())})
        for item in body.get("data") or []:
            metrics = ((item.get("id_data") or [{}])[0].get("metrics")) or {}

            def series(name: str) -> list[Any]:
                return list(metrics.get(name) or [])

            spend, imps, clicks = series("billed_charge_local_micro"), series("impressions"), series("clicks")
            conv = (metrics.get("conversion_purchases") or {}).get("metric") if isinstance(metrics.get("conversion_purchases"), dict) else None
            for i in range((stop - start).days):
                day = (start + timedelta(days=i)).date().isoformat()
                out.append({"campaign_id": str(item.get("id")), "date": day,
                            "spend": (spend[i] or 0) / 1_000_000 if i < len(spend) else 0, "impressions": imps[i] if i < len(imps) else None,
                            "clicks": clicks[i] if i < len(clicks) else None, "conversions": conv[i] if isinstance(conv, list) and i < len(conv) else None})
        start = stop
    return out
