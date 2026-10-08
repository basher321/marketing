"""Shipping engine (SPEC-BE-043, SPEC-BE-058).

- Zones & rates: list, create, update, enable/disable (rates = shipping_policies).
- Store sync: detect the connected store's shipping (Shopify / WooCommerce),
  import/refresh it (upsert by source + external_id; rows the store removed are
  deactivated, never deleted), status + errors + audit.
- Guided setup (3B) for stores without a usable setup, or no store at all.
- Validation before activation.
- Edits to a store-sourced rate are pushed to the store first (decision 2);
  what the store API can't write is refused with 409.

Money is integer cents in the tenant currency, returned in major units via
Decimal. Calculating shipping on orders is out of scope.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.orm import Session, selectinload

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.shipping import ShippingPolicy, ShippingZone
from app.models.tenant import Tenant
from app.schemas.shipping import (
    RateConditions,
    ShippingRateCreate,
    ShippingRateUpdate,
    ShippingSetup,
    ShippingZoneCreate,
)

logger = structlog.get_logger(__name__)

STORE_SOURCES = ("shopify", "woocommerce")
STORE_LABEL = {"shopify": "Shopify", "woocommerce": "WooCommerce"}
PAID_TYPES = ("flat_rate", "local_delivery")


def _major(cents: int | None) -> float | None:
    return None if cents is None else float(Decimal(cents) / 100)


def _cents(amount: Decimal | None) -> int | None:
    return None if amount is None else int(amount * 100)


def _conditions_cents(c: RateConditions | None) -> dict[str, int]:
    if c is None:
        return {}
    out = {
        "min_subtotal_cents": _cents(c.min_subtotal),
        "max_subtotal_cents": _cents(c.max_subtotal),
        "min_weight_g": c.min_weight_g,
        "max_weight_g": c.max_weight_g,
    }
    return {k: v for k, v in out.items() if v is not None}


def _conditions_major(c: dict[str, Any] | None) -> dict[str, Any]:
    c = c or {}
    out: dict[str, Any] = {}
    if c.get("min_subtotal_cents") is not None:
        out["min_subtotal"] = _major(c["min_subtotal_cents"])
    if c.get("max_subtotal_cents") is not None:
        out["max_subtotal"] = _major(c["max_subtotal_cents"])
    for key in ("min_weight_g", "max_weight_g"):
        if c.get(key) is not None:
            out[key] = c[key]
    return out


def _read_only(rate: ShippingPolicy) -> bool:
    # What the store APIs can't write (SPEC-BE-058 decision 2): carrier-
    # calculated methods anywhere, and WooCommerce cost formulas.
    if rate.source not in STORE_SOURCES:
        return False
    return rate.method_type == "carrier_calculated" or bool((rate.extra_metadata or {}).get("cost_formula"))


def _rate_dict(rate: ShippingPolicy) -> dict[str, Any]:
    meta = dict(rate.extra_metadata or {})
    validation = meta.pop("validation", None)
    return {
        "id": rate.id,
        "name": rate.name,
        "carrier": rate.carrier,
        "rate": _major(rate.rate_cents),
        "free_over": _major(rate.free_over_cents),
        "sla_days_min": rate.sla_days_min,
        "sla_days_max": rate.sla_days_max,
        "cutoff_time": rate.cutoff_time,
        "active": rate.active,
        "source": rate.source or "local",
        "external_id": rate.external_id,
        "method_type": rate.method_type or "flat_rate",
        "conditions": _conditions_major(rate.conditions),
        "metadata": meta,
        "validation": validation,
        "read_only": _read_only(rate),
    }


def _zone_dict(zone: ShippingZone) -> dict[str, Any]:
    meta = zone.extra_metadata or {}
    return {
        "id": zone.id,
        "name": zone.name,
        # bpchar values come back as-is; strip in case of padding.
        "country_codes": [c.strip() for c in zone.country_codes],
        "regions": list(zone.regions or []),
        "active": zone.active,
        # Rates are ordered by rate_cents, then name (the relationship's order_by).
        "rates": [_rate_dict(r) for r in zone.rates if r.tenant_id == zone.tenant_id],
        "source": zone.source or "local",
        "external_id": zone.external_id,
        "rest_of_world": bool(meta.get("rest_of_world")),
        "validation": meta.get("validation"),
    }


def _zones(db: Session, tenant_id: str) -> list[ShippingZone]:
    return (
        db.query(ShippingZone)
        .options(selectinload(ShippingZone.rates))
        .filter(ShippingZone.tenant_id == tenant_id)
        .order_by(ShippingZone.name, ShippingZone.id)
        .all()
    )


def _currency(db: Session, tenant_id: str) -> str:
    return (db.query(Tenant.currency).filter(Tenant.id == tenant_id).scalar() or "USD").strip()


def list_zones(db: Session, tenant_id: str) -> dict[str, Any]:
    return {"currency": _currency(db, tenant_id), "zones": [_zone_dict(z) for z in _zones(db, tenant_id)]}


# ---------------------------------------------------------------------------
# Validation (SPEC-BE-058): errors block activation, warnings don't
# ---------------------------------------------------------------------------
def _issue(code: str, message: str, severity: str, zone: dict[str, Any], rate: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "zone_id": str(zone["id"]) if zone.get("id") else None,
        "rate_id": str(rate["id"]) if rate and rate.get("id") else None,
        "zone": zone.get("name"),
        "rate": rate.get("name") if rate else None,
        "code": code,
        "message": message,
        "severity": severity,
    }


def validate_config(zones: list[dict[str, Any]], store_currency: str | None = None, tenant_currency: str | None = None) -> list[dict[str, Any]]:
    """zones: [{id?, name, country_codes, rest_of_world, source, active,
    methods: [{id?, name, method_type, rate_cents, conditions, sla_days_min,
    sla_days_max, active, metadata}]}]."""
    issues: list[dict[str, Any]] = []
    if store_currency and tenant_currency and store_currency != tenant_currency:
        issues.append({"zone_id": None, "rate_id": None, "zone": None, "rate": None, "code": "currency_mismatch",
                       "message": f"The store uses {store_currency} but this workspace uses {tenant_currency}; amounts aren't converted.", "severity": "error"})
    # country -> [(zone name, its regions)] of the active local zones seen so far.
    seen: dict[str, list[tuple[str, set[str]]]] = {}
    for zone in zones:
        active = zone.get("active", True)
        if not zone.get("country_codes") and not zone.get("rest_of_world"):
            issues.append(_issue("no_countries", "The zone has no countries.", "error", zone))
        # Overlap is checked for our own (local) zones only: Shopify product
        # profiles legitimately ship the same country with different rates.
        # SPEC-BE-061: zones may share a country when their regions differ. A
        # zone with no regions covers the whole country; regions are compared
        # trimmed and case-insensitively. Regions aren't mapped to countries, so
        # in a multi-country zone any shared region name counts (conservative).
        if active and (zone.get("source") or "local") == "local":
            name = zone.get("name") or ""
            regions = {r.strip().casefold() for r in zone.get("regions") or [] if r.strip()}
            for code in zone.get("country_codes") or []:
                for other, other_regions in seen.get(code, []):
                    if other == name:
                        continue
                    if not regions or not other_regions:
                        issues.append(_issue("overlap", f"{code} is also covered by the active zone “{other}”.", "error", zone))
                        break
                    shared = regions & other_regions
                    if shared:
                        labels = ", ".join(sorted(r.strip() for r in zone.get("regions") or [] if r.strip().casefold() in shared))
                        issues.append(_issue("overlap", f"{code} ({labels}) is also in the active zone “{other}”.", "error", zone))
                        break
                seen.setdefault(code, []).append((name, regions))
        methods = zone.get("methods") or []
        active_methods = [m for m in methods if m.get("active", True)]
        if active and not active_methods:
            issues.append(_issue("no_methods", "The zone has no active shipping method.", "error", zone))
        has_paid = any(m.get("method_type") in PAID_TYPES and (m.get("rate_cents") or 0) > 0 for m in active_methods)
        for m in methods:
            c = m.get("conditions") or {}
            if (m.get("rate_cents") or 0) < 0:
                issues.append(_issue("negative_rate", "The price can't be negative.", "error", zone, m))
            if c.get("min_subtotal_cents") is not None and c.get("max_subtotal_cents") is not None and c["min_subtotal_cents"] >= c["max_subtotal_cents"]:
                issues.append(_issue("bad_subtotal_range", "The minimum order amount must be below the maximum.", "error", zone, m))
            if c.get("min_weight_g") is not None and c.get("max_weight_g") is not None and c["min_weight_g"] >= c["max_weight_g"]:
                issues.append(_issue("bad_weight_range", "The minimum weight must be below the maximum.", "error", zone, m))
            if m.get("sla_days_min") is not None and m.get("sla_days_max") is not None and m["sla_days_min"] > m["sla_days_max"]:
                issues.append(_issue("bad_sla", "Minimum delivery days exceed the maximum.", "error", zone, m))
            meta = m.get("metadata") or {}
            if m.get("method_type") == "free_shipping" and not c.get("min_subtotal_cents"):
                issues.append(_issue("free_no_minimum", "Free shipping applies to every order (no minimum)" + (", alongside paid methods." if has_paid else "."), "warning", zone, m))
            if m.get("method_type") == "carrier_calculated" and (zone.get("source") or "local") == "local":
                issues.append(_issue("carrier_not_connected", "Carrier-calculated rates need a carrier connection at checkout.", "warning", zone, m))
            if meta.get("cost_formula"):
                issues.append(_issue("cost_formula", f"Cost formula “{meta['cost_formula']}” — edit it in WooCommerce.", "warning", zone, m))
            if m.get("method_type") == "local_pickup" and not meta.get("pickup_instructions"):
                issues.append(_issue("pickup_no_instructions", "Add pickup instructions for customers.", "warning", zone, m))
    return issues


def _zone_struct(zone: ShippingZone) -> dict[str, Any]:
    return {
        "id": zone.id,
        "name": zone.name,
        "country_codes": [c.strip() for c in zone.country_codes],
        "regions": list(zone.regions or []),
        "rest_of_world": bool((zone.extra_metadata or {}).get("rest_of_world")),
        "source": zone.source or "local",
        "active": zone.active,
        "methods": [
            {
                "id": r.id, "name": r.name, "method_type": r.method_type, "rate_cents": r.rate_cents,
                "conditions": r.conditions or {}, "sla_days_min": r.sla_days_min, "sla_days_max": r.sla_days_max,
                "active": r.active, "metadata": r.extra_metadata or {},
            }
            for r in zone.rates
            if r.tenant_id == zone.tenant_id
        ],
    }


def _store_validation(zones: list[ShippingZone], issues: list[dict[str, Any]]) -> None:
    for zone in zones:
        own = [i for i in issues if i["zone_id"] == str(zone.id) and not i["rate_id"]]
        zone.extra_metadata = {**(zone.extra_metadata or {}), "validation": {"ok": not any(i["severity"] == "error" for i in own), "issues": own}}
        for rate in zone.rates:
            mine = [i for i in issues if i["rate_id"] == str(rate.id)]
            rate.extra_metadata = {**(rate.extra_metadata or {}), "validation": {"ok": not any(i["severity"] == "error" for i in mine), "issues": mine}}


def validate(db: Session, tenant_id: str) -> dict[str, Any]:
    zones = _zones(db, tenant_id)
    issues = validate_config([_zone_struct(z) for z in zones])
    _store_validation(zones, issues)
    db.commit()
    return {"ok": not any(i["severity"] == "error" for i in issues), "issues": issues}


# ---------------------------------------------------------------------------
# Create / update
# ---------------------------------------------------------------------------
def _activation_errors(db: Session, tenant_id: str, struct: dict[str, Any]) -> list[dict[str, Any]]:
    """Validation errors that block `struct` (a zone + its methods) from being
    active (SPEC-BE-058). The zone is validated LAST so a country overlap is
    attributed to it rather than to the zone that already had the country.
    no_methods is ignored: a zone is set up one method at a time."""
    key = str(struct["id"]) if struct.get("id") else None
    others = [_zone_struct(z) for z in _zones(db, tenant_id) if str(z.id) != key]
    return [
        i for i in validate_config([*others, struct])
        if i["severity"] == "error" and i["zone_id"] == key and i["code"] != "no_methods"
    ]


def _refuse(errors: list[dict[str, Any]]) -> None:
    if errors:
        raise AppError("Fix these first: " + "; ".join(e["message"] for e in errors), 422)


def create_zone(db: Session, tenant_id: str, actor_user_id: str, payload: ShippingZoneCreate) -> dict[str, Any]:
    # A new zone is active, so it must not overlap an active local zone.
    _refuse(_activation_errors(db, tenant_id, {
        "id": None, "name": payload.name, "country_codes": payload.country_codes, "regions": payload.regions, "rest_of_world": False,
        "source": "local", "active": True, "methods": [],
    }))
    zone = ShippingZone(
        tenant_id=tenant_id,
        name=payload.name,
        country_codes=payload.country_codes,
        regions=payload.regions,
        active=True,
        source="local",
        extra_metadata={},
    )
    db.add(zone)
    db.flush()
    # write_audit_log commits: the zone and its audit row land in one commit.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="shipping_zone.create",
        resource_type="shipping_zone",
        resource_id=zone.id,
        metadata={"name": zone.name, "country_codes": payload.country_codes, "regions": payload.regions, "source": "local"},
    )
    db.refresh(zone)
    logger.info("shipping_zone_created", tenant_id=tenant_id, zone_id=str(zone.id))
    return _zone_dict(zone)


def _zone_row(db: Session, tenant_id: str, zone_id: str) -> ShippingZone:
    zone = (
        db.query(ShippingZone)
        .options(selectinload(ShippingZone.rates))
        .filter(ShippingZone.tenant_id == tenant_id, ShippingZone.id == zone_id)
        .first()
    )
    if zone is None:
        # Same 404 for a missing zone and another tenant's zone.
        raise NotFoundError("Shipping zone not found.")
    return zone


def _rate_metadata(payload: ShippingRateCreate) -> dict[str, Any]:
    return {k: v for k, v in {"pickup_instructions": payload.pickup_instructions, "pickup_location": payload.pickup_location}.items() if v}


def create_rate(db: Session, tenant_id: str, actor_user_id: str, zone_id: str, payload: ShippingRateCreate) -> dict[str, Any]:
    zone = _zone_row(db, tenant_id, zone_id)
    if zone.source in STORE_SOURCES:
        raise ConflictError(f"This zone is managed by {STORE_LABEL[zone.source]}; add the method there, then sync.")
    # The new method is active at once, so it is validated like an activation.
    struct = _zone_struct(zone)
    struct["methods"].append({
        "id": None, "name": payload.name, "method_type": payload.method_type, "rate_cents": _cents(payload.rate),
        "conditions": _conditions_cents(payload.conditions), "sla_days_min": payload.sla_days_min,
        "sla_days_max": payload.sla_days_max, "active": True, "metadata": _rate_metadata(payload),
    })
    _refuse(_activation_errors(db, tenant_id, struct))
    rate = ShippingPolicy(
        tenant_id=tenant_id,
        zone_id=zone.id,
        name=payload.name,
        carrier=payload.carrier,
        rate_cents=_cents(payload.rate),
        free_over_cents=_cents(payload.free_over),
        cutoff_time=payload.cutoff_time,
        sla_days_min=payload.sla_days_min,
        sla_days_max=payload.sla_days_max,
        active=True,
        source="local",
        method_type=payload.method_type,
        conditions=_conditions_cents(payload.conditions),
        extra_metadata=_rate_metadata(payload),
    )
    db.add(rate)
    db.flush()
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="shipping_rate.create",
        resource_type="shipping_rate",
        resource_id=rate.id,
        metadata={
            "zone_id": str(zone.id),
            "name": rate.name,
            "carrier": rate.carrier,
            "method_type": rate.method_type,
            "rate_cents": rate.rate_cents,
            "free_over_cents": rate.free_over_cents,
        },
    )
    db.refresh(rate)
    logger.info("shipping_rate_created", tenant_id=tenant_id, rate_id=str(rate.id))
    return _rate_dict(rate)


def _push_rate(db: Session, tenant_id: str, rate: ShippingPolicy, changes: dict[str, Any]) -> None:
    """Store-first write for an imported rate (decision 2). Raises 409 when the
    API can't write it, 502 when the store refuses."""
    from app.integrations import shopify, woocommerce
    from app.services import integration_service

    label = STORE_LABEL[rate.source]
    if _read_only(rate):
        raise ConflictError(f"Managed by {label}: this method can't be changed through the API. Edit it in {label}.")
    store = integration_service.store_connection(db, tenant_id)
    if store is None or store["provider"] != rate.source:
        raise ConflictError(f"Managed by {label}, which isn't connected. Reconnect it in Integrations.")
    try:
        if rate.source == "shopify":
            shopify.update_method(store["fields"], rate.zone.external_id or "", rate.external_id or "", changes, _currency(db, tenant_id))
        else:
            woocommerce.update_method(store["fields"], rate.external_id or "", changes, rate.method_type)
    except (shopify.ShopifyError, woocommerce.WooError) as exc:
        raise AppError(exc.message, 502) from None


