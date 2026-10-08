"""Live trigger catalog (SPEC-BE-060).

Each wired trigger lists the context fields its runs provide; Command Chat
uses this to check that a condition only names fields the trigger supplies.
Triggers not listed here keep the SPEC-BE-034 dry run only ("manual test
only" in the catalog).
"""
from typing import Any

TRIGGER_CONTEXT_FIELDS: dict[str, tuple[str, ...]] = {
    # Fired by inventory_service.adjust_on_hand when `available` crosses from
    # above the threshold to at/below it.
    "inventory_low": (
        "product.id", "product.sku", "product.title", "product.units_sold_30d",
        "product.revenue_30d_cents", "inventory.available", "inventory.committed",
        "inventory.location",
    ),
    # Fired by order creation paths (none exists in this backend yet besides
    # store syncs); the context shape is fixed here.
    "order_placed": ("order.total", "order.channel", "order.status", "order.items_count", "customer.tags"),
    # Fired by the Meta insights import (SPEC-BE-056) per campaign.
    "ad_threshold_crossed": (
        "campaign.id", "campaign.name", "campaign.roas", "campaign.ctr", "campaign.cpc",
        "campaign.daily_spend",
    ),
    "schedule_cron": ("now",),
    "manual_owner_command": ("input",),
}


def field_allowed(trigger_type: str, field: str) -> bool:
    fields = TRIGGER_CONTEXT_FIELDS.get(trigger_type)
    if fields is None:
        return False
    if trigger_type == "manual_owner_command":
        return field == "input" or field.startswith("input.")
    return field in fields


def is_live(trigger_type: str) -> bool:
    return trigger_type in TRIGGER_CONTEXT_FIELDS


def describe(trigger_type: str, config: dict[str, Any]) -> str:
    if trigger_type == "inventory_low":
        return f"inventory is low (≤ {config.get('threshold')})"
    if trigger_type == "order_placed":
        return "an order is placed" + (f" of at least {config.get('min_total')}" if config.get("min_total") else "")
    if trigger_type == "ad_threshold_crossed":
        return f"{config.get('metric')} goes {config.get('operator')} {config.get('value')}"
    if trigger_type == "schedule_cron":
        return f"on schedule “{config.get('cron')}”"
    if trigger_type == "manual_owner_command":
        return "run manually"
    return trigger_type.replace("_", " ")
