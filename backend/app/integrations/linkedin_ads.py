"""LinkedIn Ads adapter (SPEC-BE-065): LinkedIn Marketing API (REST).

Hierarchy: our campaign = LinkedIn campaign group, our group = LinkedIn
campaign, our ad = creative (a dark post owned by the organisation, referenced
by the creative). Everything is created as DRAFT first, because LinkedIn only
deletes drafts: on failure the drafts are deleted in reverse order. Headers:
Linkedin-Version (config LINKEDIN_API_VERSION), X-Restli-Protocol-Version.
The stored access token is used first; on a 401 it is refreshed once from the
refresh token (kept in memory; reconnecting saves a new one).
"""
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

from app.config import get_settings
from app.integrations.base_adapter import PlatformError, Rollback, http, ids, issue, short, unresolved

BASE = "https://api.linkedin.com/rest"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_tokens: dict[str, str] = {}

FACETS = {
    "locations": "urn:li:adTargetingFacet:locations", "languages": "urn:li:adTargetingFacet:interfaceLocales",
    "job_titles": "urn:li:adTargetingFacet:titles", "industries": "urn:li:adTargetingFacet:industries",
    "company_sizes": "urn:li:adTargetingFacet:staffCountRanges", "seniorities": "urn:li:adTargetingFacet:seniorities",
    "skills": "urn:li:adTargetingFacet:skills", "audiences": "urn:li:adTargetingFacet:audienceMatchingSegments",
}
LOOKUP_FACET = {"locations": "locations", "languages": "interfaceLocales", "titles": "titles", "industries": "industries",
                "company_sizes": "staffCountRanges", "seniorities": "seniorities", "skills": "skills", "audiences": "audienceMatchingSegments"}
# objective -> (cost type, optimisation target under maximum delivery)
OBJECTIVES = {
    "BRAND_AWARENESS": ("CPM", "MAX_REACH"), "WEBSITE_VISIT": ("CPC", "MAX_CLICK"), "ENGAGEMENT": ("CPM", "MAX_ENGAGEMENT"),
    "VIDEO_VIEW": ("CPV", "MAX_VIDEO_VIEW"), "LEAD_GENERATION": ("CPM", "MAX_LEAD"), "WEBSITE_CONVERSION": ("CPC", "MAX_CONVERSION"),
}
MIN_DAILY_USD = 10


def _token_key(f: dict[str, Any]) -> str:
    return f"{f.get('client_id')}:{str(f.get('refresh_token', ''))[-12:]}"


def _refresh(f: dict[str, Any]) -> str:
    resp = http("POST", TOKEN_URL, data={"grant_type": "refresh_token", "refresh_token": f.get("refresh_token"),
                                         "client_id": f.get("client_id"), "client_secret": f.get("client_secret")})
    body = resp.json() if resp.content else {}
    if resp.status_code >= 400 or "access_token" not in body:
        raise PlatformError(f"LinkedIn sign-in failed: {short(body.get('error_description') or body.get('error') or resp.status_code)}", 409, auth=True)
    _tokens[_token_key(f)] = body["access_token"]
    return str(body["access_token"])


def _call(conn: dict[str, Any], method: str, path: str, *, restli_method: str | None = None, **kwargs: Any) -> Any:
    f = conn["fields"]
    url = path if path.startswith("http") else f"{BASE}/{path}"
    for attempt in (0, 1):
        token = _tokens.get(_token_key(f)) or f.get("access_token", "")
        headers = {"Authorization": f"Bearer {token}", "Linkedin-Version": get_settings().LINKEDIN_API_VERSION, "X-Restli-Protocol-Version": "2.0.0"}
        if restli_method:
            headers["X-RestLi-Method"] = restli_method
        resp = http(method, url, headers=headers, **kwargs)
        if resp.status_code == 401 and attempt == 0 and f.get("refresh_token"):
            _refresh(f)
            continue
        break
    if resp.status_code >= 400:
        try:
            body = resp.json()
            message = body.get("message") or body
        except ValueError:
            message = resp.text
        auth = resp.status_code == 401
        raise PlatformError(f"LinkedIn: {short(message)}", 409 if auth else 502, auth=auth)
    created = resp.headers.get("x-restli-id") or resp.headers.get("x-linkedin-id")
    if created:
        return {"id": created}
    return resp.json() if resp.content else {}