def update_rate(db: Session, tenant_id: str, actor_user_id: str, rate_id: str, payload: ShippingRateUpdate) -> dict[str, Any]:
    rate = (
        db.query(ShippingPolicy)
        .filter(ShippingPolicy.tenant_id == tenant_id, ShippingPolicy.id == rate_id)
        .with_for_update()
        .first()
    )
    if rate is None:
        raise NotFoundError("Shipping rate not found.")
    sent = payload.model_fields_set
    changes: dict[str, Any] = {}
    if "name" in sent and payload.name:
        changes["name"] = payload.name
    if "active" in sent and payload.active is not None:
        changes["active"] = payload.active
    if "rate" in sent and payload.rate is not None:
        changes["rate_cents"] = _cents(payload.rate)
    if "free_over" in sent:
        changes["free_over_cents"] = _cents(payload.free_over)
    if "conditions" in sent:
        changes["conditions"] = _conditions_cents(payload.conditions)
    for key in ("sla_days_min", "sla_days_max"):
        if key in sent:
            changes[key] = getattr(payload, key)
    if not changes:
        raise AppError("Nothing to change.", 422)

    # Activation is refused while the zone has a validation error (SPEC-BE-058).
    if changes.get("active") is True:
        zone = _zone_row(db, tenant_id, str(rate.zone_id))
        struct = _zone_struct(zone)
        for m in struct["methods"]:
            if m["id"] == rate.id:
                m.update(active=True, **{k: v for k, v in changes.items() if k in ("rate_cents", "conditions", "sla_days_min", "sla_days_max")})
        _refuse(_activation_errors(db, tenant_id, struct))

    pushed = False
    if rate.source in STORE_SOURCES:
        store_changes = {k: v for k, v in changes.items() if k in ("name", "active", "rate_cents", "conditions")}
        if store_changes:
            _push_rate(db, tenant_id, rate, store_changes)
            pushed = True
    before = {"name": rate.name, "active": rate.active, "rate_cents": rate.rate_cents, "free_over_cents": rate.free_over_cents}
    for key, value in changes.items():
        setattr(rate, key, value)
    if pushed:
        write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.pushed_to_store",
                        resource_type="shipping_rate", resource_id=rate.id, metadata={"source": rate.source, "fields": sorted(changes)})
    action = "shipping_rate.update"
    if set(changes) == {"active"}:
        action = "shipping_rate.enable" if changes["active"] else "shipping_rate.disable"
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type="shipping_rate",
        resource_id=rate.id,
        metadata={"name": rate.name, "source": rate.source, "before": before, "changed": sorted(changes)},
    )
    db.refresh(rate)
    logger.info("shipping_rate_updated", tenant_id=tenant_id, rate_id=str(rate.id), fields=sorted(changes))
    return _rate_dict(rate)


