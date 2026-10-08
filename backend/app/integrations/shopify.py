"""Shopify Admin API client for shipping (SPEC-BE-058).

Auth (SPEC-BE-058 decision 3):
- older custom apps: a static Admin API access token (`admin_token`);
- stores created after 2026-01-01: a Dev Dashboard client ID + secret, exchanged
  for a 24-hour token with the client-credentials grant
  (POST https://{shop}/admin/oauth/access_token, grant_type=client_credentials).
  Tokens are cached in-process until 5 minutes before they expire.

Every call goes through verify.client_factory (httpx, 20 s timeout, no
redirects) after the SSRF guard on the shop host, so tests swap the transport
with httpx.MockTransport exactly like the Meta and verify clients.

Shipping read: `deliveryProfiles` (scope read_shipping). Write:
`deliveryProfileUpdate` (scope write_shipping) on method definitions.
"""
import time
from decimal import Decimal
from typing import Any

import structlog

from app.config import get_settings
from app.integrations import verify

logger = structlog.get_logger(__name__)

_token_cache: dict[str, tuple[str, float]] = {}


class ShopifyError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


def shop_base(shop_domain: str) -> str:
    try:
        return verify._public_https_base(shop_domain if "://" in shop_domain else f"https://{shop_domain}")
    except verify.VerifyError as exc:
        raise ShopifyError(str(exc)) from None


def access_token(fields: dict[str, str]) -> str:
    if fields.get("admin_token"):
        return fields["admin_token"]
    client_id, client_secret = fields.get("client_id"), fields.get("client_secret")
    if not (client_id and client_secret):
        raise ShopifyError("Add an Admin API access token, or a client ID and secret.")
    base = shop_base(fields["shop_domain"])
    cached = _token_cache.get(f"{base}|{client_id}")
    if cached and cached[1] > time.time():
        return cached[0]
    with verify.client_factory() as client:
        resp = client.post(
            f"{base}/admin/oauth/access_token",
            data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        )
    if resp.status_code >= 400:
        raise ShopifyError(f"Shopify rejected the client credentials ({verify._json_error(resp)}).", resp.status_code)
    body = resp.json()
    token = body.get("access_token")
    if not token:
        raise ShopifyError("Shopify didn't return an access token.")
    _token_cache[f"{base}|{client_id}"] = (token, time.time() + int(body.get("expires_in") or 86400) - 300)
    return str(token)