def _acct(conn: dict[str, Any]) -> str:
    return str(conn["fields"].get("ad_account_id", "")).rsplit(":", 1)[-1]


def verify_account(fields: dict[str, str]) -> dict[str, Any]:
    data = _call({"fields": fields}, "GET", f"adAccounts/{str(fields['ad_account_id']).rsplit(':', 1)[-1]}")
    return {"name": data.get("name"), "currency": data.get("currency"), "status": data.get("status")}


def _ms(iso: str | None) -> int | None:
    return int(datetime.fromisoformat(iso).timestamp() * 1000) if iso else None


def _money(amount: Any, currency: str) -> dict[str, str]:
    return {"amount": f"{float(amount):.2f}", "currencyCode": currency}


def _targeting(t: dict[str, Any]) -> dict[str, Any]:
    clauses = []
    for key in ("locations", "languages", "job_titles", "industries", "company_sizes", "seniorities", "skills", "audiences"):
        urns = ids(t, key)
        if urns:
            clauses.append({"or": {FACETS[key]: urns}})
    return {"include": {"and": clauses}}


# ---------------------------------------------------------------------------
def validate(conn: dict[str, Any], tree: dict[str, Any]) -> list[dict[str, Any]]:
    out = unresolved(tree, tuple(FACETS), "LinkedIn")
    c = tree["campaign"]
    if not conn["fields"].get("organization_urn"):
        out.append(issue("campaign", c["id"], "connection.organization_urn", "Add your LinkedIn Page (organization URN) in Integrations; ads post as it."))
    try:
        account = verify_account(conn["fields"])
        if account.get("currency") and account["currency"] != c["currency"]:
            out.append(issue("campaign", c["id"], "campaign.currency", f"Your LinkedIn ad account bills in {account['currency']}, but this campaign is in {c['currency']}."))
    except PlatformError as exc:
        out.append(issue("campaign", c["id"], "connection", exc.message))
    usd = c["currency"] == "USD"
    for gi, g in enumerate(tree["groups"]):
        f = g["fields"]
        # Since API version 202605 a campaign must have an end date.
        if not (g.get("ends_at") or c.get("ends_at")):
            out.append(issue("group", g["id"], f"groups[{gi}].ends_at", "LinkedIn needs an end date (on this campaign or the campaign group)."))
        if usd and g["budget_mode"] == "daily" and (g["budget"] or 0) < MIN_DAILY_USD:
            out.append(issue("group", g["id"], f"groups[{gi}].budget", f"LinkedIn's minimum daily budget is {MIN_DAILY_USD} USD."))
        if c["objective"] == "LEAD_GENERATION" and not f.get("lead_form_id"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.lead_form_id", "Lead generation needs a Lead Gen Form ID."))
        if f.get("bid_strategy") in ("COST_CAP", "MANUAL_CPC", "MANUAL_CPM") and not f.get("bid_amount"):
            out.append(issue("group", g["id"], f"groups[{gi}].fields.bid_amount", "Set a bid amount."))
        formats = {a["creative"].get("format") for a in g["ads"]}
        if len(formats) > 1 and "text_ad" in formats:
            out.append(issue("group", g["id"], f"groups[{gi}].ads", "Text ads and sponsored content can't share a LinkedIn campaign; split them."))
        for ai, ad in enumerate(g["ads"]):
            cr = ad["creative"]
            path = f"groups[{gi}].ads[{ai}]"
            if not cr.get("destination_url") and c["objective"] != "LEAD_GENERATION":
                out.append(issue("ad", ad["id"], f"{path}.destination_url", "Add the landing page URL."))
            if cr.get("format") != "text_ad" and not cr.get("media"):
                out.append(issue("ad", ad["id"], f"{path}.media", "Upload an image, video or document."))
            if not str(cr.get("headline") or "").strip():
                out.append(issue("ad", ad["id"], f"{path}.headline", "Add a headline."))
            if cr.get("format") == "text_ad" and len(str(cr.get("headline") or "")) > 25:
                out.append(issue("ad", ad["id"], f"{path}.headline", "Text ad headlines allow 25 characters."))
    return out


def lookup(conn: dict[str, Any], kind: str, q: str) -> list[dict[str, Any]]:
    facet = LOOKUP_FACET.get(kind)
    if facet is None:
        raise PlatformError(f"LinkedIn has no {kind} list.", 404)
    data = _call(conn, "GET", f"adTargetingEntities?q=typeahead&facet={quote('urn:li:adTargetingFacet:' + facet)}&query={quote(q[:80])}")
    return [{"id": e.get("urn"), "name": e.get("name"), "type": facet} for e in data.get("elements") or [] if e.get("urn")][:50]


def upload_media(conn: dict[str, Any], filename: str, content: bytes) -> dict[str, Any]:
    owner = conn["fields"].get("organization_urn")
    if not owner:
        raise PlatformError("Add your LinkedIn Page (organization URN) in Integrations first.", 409)
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext in ("mp4", "mov", "avi", "webm"):
        init = _call(conn, "POST", "videos?action=initializeUpload",
                     json={"initializeUploadRequest": {"owner": owner, "fileSizeBytes": len(content), "uploadCaptions": False, "uploadThumbnail": False}})
        value = init.get("value") or {}
        etags = []
        for part in value.get("uploadInstructions") or []:
            chunk = content[int(part["firstByte"]): int(part["lastByte"]) + 1]
            resp = http("PUT", part["uploadUrl"], content=chunk, headers={"Content-Type": "application/octet-stream"})
            if resp.status_code >= 400:
                raise PlatformError("LinkedIn rejected the video upload.", 502)
            etags.append(resp.headers.get("etag", ""))
        _call(conn, "POST", "videos?action=finalizeUpload",
              json={"finalizeUploadRequest": {"video": value.get("video"), "uploadToken": value.get("uploadToken", ""), "uploadedPartIds": etags}})
        return {"media_id": value.get("video"), "kind": "video", "name": filename, "thumbnail_url": None}
    kind = "documents" if ext in ("pdf", "ppt", "pptx", "doc", "docx") else "images"
    init = _call(conn, "POST", f"{kind}?action=initializeUpload", json={"initializeUploadRequest": {"owner": owner}})
    value = init.get("value") or {}
    resp = http("PUT", value.get("uploadUrl", ""), content=content, headers={"Content-Type": "application/octet-stream"})
    if resp.status_code >= 400:
        raise PlatformError("LinkedIn rejected the upload.", 502)
    urn = value.get("image") or value.get("document")
    return {"media_id": urn, "kind": "image" if kind == "images" else "video", "name": filename, "thumbnail_url": None}


# ---------------------------------------------------------------------------
def _campaign_body(acct: str, group_urn: str, c: dict[str, Any], g: dict[str, Any]) -> dict[str, Any]:
    f, cur = g["fields"], c["currency"]
    cost, target = OBJECTIVES.get(c["objective"], ("CPC", "MAX_CLICK"))
    strategy = f.get("bid_strategy") or "MAXIMUM_DELIVERY"
    body: dict[str, Any] = {
        "account": f"urn:li:sponsoredAccount:{acct}", "campaignGroup": group_urn, "name": g["name"][:100], "status": "DRAFT",
        "type": "TEXT_AD" if any(a["creative"].get("format") == "text_ad" for a in g["ads"]) else "SPONSORED_UPDATES",
        "objectiveType": c["objective"], "costType": cost, "locale": {"country": "US", "language": "en"},
        "targetingCriteria": _targeting(g["targeting"]), "audienceExpansionEnabled": bool(f.get("audience_expansion")),
        "offsiteDeliveryEnabled": False, "politicalIntent": "NOT_POLITICAL",
        "runSchedule": {k: v for k, v in (("start", _ms(g.get("starts_at") or c.get("starts_at")) or int(time.time() * 1000)), ("end", _ms(g.get("ends_at") or c.get("ends_at")))) if v},
    }
    if strategy == "MAXIMUM_DELIVERY":
        body["optimizationTargetType"] = target
    elif strategy == "COST_CAP":
        body.update(optimizationTargetType=target, unitCost=_money(f["bid_amount"], cur))
    else:
        body.update(costType="CPC" if strategy == "MANUAL_CPC" else "CPM", optimizationTargetType="NONE", unitCost=_money(f["bid_amount"], cur))
    if g["budget_mode"] == "daily" and g["budget"]:
        body["dailyBudget"] = _money(g["budget"], cur)
    elif g["budget_mode"] == "total" and g["budget"]:
        body["totalBudget"] = _money(g["budget"], cur)
    if f.get("conversion_ids"):
        body["conversions"] = [f"urn:lla:llaPartnerConversion:{x.strip()}" for x in str(f["conversion_ids"]).split(",") if x.strip()]
    return body


def _post_body(owner: str, ad: dict[str, Any]) -> dict[str, Any]:
    cr = ad["creative"]
    media = (cr.get("media") or [{}])[0]
    content: dict[str, Any]
    if cr.get("format") in ("video", "document") or str(media.get("media_id", "")).startswith(("urn:li:video", "urn:li:document")):
        content = {"media": {"id": media.get("media_id"), "title": cr.get("headline") or ad["name"]}}
    else:
        content = {"article": {"source": cr.get("destination_url"), "title": cr.get("headline"), "description": cr.get("description"), "thumbnail": media.get("media_id")}}
    return {"author": owner, "commentary": cr.get("intro_text") or "", "visibility": "PUBLIC", "lifecycleState": "PUBLISHED",
            "distribution": {"feedDistribution": "NONE", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "content": content, "isReshareDisabledByAuthor": False}


def _urn_id(value: str) -> str:
    return value.rsplit(":", 1)[-1]


def publish(conn: dict[str, Any], tree: dict[str, Any], mode: str) -> dict[str, Any]:
    acct = _acct(conn)
    owner = conn["fields"].get("organization_urn", "")
    c = tree["campaign"]
    undo = Rollback("linkedin")
    path = "campaign"
    try:
        gbody: dict[str, Any] = {"account": f"urn:li:sponsoredAccount:{acct}", "name": c["name"][:100], "status": "DRAFT",
                                 "runSchedule": {k: v for k, v in (("start", _ms(c.get("starts_at")) or int(time.time() * 1000)), ("end", _ms(c.get("ends_at")))) if v}}
        if c["budget_mode"] == "total" and c["budget"]:
            gbody["totalBudget"] = _money(c["budget"], c["currency"])
        group_id = _urn_id(_call(conn, "POST", f"adAccounts/{acct}/adCampaignGroups", json=gbody)["id"])
        group_urn = f"urn:li:sponsoredCampaignGroup:{group_id}"
        undo.add(f"group {group_id}", lambda: _call(conn, "DELETE", f"adAccounts/{acct}/adCampaignGroups/{group_id}"))
        groups: dict[str, str] = {}
        ads: dict[str, str] = {}
        for gi, g in enumerate(tree["groups"]):
            path = f"groups[{gi}]"
            camp_id = _urn_id(_call(conn, "POST", f"adAccounts/{acct}/adCampaigns", json=_campaign_body(acct, group_urn, c, g))["id"])
            groups[g["id"]] = camp_id
            undo.add(f"campaign {camp_id}", lambda cid=camp_id: _call(conn, "DELETE", f"adAccounts/{acct}/adCampaigns/{cid}"))
            for ai, ad in enumerate(g["ads"]):
                path = f"groups[{gi}].ads[{ai}]"
                cr = ad["creative"]
                if cr.get("format") == "text_ad":
                    content: dict[str, Any] = {"textAd": {"headline": cr.get("headline"), "description": cr.get("description"), "landingPage": cr.get("destination_url")}}
                else:
                    post_urn = _call(conn, "POST", "posts", json=_post_body(owner, ad))["id"]
                    undo.add(f"post {post_urn}", lambda p=post_urn: _call(conn, "DELETE", f"posts/{quote(p)}"))
                    content = {"reference": post_urn}
                creative = _call(conn, "POST", f"adAccounts/{acct}/creatives", json={
                    "campaign": f"urn:li:sponsoredCampaign:{camp_id}", "content": content, "intendedStatus": "ACTIVE",
                    **({"leadgenCallToAction": {"destination": f"urn:li:adForm:{g['fields']['lead_form_id']}", "label": cr.get("cta") or "LEARN_MORE"}} if g["fields"].get("lead_form_id") else {}),
                })["id"]
                ads[ad["id"]] = creative
        if mode == "active":
            path = "campaign"
            _set(conn, "campaign", group_id, "ACTIVE")
            for camp_id in groups.values():
                _set(conn, "group", camp_id, "ACTIVE")
        else:
            _set(conn, "campaign", group_id, "PAUSED")
            for camp_id in groups.values():
                _set(conn, "group", camp_id, "PAUSED")
    except PlatformError as exc:
        undo.run()
        raise PlatformError(exc.message, exc.status_code, path=path, auth=exc.auth) from None
    return {"campaign": group_id, "groups": groups, "ads": ads,
            "url": f"https://www.linkedin.com/campaignmanager/accounts/{acct}/campaign-groups/{group_id}"}


def _set(conn: dict[str, Any], level: str, external_id: str, status: str) -> None:
    acct = _acct(conn)
    if level == "ad":
        _call(conn, "POST", f"adAccounts/{acct}/creatives/{quote(external_id)}", restli_method="PARTIAL_UPDATE",
              json={"patch": {"$set": {"intendedStatus": status}}})
        return
    path = "adCampaignGroups" if level == "campaign" else "adCampaigns"
    _call(conn, "POST", f"adAccounts/{acct}/{path}/{external_id}", restli_method="PARTIAL_UPDATE", json={"patch": {"$set": {"status": status}}})


def set_status(conn: dict[str, Any], level: str, external_id: str, active: bool) -> None:
    _set(conn, level, external_id, "ACTIVE" if active else "PAUSED")


def import_results(conn: dict[str, Any], campaign_ids: list[str], since: str, until: str) -> list[dict[str, Any]]:
    if not campaign_ids:
        return []
    s, u = datetime.fromisoformat(since), datetime.fromisoformat(until)
    urns = ",".join(quote(f"urn:li:sponsoredCampaignGroup:{c}", safe="") for c in campaign_ids)
    data = _call(conn, "GET", "adAnalytics?q=analytics&pivot=CAMPAIGN_GROUP&timeGranularity=DAILY"
                 f"&dateRange=(start:(year:{s.year},month:{s.month},day:{s.day}),end:(year:{u.year},month:{u.month},day:{u.day}))"
                 f"&campaignGroups=List({urns})&fields=costInLocalCurrency,impressions,clicks,externalWebsiteConversions,oneClickLeads,dateRange,pivotValues")
    out = []
    for e in data.get("elements") or []:
        start = (e.get("dateRange") or {}).get("start") or {}
        pivot = (e.get("pivotValues") or [""])[0]
        out.append({"campaign_id": _urn_id(str(pivot)), "date": f"{start.get('year')}-{int(start.get('month', 1)):02d}-{int(start.get('day', 1)):02d}",
                    "spend": e.get("costInLocalCurrency"), "impressions": e.get("impressions"), "clicks": e.get("clicks"),
                    "conversions": (e.get("externalWebsiteConversions") or 0) + (e.get("oneClickLeads") or 0)})
    return out