def set_rate_active(db: Session, tenant_id: str, actor_user_id: str, rate_id: str, active: bool) -> dict[str, Any]:
    return update_rate(db, tenant_id, actor_user_id, rate_id, ShippingRateUpdate(active=active))


def set_free_shipping_threshold(db: Session, tenant_id: str, actor_user_id: str, zone_id: str, threshold: Decimal) -> dict[str, Any]:
    """Free shipping over `threshold` in a zone. Local zones: free_over on every
    paid rate. Store zones: the store's free method's minimum order (pushed
    first); with no free method there -> 409."""
    zone = _zone_row(db, tenant_id, zone_id)
    cents = _cents(threshold)
    updated = 0
    if zone.source in STORE_SOURCES:
        free = [r for r in zone.rates if r.method_type == "free_shipping"]
        if not free:
            raise ConflictError(f"Add a free-shipping method to this zone in {STORE_LABEL[zone.source]} first, then sync.")
        for rate in free:
            update_rate(db, tenant_id, actor_user_id, str(rate.id), ShippingRateUpdate(conditions=RateConditions(min_subtotal=threshold)))
            updated += 1
        db.refresh(zone)
    for rate in zone.rates:
        if rate.method_type in PAID_TYPES:
            rate.free_over_cents = cents
            updated += 0 if zone.source in STORE_SOURCES else 1
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="shipping_zone.free_threshold",
        resource_type="shipping_zone",
        resource_id=zone.id,
        metadata={"threshold_cents": cents, "source": zone.source, "updated": updated},
    )
    return {"zone_id": str(zone.id), "updated": updated, "threshold": float(threshold)}