def graphql(fields: dict[str, str], query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    base = shop_base(fields["shop_domain"])
    url = f"{base}/admin/api/{get_settings().SHOPIFY_API_VERSION}/graphql.json"
    try:
        with verify.client_factory() as client:
            resp = client.post(
                url,
                json={"query": query, "variables": variables or {}},
                headers={"X-Shopify-Access-Token": access_token(fields)},
            )
    except verify.httpx.TimeoutException:
        raise ShopifyError("Shopify didn't answer within 20 seconds.") from None
    except verify.httpx.HTTPError as exc:
        raise ShopifyError(f"Couldn't reach Shopify ({type(exc).__name__}).") from None
    if resp.status_code >= 400:
        raise ShopifyError(f"Shopify error: {verify._json_error(resp)}", resp.status_code)
    body = resp.json()
    if body.get("errors"):
        first = body["errors"][0] if isinstance(body["errors"], list) else body["errors"]
        raise ShopifyError(f"Shopify error: {verify._short((first or {}).get('message') if isinstance(first, dict) else first)}")
    return body.get("data") or {}


PROFILES_QUERY = """
query Shipping {
  shop { currencyCode }
  deliveryProfiles(first: 25) { nodes {
    id name default
    profileLocationGroups { locationGroupZones(first: 100) { nodes {
      zone { id name countries { code { countryCode restOfWorld } provinces { code name } } }
      methodDefinitions(first: 50) { nodes {
        id name active description
        rateProvider {
          ... on DeliveryRateDefinition { price { amount currencyCode } }
          ... on DeliveryParticipant { carrierService { id formattedName } fixedFee { amount } percentageOfRateFee }
        }
        methodConditions { field operator conditionCriteria {
          ... on MoneyV2 { amount currencyCode }
          ... on Weight { value unit }
        } }
      } }
    } } }
  } }
  carrierServices(first: 25) { nodes { id formattedName active } }
}
"""

_WEIGHT_TO_G = {"GRAMS": 1, "KILOGRAMS": 1000, "OUNCES": 28.3495, "POUNDS": 453.592}


def _cents(amount: Any) -> int:
    return int((Decimal(str(amount or 0)) * 100).to_integral_value())


def _conditions(method: dict[str, Any]) -> dict[str, int]:
    """Shopify methodConditions -> our conditions jsonb (SPEC-BE-058 mapping)."""
    out: dict[str, int] = {}
    for cond in method.get("methodConditions") or []:
        crit = cond.get("conditionCriteria") or {}
        upper = cond.get("operator") == "LESS_THAN_OR_EQUAL_TO"
        if cond.get("field") == "TOTAL_PRICE" and "amount" in crit:
            out["max_subtotal_cents" if upper else "min_subtotal_cents"] = _cents(crit["amount"])
        elif cond.get("field") == "TOTAL_WEIGHT" and "value" in crit:
            grams = int(float(crit["value"]) * _WEIGHT_TO_G.get(str(crit.get("unit")), 1))
            out["max_weight_g" if upper else "min_weight_g"] = grams
    return out


def read_shipping(fields: dict[str, str]) -> dict[str, Any]:
    """Normalized config: {currency, zones: [{external_id, name, country_codes,
    regions, rest_of_world, profile, methods: [...]}], unsupported: [...]}."""
    data = graphql(fields, PROFILES_QUERY)
    currency = ((data.get("shop") or {}).get("currencyCode") or "").upper()
    zones: list[dict[str, Any]] = []
    for profile in (data.get("deliveryProfiles") or {}).get("nodes") or []:
        for group in profile.get("profileLocationGroups") or []:
            for lgz in (group.get("locationGroupZones") or {}).get("nodes") or []:
                zone = lgz.get("zone") or {}
                countries = zone.get("countries") or []
                rest = any((c.get("code") or {}).get("restOfWorld") for c in countries)
                methods = []
                for m in (lgz.get("methodDefinitions") or {}).get("nodes") or []:
                    rp = m.get("rateProvider") or {}
                    conditions = _conditions(m)
                    if "carrierService" in rp:
                        kind, rate = "carrier_calculated", 0
                        extra = {"carrier_service": (rp.get("carrierService") or {}).get("formattedName"), "fixed_fee": (rp.get("fixedFee") or {}).get("amount"), "percentage_fee": rp.get("percentageOfRateFee")}
                    else:
                        rate = _cents((rp.get("price") or {}).get("amount"))
                        kind, extra = ("free_shipping" if rate == 0 else "flat_rate"), {}
                    methods.append(
                        {
                            "external_id": m["id"],
                            "name": m.get("name") or "Shipping",
                            "carrier": extra.get("carrier_service") or "Shopify",
                            "method_type": kind,
                            "rate_cents": rate,
                            "conditions": conditions,
                            "active": bool(m.get("active", True)),
                            "metadata": {k: v for k, v in {**extra, "description": m.get("description")}.items() if v not in (None, "")},
                        }
                    )
                name = zone.get("name") or "Zone"
                zones.append(
                    {
                        # One row per (profile, location group, zone); Shopify reuses zone ids per group.
                        "external_id": f"{profile['id']}|{zone.get('id')}",
                        "name": name if profile.get("default") else f"{profile.get('name')}: {name}",
                        "country_codes": [] if rest else [(c.get("code") or {}).get("countryCode") for c in countries if (c.get("code") or {}).get("countryCode")],
                        "regions": [p.get("name") for c in countries for p in c.get("provinces") or [] if p.get("name")],
                        "rest_of_world": rest,
                        "profile": profile.get("name"),
                        "methods": methods,
                    }
                )
    unsupported = [
        "Checkout customizations and Shopify Functions (not available through the API)",
        "Local delivery and pickup settings per location are read-only in the Admin API",
    ]
    return {"currency": currency, "zones": zones, "unsupported": unsupported}


UPDATE_METHOD = """
mutation UpdateMethod($id: ID!, $profile: DeliveryProfileInput!) {
  deliveryProfileUpdate(id: $id, profile: $profile) { profile { id } userErrors { field message } }
}
"""


def update_method(fields: dict[str, str], zone_external_id: str, method_external_id: str, changes: dict[str, Any], currency: str) -> None:
    """Pushes a rate change on an imported method (decision 2: store first).
    Supported: name, active, price (flat/free), min/max subtotal conditions."""
    profile_id, _zone_id = zone_external_id.split("|", 1)
    method: dict[str, Any] = {"id": method_external_id}
    if "name" in changes:
        method["name"] = changes["name"]
    if "active" in changes:
        method["active"] = bool(changes["active"])
    if "rate_cents" in changes:
        method["rateDefinition"] = {"price": {"amount": str(Decimal(changes["rate_cents"]) / 100), "currencyCode": currency}}
    if "conditions" in changes:
        conds = []
        c = changes["conditions"] or {}
        if c.get("min_subtotal_cents"):
            conds.append({"criteria": {"amount": str(Decimal(c["min_subtotal_cents"]) / 100), "currencyCode": currency}, "operator": "GREATER_THAN_OR_EQUAL_TO"})
        if c.get("max_subtotal_cents"):
            conds.append({"criteria": {"amount": str(Decimal(c["max_subtotal_cents"]) / 100), "currencyCode": currency}, "operator": "LESS_THAN_OR_EQUAL_TO"})
        method["priceConditionsToCreate"] = conds
    data = graphql(
        fields,
        UPDATE_METHOD,
        {"id": profile_id, "profile": {"locationGroupsToUpdate": [], "methodDefinitionsToUpdate": [method]}},
    )
    errors = ((data.get("deliveryProfileUpdate") or {}).get("userErrors")) or []
    if errors:
        raise ShopifyError("Shopify refused the change: " + "; ".join(str(e.get("message")) for e in errors))


CREATE_ZONE = """
mutation CreateZone($id: ID!, $profile: DeliveryProfileInput!) {
  deliveryProfileUpdate(id: $id, profile: $profile) { profile { id } userErrors { field message } }
}
"""
DEFAULT_PROFILE = "query { deliveryProfiles(first: 10) { nodes { id default profileLocationGroups { locationGroup { id } } } } }"


def create_zones(fields: dict[str, str], zones: list[dict[str, Any]], currency: str) -> None:
    """Guided setup push (3B): adds the zones + flat/free methods to the general profile."""
    data = graphql(fields, DEFAULT_PROFILE)
    profile = next((p for p in (data.get("deliveryProfiles") or {}).get("nodes") or [] if p.get("default")), None)
    if profile is None or not profile.get("profileLocationGroups"):
        raise ShopifyError("The store has no general shipping profile to add zones to.")
    group_id = profile["profileLocationGroups"][0]["locationGroup"]["id"]
    zones_input = []
    for z in zones:
        methods = []
        for m in z["methods"]:
            if m["method_type"] not in ("flat_rate", "free_shipping"):
                continue
            entry: dict[str, Any] = {
                "name": m["name"],
                "active": True,
                "rateDefinition": {"price": {"amount": str(Decimal(m["rate_cents"]) / 100), "currencyCode": currency}},
            }
            minimum = (m.get("conditions") or {}).get("min_subtotal_cents")
            if minimum:
                entry["priceConditionsToCreate"] = [{"criteria": {"amount": str(Decimal(minimum) / 100), "currencyCode": currency}, "operator": "GREATER_THAN_OR_EQUAL_TO"}]
            methods.append(entry)
        zones_input.append(
            {"name": z["name"], "countries": [{"code": c, "includeAllProvinces": True} for c in z["country_codes"]], "methodDefinitionsToCreate": methods}
        )
    result = graphql(
        fields,
        CREATE_ZONE,
        {"id": profile["id"], "profile": {"locationGroupsToUpdate": [{"id": group_id, "zonesToCreate": zones_input}]}},
    )
    errors = ((result.get("deliveryProfileUpdate") or {}).get("userErrors")) or []
    if errors:
        raise ShopifyError("Shopify refused the setup: " + "; ".join(str(e.get("message")) for e in errors))
