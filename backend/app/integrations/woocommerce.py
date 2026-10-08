"""WooCommerce REST v3 client for shipping (SPEC-BE-058).

Basic auth with the consumer key/secret from SPEC-BE-052, over https only,
through verify.client_factory after the SSRF guard (swappable in tests).

Mapping (documented, SPEC-BE-058):
- flat_rate.settings.cost -> rate_cents when it is a plain number; a formula
  (e.g. "10 + [qty]*2") is kept in metadata.cost_formula with rate_cents 0
  and flagged by validation.
- free_shipping -> free_shipping; settings.min_amount -> conditions.min_subtotal_cents.
- local_pickup / pickup_location -> local_pickup.
- Anything else -> carrier_calculated with the method title (computed by the
  plugin at checkout, never by us).
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations import verify


class WooError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


_NUMBER = re.compile(r"^\s*\d+(\.\d+)?\s*$")


def _base(fields: dict[str, str]) -> str:
    try:
        return verify._public_https_base(fields["site_url"]) + "/wp-json/wc/v3"
    except verify.VerifyError as exc:
        raise WooError(str(exc)) from None


def request(fields: dict[str, str], method: str, path: str, json: Any = None) -> Any:
    try:
        with verify.client_factory() as client:
            resp = client.request(method, f"{_base(fields)}{path}", json=json, auth=(fields["consumer_key"], fields["consumer_secret"]))
    except verify.httpx.TimeoutException:
        raise WooError("WooCommerce didn't answer within 20 seconds.") from None
    except verify.httpx.HTTPError as exc:
        raise WooError(f"Couldn't reach WooCommerce ({type(exc).__name__}).") from None
    if resp.status_code >= 400:
        raise WooError(f"WooCommerce error: {verify._json_error(resp)}", resp.status_code)
    return resp.json()


def _cents(value: Any) -> int | None:
    try:
        return int((Decimal(str(value).strip()) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def _setting(method: dict[str, Any], key: str) -> str:
    return str(((method.get("settings") or {}).get(key) or {}).get("value") or "")


def read_shipping(fields: dict[str, str]) -> dict[str, Any]:
    currency = ""
    try:
        general = request(fields, "GET", "/settings/general/woocommerce_currency")
        currency = str(general.get("value") or "").upper()
    except WooError:
        pass
    zones: list[dict[str, Any]] = []
    for z in request(fields, "GET", "/shipping/zones"):
        zid = z.get("id")
        locations = request(fields, "GET", f"/shipping/zones/{zid}/locations")
        countries = [loc["code"] for loc in locations if loc.get("type") == "country"]
        regions = [loc["code"] for loc in locations if loc.get("type") in ("state", "postcode", "continent")]
        methods = []
        for m in request(fields, "GET", f"/shipping/zones/{zid}/methods"):
            mid, title = m.get("method_id"), m.get("title") or m.get("method_title") or "Shipping"
            meta: dict[str, Any] = {}
            conditions: dict[str, int] = {}
            if mid == "flat_rate":
                cost = _setting(m, "cost")
                if cost and not _NUMBER.match(cost):
                    rate, meta["cost_formula"] = 0, cost
                else:
                    rate = _cents(cost or 0) or 0
                kind = "flat_rate"
            elif mid == "free_shipping":
                kind, rate = "free_shipping", 0
                minimum = _cents(_setting(m, "min_amount"))
                if minimum:
                    conditions["min_subtotal_cents"] = minimum
                meta["requires"] = _setting(m, "requires") or None
            elif mid in ("local_pickup", "pickup_location"):
                kind, rate = "local_pickup", _cents(_setting(m, "cost") or 0) or 0
            else:
                kind, rate, meta["plugin_method"] = "carrier_calculated", 0, mid
            methods.append(
                {
                    "external_id": f"{zid}:{m.get('instance_id')}",
                    "name": title,
                    "carrier": "WooCommerce" if kind != "carrier_calculated" else str(m.get("method_title") or mid),
                    "method_type": kind,
                    "rate_cents": rate,
                    "conditions": conditions,
                    "active": bool(m.get("enabled", True)),
                    "metadata": {k: v for k, v in meta.items() if v},
                }
            )
        rest = zid == 0
        zones.append(
            {
                "external_id": str(zid),
                "name": z.get("name") or ("Rest of world" if rest else "Zone"),
                "country_codes": countries,
                "regions": regions,
                "rest_of_world": rest,
                "profile": None,
                "methods": methods,
            }
        )
    return {"currency": currency, "zones": zones, "unsupported": ["Shipping classes and per-class costs", "Table-rate plugins (shown as carrier-calculated)"]}


def update_method(fields: dict[str, str], method_external_id: str, changes: dict[str, Any], method_type: str) -> None:
    zone_id, instance_id = method_external_id.split(":", 1)
    body: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    if "active" in changes:
        body["enabled"] = bool(changes["active"])
    if "name" in changes:
        settings["title"] = changes["name"]
    if "rate_cents" in changes and method_type in ("flat_rate", "local_pickup"):
        settings["cost"] = str(Decimal(changes["rate_cents"]) / 100)
    if "conditions" in changes and method_type == "free_shipping":
        minimum = (changes["conditions"] or {}).get("min_subtotal_cents")
        settings["min_amount"] = str(Decimal(minimum) / 100) if minimum else ""
        settings["requires"] = "min_amount" if minimum else ""
    if settings:
        body["settings"] = settings
    request(fields, "PUT", f"/shipping/zones/{zone_id}/methods/{instance_id}", body)


def create_zones(fields: dict[str, str], zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Guided setup push: creates each zone, its countries, and its methods.
    Returns the created external ids per zone/method, in order."""
    created = []
    for z in zones:
        zone = request(fields, "POST", "/shipping/zones", {"name": z["name"]})
        zid = zone["id"]
        request(fields, "PUT", f"/shipping/zones/{zid}/locations", [{"code": c, "type": "country"} for c in z["country_codes"]])
        method_ids: list[str | None] = []
        for m in z["methods"]:
            method_id = {"flat_rate": "flat_rate", "free_shipping": "free_shipping", "local_pickup": "local_pickup"}.get(m["method_type"])
            if method_id is None:
                method_ids.append(None)
                continue
            settings: dict[str, Any] = {"title": m["name"]}
            if method_id in ("flat_rate", "local_pickup"):
                settings["cost"] = str(Decimal(m["rate_cents"]) / 100)
            minimum = (m.get("conditions") or {}).get("min_subtotal_cents")
            if method_id == "free_shipping" and minimum:
                settings.update(min_amount=str(Decimal(minimum) / 100), requires="min_amount")
            made = request(fields, "POST", f"/shipping/zones/{zid}/methods", {"method_id": method_id, "settings": settings})
            method_ids.append(f"{zid}:{made.get('instance_id')}")
        created.append({"zone": str(zid), "methods": method_ids})
    return created