# ---------------------------------------------------------------------------
# Store detect / sync / status
# ---------------------------------------------------------------------------
def _read_store(store: dict[str, Any]) -> dict[str, Any]:
    from app.integrations import shopify, woocommerce

    try:
        if store["provider"] == "shopify":
            return shopify.read_shipping(store["fields"])
        return woocommerce.read_shipping(store["fields"])
    except (shopify.ShopifyError, woocommerce.WooError) as exc:
        raise AppError(exc.message, 502) from None


def _is_usable(config: dict[str, Any]) -> bool:
    # "Detected" = at least one zone with at least one active method.
    return any(any(m["active"] for m in z["methods"]) for z in config["zones"])


def _record_sync(db: Session, store: dict[str, Any], **values: Any) -> None:
    from app.services import integration_service

    record = integration_service.store_record(db, str(store.get("tenant_id")), store["integration_id"]) if store.get("tenant_id") else None
    if record is None:
        return
    now = datetime.now(timezone.utc)
    meta = dict(record.extra_metadata or {})
    sync = dict(meta.get("shipping_sync") or {})
    errors = list(sync.get("errors") or [])
    if values.get("error"):
        errors = ([{"message": values["error"], "at": now.isoformat()}] + errors)[:20]
        record.last_error = str(values["error"])[:300]
    sync.update({k: v for k, v in values.items() if k != "error"}, errors=errors)
    if values.get("status") in ("ok", "partial"):
        record.last_sync_at = now
        sync["last_success_at"] = now.isoformat()
        record.last_error = None
    sync["last_sync_at"] = now.isoformat()
    meta["shipping_sync"] = sync
    record.extra_metadata = meta


def _preview(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "zones": [
            {
                "name": z["name"],
                "country_codes": z["country_codes"],
                "regions": z["regions"],
                "rest_of_world": z["rest_of_world"],
                "methods": [
                    {"name": m["name"], "method_type": m["method_type"], "rate": _major(m["rate_cents"]), "conditions": _conditions_major(m["conditions"]), "active": m["active"]}
                    for m in z["methods"]
                ],
            }
            for z in config["zones"]
        ]
    }


def _store(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.services import integration_service

    store = integration_service.store_connection(db, tenant_id)
    if store is None:
        raise ConflictError("Connect Shopify or WooCommerce in Integrations first.")
    return {**store, "tenant_id": tenant_id}


def detect(db: Session, tenant_id: str, actor_user_id: str) -> dict[str, Any]:
    """Reads the store's shipping without writing any zone (preview)."""
    store = _store(db, tenant_id)
    try:
        config = _read_store(store)
    except AppError as exc:
        _record_sync(db, store, status="failed", error=exc.detail)
        write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.sync_failed",
                        resource_type="integration", resource_id=store["integration_id"], metadata={"source": store["provider"], "step": "detect"})
        raise
    tenant_currency = _currency(db, tenant_id)
    detected = _is_usable(config)
    warnings = [i["message"] for i in validate_config(_import_struct(config), config.get("currency") or None, tenant_currency) if i["severity"] == "error"]
    _record_sync(db, store, detected=detected, unsupported=config["unsupported"])
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.detected",
                    resource_type="integration", resource_id=store["integration_id"],
                    metadata={"source": store["provider"], "detected": detected, "zones": len(config["zones"])})
    return {
        "detected": detected,
        "provider": store["provider"],
        "currency": config.get("currency") or None,
        "preview": _preview(config),
        "unsupported": config["unsupported"],
        "warnings": warnings,
    }


def _import_struct(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": z["name"], "country_codes": z["country_codes"], "rest_of_world": z["rest_of_world"], "source": "store", "active": True,
         "methods": [{**m, "sla_days_min": None, "sla_days_max": None} for m in z["methods"]]}
        for z in config["zones"]
    ]


def sync(db: Session, tenant_id: str, actor_user_id: str | None) -> dict[str, Any]:
    """Imports/refreshes the store's shipping (upsert by source + external_id)."""
    store = _store(db, tenant_id)
    source = store["provider"]
    try:
        config = _read_store(store)
    except AppError as exc:
        _record_sync(db, store, status="failed", error=exc.detail)
        write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.sync_failed",
                        resource_type="integration", resource_id=store["integration_id"], metadata={"source": source})
        raise
    tenant_currency = _currency(db, tenant_id)
    if config.get("currency") and config["currency"] != tenant_currency:
        message = f"The store uses {config['currency']} but this workspace uses {tenant_currency}; shipping wasn't imported."
        _record_sync(db, store, status="failed", error=message)
        write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.sync_failed",
                        resource_type="integration", resource_id=store["integration_id"], metadata={"source": source, "reason": "currency"})
        raise AppError(message, 422)

    existing = {z.external_id: z for z in _zones(db, tenant_id) if z.source == source and z.external_id}
    created = updated = deactivated = 0
    seen_zones: set[str] = set()
    for z in config["zones"]:
        seen_zones.add(z["external_id"])
        zone = existing.get(z["external_id"])
        meta = {"rest_of_world": z["rest_of_world"], "profile": z.get("profile")}
        if zone is None:
            # A store zone with no methods (e.g. WooCommerce "Locations not
            # covered") is imported inactive: it ships nothing.
            zone = ShippingZone(tenant_id=tenant_id, source=source, external_id=z["external_id"], name=z["name"][:255],
                                country_codes=z["country_codes"], regions=z["regions"], active=bool(z["methods"]), extra_metadata=meta)
            db.add(zone)
            db.flush()
            db.refresh(zone)
            created += 1
        else:
            zone.name, zone.country_codes, zone.regions, zone.active = z["name"][:255], z["country_codes"], z["regions"], bool(z["methods"])
            zone.extra_metadata = {**(zone.extra_metadata or {}), **meta}
            updated += 1
        rates = {r.external_id: r for r in zone.rates if r.external_id}
        free_min = min((m["conditions"].get("min_subtotal_cents") for m in z["methods"] if m["method_type"] == "free_shipping" and m["conditions"].get("min_subtotal_cents")), default=None)
        seen_rates: set[str] = set()
        for m in z["methods"]:
            seen_rates.add(m["external_id"])
            values = {
                "name": m["name"][:255], "carrier": (m.get("carrier") or STORE_LABEL[source])[:255], "rate_cents": m["rate_cents"],
                "method_type": m["method_type"], "conditions": m["conditions"], "active": m["active"],
                # The store's free-over threshold is also shown on its paid rates (existing UI).
                "free_over_cents": free_min if m["method_type"] in PAID_TYPES else None,
            }
            rate = rates.get(m["external_id"])
            if rate is None:
                db.add(ShippingPolicy(tenant_id=tenant_id, zone_id=zone.id, source=source, external_id=m["external_id"], extra_metadata=m.get("metadata") or {}, **values))
                created += 1
            else:
                for key, value in values.items():
                    setattr(rate, key, value)
                rate.extra_metadata = {**{k: v for k, v in (rate.extra_metadata or {}).items() if k == "validation"}, **(m.get("metadata") or {})}
                updated += 1
        for ext, rate in rates.items():
            if ext not in seen_rates and rate.active:
                rate.active = False
                deactivated += 1
    for ext, zone in existing.items():
        if ext not in seen_zones and zone.active:
            zone.active = False
            for rate in zone.rates:
                rate.active = False
            deactivated += 1
    db.flush()
    zones = _zones(db, tenant_id)
    issues = validate_config([_zone_struct(z) for z in zones])
    _store_validation(zones, issues)
    status = "partial" if any(i["severity"] == "error" for i in issues) else "ok"
    counts = {"zones": sum(1 for z in zones if z.source == source and z.active), "methods": sum(1 for z in zones if z.source == source for r in z.rates if r.active)}
    _record_sync(db, store, status=status, detected=_is_usable(config), counts=counts, unsupported=config["unsupported"])
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.synced",
                    resource_type="integration", resource_id=store["integration_id"],
                    metadata={"source": source, "created": created, "updated": updated, "deactivated": deactivated, "status": status})
    logger.info("shipping_synced", tenant_id=tenant_id, source=source, created=created, updated=updated, deactivated=deactivated)
    return {"created": created, "updated": updated, "deactivated": deactivated,
            "errors": [i["message"] for i in issues if i["severity"] == "error"], "last_sync_at": datetime.now(timezone.utc).isoformat()}


def auto_detect_and_sync(db: Session, tenant_id: str, actor_user_id: str | None) -> None:
    """After a store connects (steps 1-3A): detect, and import when usable.
    Errors are already recorded on the integration's shipping_sync status."""
    try:
        if detect(db, tenant_id, actor_user_id or "")["detected"]:
            sync(db, tenant_id, actor_user_id)
    except AppError as exc:
        logger.warning("shipping_auto_detect_failed", tenant_id=tenant_id, error=exc.detail)


def sync_all_stores() -> int:
    """Scheduler job (every 6 hours): re-sync every tenant whose store was synced before."""
    from app.db.session import SessionLocal
    from app.models.integration import Integration

    done = 0
    db = SessionLocal()
    try:
        rows = (
            db.query(Integration.tenant_id)
            .filter(Integration.provider.in_(STORE_SOURCES), Integration.status == "connected")
            .distinct()
            .all()
        )
        for (tenant_id,) in rows:
            synced_before = db.query(ShippingZone.id).filter(ShippingZone.tenant_id == tenant_id, ShippingZone.source.in_(STORE_SOURCES)).first()
            if not synced_before:
                continue
            try:
                sync(db, str(tenant_id), None)
                done += 1
            except AppError as exc:
                db.rollback()
                logger.warning("shipping_scheduled_sync_failed", tenant_id=str(tenant_id), error=exc.detail)
    finally:
        db.close()
    return done


def get_status(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.services import integration_service

    store = integration_service.store_connection(db, tenant_id)
    zones = _zones(db, tenant_id)
    sync_state: dict[str, Any] = {}
    if store:
        record = integration_service.store_record(db, tenant_id, store["integration_id"])
        sync_state = ((record.extra_metadata or {}) if record else {}).get("shipping_sync") or {}
    store_zones = [z for z in zones if z.source in STORE_SOURCES and z.active]
    local_zones = [z for z in zones if (z.source or "local") == "local"]
    mode = "synced" if store_zones else ("local" if local_zones else "setup_required")
    active = [z for z in zones if z.active]
    return {
        "store": {"provider": store["provider"], "connected": True, "account_name": store["account_name"]} if store else None,
        "detected": sync_state.get("detected"),
        "mode": mode,
        "last_sync_at": sync_state.get("last_sync_at"),
        "last_sync_status": sync_state.get("status"),
        "errors": sync_state.get("errors") or [],
        "counts": {"zones": len(active), "methods": sum(1 for z in active for r in z.rates if r.active)},
        "unsupported": sync_state.get("unsupported") or [],
    }


# ---------------------------------------------------------------------------
# Guided setup (3B)
# ---------------------------------------------------------------------------
def _setup_zones(payload: ShippingSetup) -> list[dict[str, Any]]:
    zones_in: list[dict[str, Any]] = []
    for zin in payload.zones:
        zones_in.append(
            {
                "name": zin.name, "country_codes": zin.country_codes, "regions": zin.regions, "rest_of_world": False, "source": "local", "active": True,
                "methods": [
                    {"name": m.name, "carrier": m.carrier, "method_type": m.method_type, "rate_cents": _cents(m.rate) or 0,
                     "free_over_cents": _cents(m.free_over), "conditions": _conditions_cents(m.conditions),
                     "sla_days_min": m.sla_days_min, "sla_days_max": m.sla_days_max, "cutoff_time": m.cutoff_time,
                     "active": True, "metadata": _rate_metadata(m)}
                    for m in zin.methods
                ],
            }
        )
    return zones_in


def _setup_issues(db: Session, tenant_id: str, zones_in: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = [_zone_struct(z) for z in _zones(db, tenant_id) if z.active and (z.source or "local") == "local"]
    # Existing zones first, so an overlap is attributed to the new zone. Only
    # issues of the new zones (zone_id None, incl. overlaps and the tenant-wide
    # currency check) are returned: an existing zone's own problem, e.g. one
    # added without methods, must not block the wizard (SPEC-BE-061).
    return [i for i in validate_config(existing + zones_in) if i["zone_id"] is None]


def validate_setup(db: Session, tenant_id: str, payload: ShippingSetup) -> dict[str, Any]:
    """Guided setup step 3 (Review): validates the draft without writing."""
    issues = _setup_issues(db, tenant_id, _setup_zones(payload))
    return {"ok": not any(i["severity"] == "error" for i in issues), "issues": issues}


def setup(db: Session, tenant_id: str, actor_user_id: str, payload: ShippingSetup) -> dict[str, Any]:
    from app.integrations import shopify, woocommerce
    from app.services import integration_service

    zones_in = _setup_zones(payload)
    issues = _setup_issues(db, tenant_id, zones_in)
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        raise AppError("Fix these first: " + "; ".join(f"{e['zone'] or ''}{' / ' + e['rate'] if e['rate'] else ''}: {e['message']}" for e in errors), 422)

    store = integration_service.store_connection(db, tenant_id) if payload.push_to_store else None
    if payload.push_to_store and store is None:
        raise ConflictError("Connect Shopify or WooCommerce to also create this in your store.")
    if store is not None:
        # Store first; on a store error nothing is written here (502).
        try:
            if store["provider"] == "shopify":
                shopify.create_zones(store["fields"], zones_in, _currency(db, tenant_id))
            else:
                woocommerce.create_zones(store["fields"], zones_in)
        except (shopify.ShopifyError, woocommerce.WooError) as exc:
            raise AppError(exc.message, 502) from None
        write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.pushed_to_store",
                        resource_type="integration", resource_id=store["integration_id"], metadata={"source": store["provider"], "zones": len(zones_in)})
        result = sync(db, tenant_id, actor_user_id)
        write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.setup_completed",
                        resource_type="shipping", resource_id=None, metadata={"zones": len(zones_in), "pushed": True})
        return {"pushed": True, **result, "zones": list_zones(db, tenant_id)["zones"]}

    created = []
    for z in zones_in:
        zone = ShippingZone(tenant_id=tenant_id, name=z["name"], country_codes=z["country_codes"], regions=z["regions"], active=True, source="local", extra_metadata={})
        db.add(zone)
        db.flush()
        for m in z["methods"]:
            db.add(ShippingPolicy(
                tenant_id=tenant_id, zone_id=zone.id, name=m["name"], carrier=m["carrier"], rate_cents=m["rate_cents"],
                free_over_cents=m["free_over_cents"], cutoff_time=m["cutoff_time"], sla_days_min=m["sla_days_min"],
                sla_days_max=m["sla_days_max"], active=True, source="local", method_type=m["method_type"],
                conditions=m["conditions"], extra_metadata=m["metadata"],
            ))
        created.append(zone)
    db.flush()
    zones = _zones(db, tenant_id)
    _store_validation(zones, validate_config([_zone_struct(z) for z in zones]))
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="shipping.setup_completed",
                    resource_type="shipping", resource_id=None,
                    metadata={"zones": len(created), "methods": sum(len(z["methods"]) for z in zones_in), "pushed": False})
    return {"pushed": False, "created": len(created), "updated": 0, "deactivated": 0, "errors": [], "last_sync_at": None,
            "zones": list_zones(db, tenant_id)["zones"]}
