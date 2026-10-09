"""Command Chat action registry, planning and executors (SPEC-BE-059).

One registry of *command actions* covers every module (E-Commerce, Shipping,
Marketing, Meta campaigns, Workflows, General). Each entry declares its strict
parameter model, module, risk class, minimum role and an executor. Executors
only call existing service functions - never the DB or an external API
directly - so every service's own validation, tenant scoping and audit rows
apply unchanged.

Plans are stored in orchestrator_plans.actions (jsonb), so action types are not
limited by the workflow_action_type enum. The 10 SPEC-BE-032 types remain as
aliases where an executor exists (adjust_pricing, update_product, launch_ad,
generate_content, notify_owner, create_task, call_webhook; since SPEC-BE-078
schedule_post -> schedule_organic_posts); the others (send_message,
adjust_budget) have no adapter yet and are registered as unavailable, so a
plan never pretends to run them.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal, Type

import structlog
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import Role, role_at_least

logger = structlog.get_logger(__name__)

Risk = Literal["read", "draft", "change", "spend"]
_STRICT = ConfigDict(extra="forbid")
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Sku = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2}$")]
# An id, or a reference to an earlier action's output: "$<n>.<field>" (1-based).
REF_RE = re.compile(r"^\$(\d+)\.([a-z_]+)$")
IdRef = Annotated[str, StringConstraints(pattern=r"^(\$\d+\.[a-z_]+|[0-9a-fA-F-]{36})$")]
Channel = Literal["facebook", "instagram", "tiktok", "whatsapp", "messenger", "email", "sms", "web"]


def _cents(amount: float | Decimal) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Parameter models (the required-field contract of each action)
# ---------------------------------------------------------------------------
class NoParams(BaseModel):
    model_config = _STRICT


class InspectProductsParams(BaseModel):
    model_config = _STRICT
    query: Annotated[str, StringConstraints(max_length=100)] | None = None
    low_stock_only: bool = False
    limit: Annotated[int, Field(ge=1, le=50)] = 20


class InspectOrdersParams(BaseModel):
    model_config = _STRICT
    status: Literal["pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"] | None = None
    query: Annotated[str, StringConstraints(max_length=100)] | None = None
    limit: Annotated[int, Field(ge=1, le=50)] = 10


class InspectInventoryParams(BaseModel):
    model_config = _STRICT
    low_stock_only: bool = True
    skus: Annotated[list[Sku], Field(max_length=50)] = []


class AdjustInventoryParams(BaseModel):
    model_config = _STRICT
    sku: Sku
    new_on_hand: Annotated[int, Field(ge=0, le=10_000_000)]
    reason: Annotated[str, StringConstraints(max_length=255)] | None = None


class PricingRuleParams(BaseModel):
    model_config = _STRICT
    name: Text
    rule_type: Literal["percent_discount", "fixed_discount", "fixed_price"]
    value: Annotated[float, Field(gt=0)]
    skus: Annotated[list[Sku], Field(max_length=200)] = []
    all_products: bool = False
    start_date: dt.date | None = None
    end_date: dt.date | None = None

    @model_validator(mode="after")
    def _target(self) -> PricingRuleParams:
        if not self.skus and not self.all_products:
            raise ValueError("skus or all_products is required")
        if self.rule_type == "percent_discount" and self.value > 100:
            raise ValueError("a percentage discount cannot exceed 100")
        return self


class UpdateProductParams(BaseModel):
    model_config = _STRICT
    skus: Annotated[list[Sku], Field(min_length=1, max_length=50)]
    status: Literal["draft", "active", "archived", "out_of_stock"] | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None

    @model_validator(mode="after")
    def _change(self) -> UpdateProductParams:
        if self.status is None and self.title is None:
            raise ValueError("status or title is required")
        return self


class ShippingZoneParams(BaseModel):
    model_config = _STRICT
    name: Text
    country_codes: Annotated[list[Country], Field(min_length=1, max_length=50)]
    regions: Annotated[list[Text], Field(max_length=100)] = []


class ShippingRateParams(BaseModel):
    model_config = _STRICT
    zone_id: IdRef
    name: Text
    carrier: Text = "Own delivery"
    method_type: Literal["flat_rate", "free_shipping", "local_pickup", "local_delivery"] = "flat_rate"
    rate: Annotated[float, Field(ge=0)]
    free_over: Annotated[float, Field(gt=0)] | None = None
    sla_days_min: Annotated[int, Field(ge=0, le=365)] | None = None
    sla_days_max: Annotated[int, Field(ge=0, le=365)] | None = None


class UpdateShippingRateParams(BaseModel):
    model_config = _STRICT
    rate_id: IdRef
    name: Text | None = None
    rate: Annotated[float, Field(ge=0)] | None = None
    free_over: Annotated[float, Field(gt=0)] | None = None
    active: bool | None = None
    sla_days_min: Annotated[int, Field(ge=0, le=365)] | None = None
    sla_days_max: Annotated[int, Field(ge=0, le=365)] | None = None


class FreeShippingThresholdParams(BaseModel):
    model_config = _STRICT
    zone_id: IdRef
    threshold: Annotated[float, Field(gt=0)]


class RateToggleParams(BaseModel):
    model_config = _STRICT
    rate_id: IdRef


class GenerateContentParams(BaseModel):
    model_config = _STRICT
    objective: Literal["awareness", "traffic", "engagement", "conversions", "reach"]
    channel: Channel
    brief: LongText
    skus: Annotated[list[Sku], Field(max_length=10)] = []
    campaign_id: IdRef | None = None


class CampaignRefParams(BaseModel):
    model_config = _STRICT
    campaign_id: IdRef


class CampaignResultsParams(BaseModel):
    model_config = _STRICT
    campaign_id: IdRef | None = None
    range: Literal["7d", "30d", "90d", "lifetime"] = "7d"


MetaObjective = Literal["awareness", "traffic", "engagement", "leads", "app_promotion", "sales"]


class MetaCampaignDraftParams(BaseModel):
    """A whole SPEC-BE-055 tree (campaign, one ad set, one ad) from one command."""

    model_config = _STRICT
    name: Text
    objective: MetaObjective
    skus: Annotated[list[Sku], Field(max_length=20)] = []
    budget_type: Literal["daily", "lifetime"] = "daily"
    budget: Annotated[float, Field(gt=0)]
    duration_days: Annotated[int, Field(ge=1, le=365)]
    start_date: dt.date | None = None
    countries: Annotated[list[Country], Field(min_length=1, max_length=25)]
    age_min: Annotated[int, Field(ge=18, le=65)] = 18
    age_max: Annotated[int, Field(ge=18, le=65)] = 65
    genders: Literal["all", "male", "female"] = "all"
    platforms: Annotated[list[Literal["facebook", "instagram", "messenger"]], Field(max_length=3)] = []
    destination_url: Annotated[str, StringConstraints(pattern=r"^https://\S+$", max_length=2048)]
    primary_text: Annotated[str, StringConstraints(max_length=2000)] | None = None
    headline: Annotated[str, StringConstraints(max_length=255)] | None = None
    call_to_action: Literal["SHOP_NOW", "LEARN_MORE", "SIGN_UP", "ORDER_NOW", "CONTACT_US", "BOOK_NOW", "GET_OFFER"] = "SHOP_NOW"


class AICampaignParams(BaseModel):
    """SPEC-BE-069: start an AI Ad Autopilot run. It only builds drafts and
    always stops for review; publishing is never part of this action."""

    model_config = _STRICT
    prompt: LongText
    platforms: Annotated[list[Literal["meta", "tiktok", "google", "youtube", "linkedin", "x", "snapchat", "pinterest"]], Field(min_length=1, max_length=3)]
    budget: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    budget_mode: Literal["daily", "total"] = "total"
    landing_url: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^https://", max_length=2048)]
    goal: Literal["sales", "traffic", "leads", "awareness", "app"] | None = None
    skus: Annotated[list[Sku], Field(max_length=10)] = []
    visuals: Literal["generate", "products", "builder"] = "generate"


class PublishMetaParams(BaseModel):
    model_config = _STRICT
    campaign_id: IdRef
    mode: Literal["active", "paused"] = "active"


class ZernioCampaignParams(BaseModel):
    """SPEC-BE-090: one Facebook/Instagram campaign → ad set → ad created on
    Zernio (SPEC-BE-084), whose approved Meta app publishes it. The goals are
    the Zernio Meta goals that need no extra ids (lead forms, app installs and
    Page goals stay in the Zernio form)."""

    model_config = _STRICT
    platform: Literal["facebook", "instagram"] = "facebook"
    ad_account_id: Annotated[str, StringConstraints(pattern=r"^act_\w{1,40}$")]
    name: Text
    goal: Literal["awareness", "traffic", "engagement", "video_views", "conversions"]
    budget: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    budget_type: Literal["daily", "lifetime"] = "daily"
    duration_days: Annotated[int, Field(ge=1, le=365)]
    start_date: dt.date | None = None
    countries: Annotated[list[Country], Field(min_length=1, max_length=25)]
    age_min: Annotated[int, Field(ge=18, le=65)] = 18
    age_max: Annotated[int, Field(ge=18, le=65)] = 65
    genders: Literal["all", "male", "female"] = "all"
    destination_url: Annotated[str, StringConstraints(pattern=r"^https://\S+$", max_length=2000)]
    primary_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    headline: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    call_to_action: Annotated[str, StringConstraints(pattern=r"^[A-Z_]{2,40}$")] = "LEARN_MORE"
    media_id: IdRef
    mode: Literal["active", "paused"] = "paused"


class MetaStatusParams(BaseModel):
    model_config = _STRICT
    level: Literal["campaign", "ad_set", "ad"] = "campaign"
    object_id: IdRef


class MetaBudgetParams(BaseModel):
    model_config = _STRICT
    campaign_id: IdRef
    budget: Annotated[float, Field(gt=0)]
    budget_type: Literal["daily", "lifetime"] = "daily"


class WorkflowActionParam(BaseModel):
    model_config = _STRICT
    type: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    params: dict[str, Any] = {}


class WorkflowDraftParams(BaseModel):
    model_config = _STRICT
    name: Text
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    trigger_type: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    trigger_config: dict[str, Any] = {}
    condition_dsl: Annotated[str, StringConstraints(max_length=2000)] | None = None
    actions: Annotated[list[WorkflowActionParam], Field(min_length=1, max_length=10)]


class UpdateWorkflowParams(WorkflowDraftParams):
    workflow_id: IdRef


class WorkflowRefParams(BaseModel):
    model_config = _STRICT
    workflow_id: IdRef | None = None


class WorkflowIdParams(BaseModel):
    model_config = _STRICT
    workflow_id: IdRef


class RunWorkflowParams(BaseModel):
    model_config = _STRICT
    workflow_id: IdRef
    input: dict[str, Any] = {}


class NotifyOwnerParams(BaseModel):
    model_config = _STRICT
    message: Text


class CreateTaskParams(BaseModel):
    model_config = _STRICT
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    details: Annotated[str, StringConstraints(max_length=1000)] | None = None
    assignee_role: Literal["owner", "manager", "operator"] = "manager"


class CallWebhookParams(BaseModel):
    model_config = _STRICT
    url: Annotated[str, StringConstraints(pattern=r"^https://\S+$", max_length=500)]
    event: Text


# --- Organic Marketing (SPEC-BE-078) ------------------------------------------
OrganicPlatform = Literal["facebook", "instagram", "tiktok", "linkedin"]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$", max_length=2000)]
LocalTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Ratio = Literal["1:1", "4:5", "9:16", "16:9", "1.91:1", "2:3", "3:2"]


class InspectOrganicParams(BaseModel):
    model_config = _STRICT
    status: Literal["scheduled", "published", "failed", "cancelled"] | None = None
    platform: OrganicPlatform | None = None
    days: Annotated[int, Field(ge=1, le=90)] = 14


class OrganicAnalyticsParams(BaseModel):
    model_config = _STRICT
    range: Literal["7d", "30d", "90d"] = "30d"


class OrganicInsightsParams(BaseModel):
    model_config = _STRICT
    days: Literal[30, 60, 90] = 60


class CreateOrganicPostsParams(BaseModel):
    model_config = _STRICT
    count: Annotated[int, Field(ge=1, le=30)]
    brief: LongText
    platforms: Annotated[list[OrganicPlatform], Field(min_length=1, max_length=4)]
    product_skus: Annotated[list[Sku], Field(max_length=10)] = []
    media: Literal["none", "product_photos", "generate_photo", "generate_video"] = "none"
    tone: Text | None = None
    link_url: HttpsUrl | None = None


class GeneratePhotoParams(BaseModel):
    model_config = _STRICT
    prompt: LongText
    product_skus: Annotated[list[Sku], Field(max_length=5)] = []
    aspect_ratio: Ratio | None = None
    style: Text | None = None
    target_platform: OrganicPlatform | None = None
    reference_media_id: IdRef | None = None


class GenerateVideoParams(BaseModel):
    model_config = _STRICT
    prompt: LongText
    product_skus: Annotated[list[Sku], Field(max_length=5)] = []
    aspect_ratio: Literal["9:16", "16:9", "1:1"] | None = None
    duration_s: Annotated[int, Field(ge=2, le=60)] = 8
    style: Text | None = None
    target_platform: OrganicPlatform | None = None
    reference_media_id: IdRef | None = None


class CreateOrganicPostParams(BaseModel):
    model_config = _STRICT
    platforms: Annotated[list[OrganicPlatform], Field(min_length=1, max_length=4)]
    caption: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)] | None = None
    brief: LongText | None = None
    media_id: IdRef | None = None
    product_skus: Annotated[list[Sku], Field(max_length=10)] = []
    link_url: HttpsUrl | None = None

    @model_validator(mode="after")
    def _text(self) -> CreateOrganicPostParams:
        if not self.caption and not self.brief:
            raise ValueError("caption or brief is required")
        return self


class RegenerateOrganicCopyParams(BaseModel):
    model_config = _STRICT
    content_id: IdRef
    parts: Annotated[list[Literal["caption", "hashtags", "cta", "title"]], Field(min_length=1, max_length=4)] = ["caption"]
    platforms: Annotated[list[OrganicPlatform], Field(max_length=4)] = []
    instruction: Text | None = None


class ScheduleOrganicParams(BaseModel):
    model_config = _STRICT
    # A list of content ids, or "$n.content_ids" / "$n.content_id" from an earlier step.
    content_ids: Annotated[list[IdRef], Field(min_length=1, max_length=30)] | IdRef
    time_local: LocalTime
    start_date: dt.date | None = None
    timezone: Annotated[str, StringConstraints(max_length=64)] | None = None
    spread: Literal["one_per_day", "all_at_once"] = "one_per_day"
    platforms: Annotated[list[OrganicPlatform], Field(max_length=4)] = []


class OrganicContentRefParams(BaseModel):
    model_config = _STRICT
    content_id: IdRef
    platforms: Annotated[list[OrganicPlatform], Field(max_length=4)] = []


class OrganicPostRefParams(BaseModel):
    model_config = _STRICT
    post_id: IdRef


class RescheduleOrganicParams(BaseModel):
    model_config = _STRICT
    post_id: IdRef
    date: dt.date
    time_local: LocalTime
    timezone: Annotated[str, StringConstraints(max_length=64)] | None = None


# ---------------------------------------------------------------------------
# Execution context + registry
# ---------------------------------------------------------------------------
@dataclass
class ExecContext:
    db: Session
    tenant_id: str
    actor_user_id: str
    actor_role: str
    # Plan id + step index (SPEC-BE-090): Zernio's Idempotency-Key, so a retried step never makes a second campaign.
    request_id: str | None = None


Executor =Callable[[ExecContext, Any], dict[str, Any]]


@dataclass
class CommandAction:
    type: str
    label: str
    module: Literal["ecommerce", "shipping", "marketing", "meta", "organic", "workflows", "general"]
    risk: Risk
    params: Type[BaseModel]
    executor: Executor | None
    hint: str
    min_role: str = "manager"
    # Dynamic risk (e.g. enable_workflow depends on the workflow's actions).
    risk_fn: Callable[[ExecContext, Any], Risk] | None = None
    unavailable_reason: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def available(self) -> bool:
        return self.executor is not None and self.unavailable_reason is None


def _rows(items: list[dict[str, Any]], keys: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
    return [{k: item.get(k) for k in keys} for item in items[:limit]]


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


# --- E-Commerce -------------------------------------------------------------
def _inspect_products(ctx: ExecContext, p: InspectProductsParams) -> dict[str, Any]:
    from app.services import product_service

    items = product_service.list_products(ctx.db, ctx.tenant_id)
    if p.query:
        q = p.query.lower()
        items = [i for i in items if q in i["sku"].lower() or q in i["title"].lower()]
    if p.low_stock_only:
        items = [i for i in items if i["low_stock"]]
    rows = _rows(items, ("sku", "title", "price", "currency", "status", "stock", "low_stock"), p.limit)
    return {"summary": f"{len(items)} product(s) match; showing {len(rows)}.", "data": _jsonable(rows)}


def _inspect_orders(ctx: ExecContext, p: InspectOrdersParams) -> dict[str, Any]:
    from app.services import order_service

    result = order_service.list_orders(ctx.db, ctx.tenant_id, status=p.status, q=p.query, limit=p.limit)
    items = result.get("items", [])
    keys = ("order_number", "customer_name", "status", "total", "currency", "placed_at")
    return {"summary": f"{result.get('total', len(items))} order(s) match; showing {len(items)}.", "data": _jsonable(_rows(items, keys, p.limit))}


def _inspect_inventory(ctx: ExecContext, p: InspectInventoryParams) -> dict[str, Any]:
    from app.services import inventory_service

    items = (inventory_service.low_stock_items if p.low_stock_only else inventory_service.list_inventory)(ctx.db, ctx.tenant_id)
    if p.skus:
        items = [i for i in items if i["sku"] in p.skus]
    keys = ("sku", "product_title", "variant_label", "location_name", "on_hand", "committed", "available", "reorder_point", "low_stock")
    return {"summary": f"{len(items)} inventory row(s){' at or below reorder point' if p.low_stock_only else ''}.", "data": _jsonable(_rows(items, keys, 50))}


def _adjust_inventory(ctx: ExecContext, p: AdjustInventoryParams) -> dict[str, Any]:
    from app.services import inventory_service

    rows = [i for i in inventory_service.list_inventory(ctx.db, ctx.tenant_id) if i["sku"] == p.sku]
    if not rows:
        raise AppError(f"No inventory row for SKU {p.sku}.", 404)
    if len(rows) > 1:
        raise AppError(f"SKU {p.sku} is stocked at {len(rows)} locations; adjust it on the Inventory tab.", 409)
    result = inventory_service.adjust_on_hand(
        ctx.db, ctx.tenant_id, ctx.actor_user_id, str(rows[0]["id"]), p.new_on_hand, p.reason or "Command Chat"
    )
    return {"summary": f"{p.sku} on hand set to {p.new_on_hand}.", "inventory_id": str(rows[0]["id"]), "data": _jsonable(result)}


def _product_ids(ctx: ExecContext, skus: list[str]) -> list[str]:
    from app.models.product import Product

    found: dict[str, Any] = {
        sku: pid
        for sku, pid in ctx.db.query(Product.sku, Product.id)
        .filter(Product.tenant_id == ctx.tenant_id, Product.sku.in_(skus), Product.deleted_at.is_(None))
        .all()
    }
    unknown = sorted(set(skus) - set(found))
    if unknown:
        raise AppError(f"Unknown SKU(s): {', '.join(unknown)}.", 404)
    return [str(found[s]) for s in skus]


def _tenant_day_start(ctx: ExecContext, day: dt.date | None) -> dt.datetime | None:
    if day is None:
        return None
    from zoneinfo import ZoneInfo

    from app.models.tenant import Tenant

    tz = ctx.db.query(Tenant.timezone).filter(Tenant.id == ctx.tenant_id).scalar() or "UTC"
    return dt.datetime.combine(day, dt.time(0, 0), ZoneInfo(tz))


def _create_pricing_rule(ctx: ExecContext, p: PricingRuleParams) -> dict[str, Any]:
    from app.schemas.pricing import PricingRuleCreate
    from app.services import pricing_service

    payload = PricingRuleCreate(
        name=p.name,
        rule_type=p.rule_type,
        value=Decimal(str(p.value)),
        scope="all" if p.all_products else "sku",
        product_ids=[] if p.all_products else _product_ids(ctx, p.skus),  # type: ignore[arg-type]
        starts_at=_tenant_day_start(ctx, p.start_date),
        ends_at=_tenant_day_start(ctx, p.end_date + dt.timedelta(days=1)) if p.end_date else None,
    )
    rule = pricing_service.create_rule(ctx.db, ctx.tenant_id, ctx.actor_user_id, payload)
    return {"summary": f"Pricing rule “{p.name}” created.", "pricing_rule_id": str(rule["id"]), "link": "/ecommerce?tab=pricing"}


def _update_product(ctx: ExecContext, p: UpdateProductParams) -> dict[str, Any]:
    from app.services import product_service

    if p.title is not None and len(p.skus) > 1:
        raise AppError("A new title can only be set on one product at a time.", 422)
    changed = product_service.update_products(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.skus, p.status, p.title)
    return {"summary": f"Updated {len(changed)} product(s).", "data": changed}


# --- Shipping ---------------------------------------------------------------
def _inspect_shipping(ctx: ExecContext, p: NoParams) -> dict[str, Any]:
    from app.services import shipping_service

    status = shipping_service.get_status(ctx.db, ctx.tenant_id)
    zones = shipping_service.list_zones(ctx.db, ctx.tenant_id)
    rows = []
    for zone in zones["zones"]:
        for rate in zone["rates"] or [{}]:
            rows.append(
                {
                    "zone": zone["name"],
                    "zone_id": str(zone["id"]),
                    "countries": ", ".join(zone["country_codes"]) or "Rest of world",
                    "source": zone.get("source", "local"),
                    "method": rate.get("name"),
                    "type": rate.get("method_type"),
                    "rate": rate.get("rate"),
                    "free_over": rate.get("free_over"),
                    "active": rate.get("active", zone["active"]),
                }
            )
    summary = (
        f"{len(zones['zones'])} zone(s), {sum(len(z['rates']) for z in zones['zones'])} method(s); "
        f"mode {status['mode']}" + (f", last sync {status['last_sync_at']}" if status.get("last_sync_at") else "") + "."
    )
    return {"summary": summary, "data": _jsonable(rows), "currency": zones["currency"], "link": "/ecommerce?tab=shipping"}


def _create_shipping_zone(ctx: ExecContext, p: ShippingZoneParams) -> dict[str, Any]:
    from app.schemas.shipping import ShippingZoneCreate
    from app.services import shipping_service

    zone = shipping_service.create_zone(
        ctx.db, ctx.tenant_id, ctx.actor_user_id,
        ShippingZoneCreate(name=p.name, country_codes=[c.upper() for c in p.country_codes], regions=list(p.regions)),
    )
    return {"summary": f"Shipping zone “{p.name}” created.", "zone_id": str(zone["id"]), "link": "/ecommerce?tab=shipping"}


def _add_shipping_rate(ctx: ExecContext, p: ShippingRateParams) -> dict[str, Any]:
    from app.schemas.shipping import ShippingRateCreate
    from app.services import shipping_service

    rate = shipping_service.create_rate(
        ctx.db, ctx.tenant_id, ctx.actor_user_id, p.zone_id,
        ShippingRateCreate(
            name=p.name,
            carrier=p.carrier,
            rate=Decimal(str(p.rate)),
            free_over=Decimal(str(p.free_over)) if p.free_over else None,
            sla_days_min=p.sla_days_min,
            sla_days_max=p.sla_days_max,
            method_type=p.method_type,
        ),
    )
    return {"summary": f"Rate “{p.name}” added.", "rate_id": str(rate["id"]), "link": "/ecommerce?tab=shipping"}


def _update_shipping_rate(ctx: ExecContext, p: UpdateShippingRateParams) -> dict[str, Any]:
    from app.schemas.shipping import ShippingRateUpdate
    from app.services import shipping_service

    changes = p.model_dump(exclude={"rate_id"}, exclude_none=True)
    if not changes:
        raise AppError("Nothing to change.", 422)
    rate = shipping_service.update_rate(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.rate_id, ShippingRateUpdate(**changes))
    return {"summary": f"Rate “{rate['name']}” updated.", "rate_id": str(rate["id"]), "link": "/ecommerce?tab=shipping"}


def _set_free_threshold(ctx: ExecContext, p: FreeShippingThresholdParams) -> dict[str, Any]:
    from app.services import shipping_service

    result = shipping_service.set_free_shipping_threshold(
        ctx.db, ctx.tenant_id, ctx.actor_user_id, p.zone_id, Decimal(str(p.threshold))
    )
    return {"summary": f"Free shipping over {p.threshold} set on {result['updated']} rate(s).", "zone_id": p.zone_id, "link": "/ecommerce?tab=shipping"}


def _rate_toggle(active: bool) -> Executor:
    def run(ctx: ExecContext, p: RateToggleParams) -> dict[str, Any]:
        from app.schemas.shipping import ShippingRateUpdate
        from app.services import shipping_service

        rate = shipping_service.update_rate(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.rate_id, ShippingRateUpdate(active=active))
        return {"summary": f"Rate “{rate['name']}” {'enabled' if active else 'disabled'}.", "rate_id": str(rate["id"])}

    return run


def _sync_shipping(ctx: ExecContext, p: NoParams) -> dict[str, Any]:
    from app.services import shipping_service

    result = shipping_service.sync(ctx.db, ctx.tenant_id, ctx.actor_user_id)
    return {
        "summary": f"Shipping synced: {result['created']} created, {result['updated']} updated, {result['deactivated']} deactivated.",
        "data": _jsonable(result),
        "link": "/ecommerce?tab=shipping",
    }


# --- Marketing / Meta -------------------------------------------------------
def _inspect_campaigns(ctx: ExecContext, p: NoParams) -> dict[str, Any]:
    from app.services import campaign_service

    items = campaign_service.list_campaigns(ctx.db, ctx.tenant_id)
    keys = ("id", "name", "objective", "status", "channels", "budget", "spent", "currency")
    return {"summary": f"{len(items)} campaign(s).", "data": _jsonable(_rows(items, keys, 50)), "link": "/marketing/paid"}


def _campaign_results(ctx: ExecContext, p: CampaignResultsParams) -> dict[str, Any]:
    from app.services import analytics_service, campaign_service

    if p.campaign_id:
        result = campaign_service.get_campaign_results(ctx.db, ctx.tenant_id, p.campaign_id, p.range)
        return {"summary": result["summary"], "data": _jsonable(result["totals"]), "campaign_id": p.campaign_id, "link": f"/marketing/paid/{p.campaign_id}/edit"}
    report = analytics_service.get_ads_report(ctx.db, ctx.tenant_id, "7d" if p.range in ("7d", "lifetime") else p.range)
    return {"summary": "Ads results for the period (from imported Meta data).", "data": _jsonable(report.get("totals", {})), "link": "/analytics"}


def _generate_content(ctx: ExecContext, p: GenerateContentParams) -> dict[str, Any]:
    from app.services import content_service

    asset = content_service.generate_creative_asset(
        ctx.db, ctx.tenant_id, ctx.actor_user_id, p.objective, p.skus, p.brief, p.channel, campaign_id=p.campaign_id
    )
    return {"summary": "Creative drafts generated.", "content_asset_id": str(asset["id"])}


def _create_ai_campaign(ctx: ExecContext, p: AICampaignParams) -> dict[str, Any]:
    from app.schemas.ai_campaign import AICampaignCreate, Budget
    from app.services import ai_campaign_service

    run = ai_campaign_service.create_run(ctx.db, ctx.tenant_id, ctx.actor_user_id, AICampaignCreate(
        prompt=p.prompt, platforms=p.platforms, goal=p.goal, budget=Budget(amount=p.budget, mode=p.budget_mode),
        skus=p.skus, landing_url=p.landing_url, visuals=p.visuals))
    return {"run_id": run["id"], "status": run["status"], "url": f"/marketing/paid/ai/{run['id']}",
            "note": "The AI builds the drafts and stops for your review; nothing is published."}


def _create_meta_draft(ctx: ExecContext, p: MetaCampaignDraftParams) -> dict[str, Any]:
    from app.services import meta_builder_service

    tree = meta_builder_service.create_from_command(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.model_dump(mode="json"))
    missing = tree.get("missing") or []
    note = f" Still needed before publishing: {', '.join(m['message'] for m in missing[:4])}." if missing else ""
    return {
        "summary": f"Draft campaign “{p.name}” created with 1 ad set and 1 ad.{note}",
        "campaign_id": tree["campaign"]["id"],
        "link": f"/marketing/paid/{tree['campaign']['id']}/edit",
    }


def _validate_meta(ctx: ExecContext, p: CampaignRefParams) -> dict[str, Any]:
    from app.services import meta_builder_service

    result = meta_builder_service.validate(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.campaign_id)
    if result["ok"]:
        return {"summary": "The campaign passed validation.", "campaign_id": p.campaign_id}
    msgs = "; ".join(e["message"] for e in result["errors"][:5])
    return {"summary": f"Validation found {len(result['errors'])} issue(s): {msgs}", "campaign_id": p.campaign_id, "data": result["errors"]}


def _publish_meta(ctx: ExecContext, p: PublishMetaParams) -> dict[str, Any]:
    from app.services import meta_builder_service

    tree = meta_builder_service.publish(
        ctx.db, ctx.tenant_id, ctx.actor_user_id, ctx.actor_role == "owner", p.campaign_id, p.mode
    )
    campaign = tree["campaign"]
    meta = tree.get("meta") or {}
    return {
        "summary": f"Campaign “{campaign['name']}” is now {campaign['status']}" + (" on Meta." if meta.get("campaign_id") else "."),
        "campaign_id": campaign["id"],
        "meta_campaign_id": meta.get("campaign_id"),
        "link": meta.get("ads_manager_url") or f"/marketing/paid/{campaign['id']}/edit",
    }


def _publish_zernio(ctx: ExecContext, p: ZernioCampaignParams) -> dict[str, Any]:
    """SPEC-BE-090: the same zernio_service.create_campaign call as the Zernio form,
    so every Zernio rule (ownership, usable ad account, copy limits) applies."""
    from app.schemas import zernio as zs
    from app.services import zernio_service

    listing = zernio_service.platforms(ctx.db, ctx.tenant_id)
    if not listing["configured"]:
        raise AppError("Zernio isn't set up on this server.", 503)
    info = next(x for x in listing["platforms"] if x["key"] == p.platform)
    account = next((a for a in info["ads_accounts"] if not a["needs_reconnection"]), None)
    if account is None:
        raise AppError(f"Connect a {info['label']} ads account in the Zernio tab first.", 409)
    # The run starts at the start of start_date in the company timezone (now when
    # omitted or already begun) and ends duration_days later.
    now = dt.datetime.now(dt.timezone.utc)
    day_start = _tenant_day_start(ctx, p.start_date)
    start = day_start if day_start and day_start > now else None
    end = (start or now) + dt.timedelta(days=p.duration_days)
    try:
        payload = zs.CampaignCreate(
            platform=p.platform, account_id=account["id"], ad_account_id=p.ad_account_id, name=p.name, goal=p.goal,
            budget=zs.Budget(amount=p.budget, type=p.budget_type), start_at=start, end_at=end,
            targeting=zs.Targeting(countries=p.countries, age_min=p.age_min, age_max=p.age_max, gender=p.genders),
            creative=zs.Creative(headline=p.headline, body=p.primary_text, call_to_action=p.call_to_action,
                                 link_url=p.destination_url, media_id=p.media_id),
            status="ACTIVE" if p.mode == "active" else "PAUSED", request_id=ctx.request_id,
        )
    except ValidationError as exc:
        raise AppError("; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors()), 422) from None
    out = zernio_service.create_campaign(ctx.db, ctx.tenant_id, ctx.actor_user_id, payload)
    state = "active (it runs once Meta approves it)" if p.mode == "active" else "paused"
    return {
        "summary": f"Campaign “{p.name}” created on {info['label']} through Zernio, {state}.",
        "zernio_campaign_id": out["campaign_id"],
        "link": "/marketing/paid?tab=zernio",
    }


def _launch_campaign(ctx: ExecContext, p: CampaignRefParams) -> dict[str, Any]:
    from app.services import campaign_service

    detail = campaign_service.launch(ctx.db, ctx.tenant_id, ctx.actor_user_id, ctx.actor_role == "owner", p.campaign_id)
    return {"summary": f"Campaign “{detail['name']}” is {detail['status']}.", "campaign_id": str(detail["id"])}


def _meta_status(resume: bool) -> Executor:
    def run(ctx: ExecContext, p: MetaStatusParams) -> dict[str, Any]:
        from app.services import meta_builder_service

        result = meta_builder_service.set_status(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.level, p.object_id, resume)
        return {"summary": f"{p.level.replace('_', ' ').capitalize()} “{result['name']}” {'resumed' if resume else 'paused'}.", "object_id": p.object_id}

    return run


def _meta_budget(ctx: ExecContext, p: MetaBudgetParams) -> dict[str, Any]:
    from app.services import meta_builder_service

    result = meta_builder_service.update_budget(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.campaign_id, _cents(p.budget), p.budget_type)
    return {"summary": f"Budget of “{result['name']}” set to {p.budget} ({p.budget_type}).", "campaign_id": p.campaign_id}


# --- Workflows --------------------------------------------------------------
def _workflow_save(p: WorkflowDraftParams, enabled: bool = False) -> Any:
    from app.schemas.workflow import WorkflowActionIn, WorkflowSave

    return WorkflowSave(
        name=p.name,
        description=p.description,
        trigger_type=p.trigger_type,
        trigger_config=p.trigger_config,
        condition_dsl=p.condition_dsl,
        actions=[WorkflowActionIn(type=a.type, params=a.params) for a in p.actions],
        enabled=enabled,
    )


def _inspect_workflows(ctx: ExecContext, p: WorkflowRefParams) -> dict[str, Any]:
    from app.services import workflow_service

    if p.workflow_id:
        detail = workflow_service.describe_workflow(ctx.db, ctx.tenant_id, p.workflow_id)
        return {"summary": detail["summary"], "workflow_id": p.workflow_id, "data": _jsonable(detail), "link": f"/workflows?open={p.workflow_id}"}
    items = workflow_service.list_workflows(ctx.db, ctx.tenant_id)
    keys = ("id", "name", "trigger_type", "actions_count", "runs_7d", "status")
    return {"summary": f"{len(items)} workflow(s).", "data": _jsonable(_rows(items, keys, 50)), "link": "/workflows"}


def _create_workflow(ctx: ExecContext, p: WorkflowDraftParams) -> dict[str, Any]:
    from app.services import workflow_service

    # Always saved disabled (SPEC-BE-059/060); enabling is its own action.
    detail = workflow_service.create_workflow(ctx.db, ctx.tenant_id, ctx.actor_user_id, _workflow_save(p, enabled=False))
    return {"summary": f"Workflow “{p.name}” saved (disabled).", "workflow_id": str(detail["id"]), "link": f"/workflows?open={detail['id']}"}


def _update_workflow(ctx: ExecContext, p: UpdateWorkflowParams) -> dict[str, Any]:
    from app.services import workflow_service

    current = workflow_service.get_workflow(ctx.db, ctx.tenant_id, p.workflow_id)
    save = _workflow_save(p, enabled=current["status"] == "Enabled")
    detail = workflow_service.update_workflow(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.workflow_id, save)
    return {"summary": f"Workflow “{p.name}” saved as version {detail['version']}.", "workflow_id": str(detail["id"]), "link": f"/workflows?open={detail['id']}"}


def _set_workflow(enabled: bool) -> Executor:
    def run(ctx: ExecContext, p: WorkflowIdParams) -> dict[str, Any]:
        from app.services import workflow_service

        detail = workflow_service.set_enabled(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.workflow_id, enabled)
        return {"summary": f"Workflow “{detail['name']}” {'enabled' if enabled else 'disabled'}.", "workflow_id": str(detail["id"]), "link": f"/workflows?open={detail['id']}"}

    return run


def _run_workflow(ctx: ExecContext, p: RunWorkflowParams) -> dict[str, Any]:
    from app.services import workflow_service

    run = workflow_service.run_manual(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.workflow_id, p.input)
    return {"summary": f"Workflow run {run['status']}.", "workflow_id": p.workflow_id, "run_id": run["id"]}


# Workflow actions that spend money vs. merely notify (SPEC-BE-060 risk rule).
_SPEND_WORKFLOW_ACTIONS = {"launch_ad", "adjust_budget"}
_NOTIFY_WORKFLOW_ACTIONS = {"notify_owner", "create_task"}


def _enable_workflow_risk(ctx: ExecContext, p: WorkflowIdParams) -> Risk:
    # enable_workflow risk (SPEC-BE-060): spend when any step launches an ad or
    # changes a budget; otherwise change (notify-only workflows included - the
    # approval policy treats any live automation as a change). An unknown or
    # still-$ref workflow is treated as change; a $ref to a draft created in the
    # same plan is checked against that draft's params by plan_command().
    from app.models.workflow import Workflow

    if REF_RE.match(p.workflow_id):
        return "change"
    actions = (
        ctx.db.query(Workflow.actions)
        .filter(Workflow.tenant_id == ctx.tenant_id, Workflow.id == p.workflow_id)
        .scalar()
    ) or []
    types = {a.get("type") for a in actions if isinstance(a, dict)}
    return "spend" if types & _SPEND_WORKFLOW_ACTIONS else "change"


# --- General ----------------------------------------------------------------
def _notify_owner(ctx: ExecContext, p: NotifyOwnerParams) -> dict[str, Any]:
    from app.workflow_engine import actions as notification_helpers

    count = notification_helpers.notify_role(ctx.db, ctx.tenant_id, "owner", "owner_notice", "Message from Command Chat", p.message)
    return {"summary": f"Owner notified ({count} recipient(s))."}


def _create_task(ctx: ExecContext, p: CreateTaskParams) -> dict[str, Any]:
    from app.workflow_engine import actions as notification_helpers

    count = notification_helpers.notify_role(
        ctx.db, ctx.tenant_id, p.assignee_role, "task", p.title, p.details or "", metadata={"assignee_role": p.assignee_role, "source": "command_chat"}
    )
    return {"summary": f"Task “{p.title}” created for {p.assignee_role} ({count} recipient(s))."}


def _call_webhook(ctx: ExecContext, p: CallWebhookParams) -> dict[str, Any]:
    from app.workflow_engine import actions as notification_helpers

    status = notification_helpers.post_webhook(p.url, {"event": p.event, "tenant_id": str(ctx.tenant_id), "source": "command_chat"})
    return {"summary": f"Webhook answered HTTP {status}."}


# --- Organic Marketing executors (SPEC-BE-078) ----------------------------------
# They call organic_service / generation_service only, so approval rules,
# platform validation, tenant scoping and audit rows are the same as in the UI.
def _sku_ids(ctx: ExecContext, skus: list[str]) -> list[str]:
    from app.services.organic_service import products

    if not skus:
        return []
    rows = products(ctx.db, ctx.tenant_id, skus=skus)
    missing = sorted(set(skus) - {r["sku"] for r in rows})
    if missing:
        raise AppError(f"Unknown SKU(s): {', '.join(missing)}.", 422)
    return [r["id"] for r in rows]


def _inspect_organic(ctx: ExecContext, p: InspectOrganicParams) -> dict[str, Any]:
    from app.services import organic_service

    if p.status in (None, "scheduled"):
        summary = organic_service.summary(ctx.db, ctx.tenant_id)
        rows = [r for r in summary["upcoming"] if not p.platform or r["platform"] == p.platform]
        if p.status == "scheduled":
            return {"summary": f"{len(rows)} upcoming post(s).", "data": _jsonable(_rows(rows, ("platform", "local_time", "timezone", "excerpt", "status"), 20)),
                    "link": "/marketing/organic/calendar"}
        return {"summary": (f"{summary['scheduled_next_7d']} scheduled in the next 7 days, {summary['published_30d']} published in 30 days, "
                            f"{summary['failed_open']} failed, {summary['awaiting_approval']} awaiting approval."),
                "data": _jsonable(_rows(rows, ("platform", "local_time", "excerpt", "status"), 10)), "link": "/marketing/organic"}
    hist = organic_service.history(ctx.db, ctx.tenant_id, p.status, p.platform, 1)
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=p.days)
    rows = [r for r in hist["items"] if (r["published_at"] or r["scheduled_at"]) >= since]
    return {"summary": f"{len(rows)} {p.status} post(s) in the last {p.days} days.",
            "data": _jsonable(_rows(rows, ("platform", "local_time", "excerpt", "external_url", "error_message"), 20)), "link": "/marketing/organic/history"}


def _organic_analytics(ctx: ExecContext, p: OrganicAnalyticsParams) -> dict[str, Any]:
    from app.services import analytics_service

    report = analytics_service.get_organic_report(ctx.db, ctx.tenant_id, p.range)
    totals = {k: ("no data yet" if v is None else v) for k, v in report["totals"].items()}
    return {"summary": f"{report['posts_published']} post(s) published in {p.range}." + (f" {report['missing_reason']}" if report["missing_reason"] else ""),
            "data": _jsonable({**totals, "engagement_rate_pct": report["engagement_rate"] if report["engagement_rate"] is not None else "no data yet"}),
            "link": "/marketing/organic/analytics"}


def _organic_insights(ctx: ExecContext, p: OrganicInsightsParams) -> dict[str, Any]:
    from app.services import organic_service

    data = organic_service.insights(ctx.db, ctx.tenant_id, p.days)
    summary = " ".join(line["text"] for line in data["lines"]) if data["has_data"] else str(data["reason"])
    return {"summary": summary, "data": _jsonable({"lines": [line["text"] for line in data["lines"]], "platforms": data["platforms"]}),
            "link": "/marketing/organic/analytics"}


def _wait_for_job(ctx: ExecContext, job: dict[str, Any]) -> dict[str, Any]:
    """Runs the generation in this (already background) plan step and waits
    for it, so the next step can use $n.media_id."""
    from app.services import generation_service

    generation_service.run_job(ctx.db, job["id"])
    done = generation_service.get_job(ctx.db, ctx.tenant_id, job["id"])
    if done["status"] != "succeeded":
        raise AppError(f"Generation {done['status']}: {done['error'] or 'no details'}", 502)
    return done


# Command Chat media chains (SPEC-BE-093, amending SPEC-BE-092): Google
# first, OpenAI on any failure. Images: Nano Banana (Gemini image), then
# OpenAI images. Videos: Google Flow (= Veo 3.1 through the Gemini API; Flow
# itself has no API), then an OpenAI slideshow (OpenAI shut down Sora on
# 2026-09-24). The chain is pinned in the job request, so retries keep it;
# the models are the company's own choices in AI Models.
CHAT_CHAINS = {"image": ["gemini_image", "openai_image"], "video": ["gemini_video", "openai_slideshow"]}
CHAT_PROVIDER_NAMES = {"gemini_image": "Nano Banana", "openai_image": "OpenAI images",
                       "gemini_video": "Google Flow (Veo)", "openai_slideshow": "OpenAI images as a slideshow"}
CHAT_NOT_READY = {
    "image": "No image provider is set up: add a Google Gemini key with a Nano Banana image model "
             "(e.g. gemini-2.5-flash-image), or an OpenAI key with an image model, in Integrations › AI Models.",
    "video": "No video provider is set up: add a Google Gemini key with a Veo video model "
             "(e.g. veo-3.1-generate-preview), or an OpenAI key with an image model (for a slideshow video), "
             "in Integrations › AI Models.",
}


def _chat_generator_ready(ctx: ExecContext, kind: str) -> None:
    from app.ai import creative_providers as cp

    if not any(cp.provider(k).available(ctx.db, ctx.tenant_id) for k in CHAT_CHAINS[kind]):
        raise AppError(CHAT_NOT_READY[kind], 409)


def _generation_request(ctx: ExecContext, p: GeneratePhotoParams | GenerateVideoParams, kind: str) -> dict[str, Any]:
    _chat_generator_ready(ctx, kind)
    req = p.model_dump(exclude_none=True, exclude={"product_skus", "reference_media_id"})
    req["product_ids"] = _sku_ids(ctx, p.product_skus)
    if p.reference_media_id:
        req["reference_media_ids"] = [p.reference_media_id]
    req["providers"] = list(CHAT_CHAINS[kind])
    return req


def _fallback_note(job: dict[str, Any]) -> str:
    """'Nano Banana failed (HTTP 429 …), so OpenAI images made it.' when an
    earlier provider of the chain failed."""
    used = job.get("provider")
    failed = [a for a in job.get("attempts") or [] if a.get("provider") != used and a.get("outcome") not in ("started", "succeeded")]
    if not failed:
        return ""
    why = "; ".join(f"{CHAT_PROVIDER_NAMES.get(a['provider'], a['provider'])} failed ({str(a.get('outcome'))[:90]})" for a in failed)
    return f"{why}, so {CHAT_PROVIDER_NAMES.get(str(used), used)} made it."


def _generated(job: dict[str, Any], kind: str, summary: str, link: str) -> dict[str, Any]:
    return {"summary": summary, "media_id": job["media"]["id"], "media_kind": kind, "generation_id": job["id"],
            "provider": CHAT_PROVIDER_NAMES.get(str(job.get("provider")), job.get("provider")), "model": job.get("model"), "link": link}


def _generate_photo(ctx: ExecContext, p: GeneratePhotoParams) -> dict[str, Any]:
    from app.services import generation_service

    job = _wait_for_job(ctx, generation_service.start(ctx.db, ctx.tenant_id, ctx.actor_user_id, "image",
                                                      _generation_request(ctx, p, "image"), run=False))
    who = CHAT_PROVIDER_NAMES.get(str(job.get("provider")), job.get("provider"))
    summary = f"Image made with {who}, model {job.get('model')}. {_fallback_note(job)} {' '.join(job['notes'])}"
    return _generated(job, "image", " ".join(summary.split()), "/marketing/organic/photo")


def _generate_video(ctx: ExecContext, p: GenerateVideoParams) -> dict[str, Any]:
    from app.services import generation_service

    job = _wait_for_job(ctx, generation_service.start(ctx.db, ctx.tenant_id, ctx.actor_user_id, "video",
                                                      _generation_request(ctx, p, "video"), run=False))
    who = CHAT_PROVIDER_NAMES.get(str(job.get("provider")), job.get("provider"))
    summary = (f"Video made with {who}, model {job.get('model')}: {job['effective'].get('duration_s')} s, "
               f"{job['effective'].get('aspect_ratio')}. {_fallback_note(job)} {' '.join(job['notes'])}")
    return _generated(job, "video", " ".join(summary.split()), "/marketing/organic/video")


def _create_organic_posts(ctx: ExecContext, p: CreateOrganicPostsParams) -> dict[str, Any]:
    from app.services import organic_service

    product_ids = _sku_ids(ctx, p.product_skus)
    rows = organic_service.products(ctx.db, ctx.tenant_id, ids=product_ids)
    media = organic_service.product_photo_media(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.product_skus) if p.media == "product_photos" else []
    posts, result = organic_service.ai_posts(ctx.db, ctx.tenant_id, p.brief, list(p.platforms), rows, p.tone, p.link_url, p.count)
    targets = [{"platform": pl} for pl in p.platforms]
    ids = []
    for post in posts:
        content = organic_service._create_ai_content(  # noqa: SLF001 - the service's own builder
            ctx.db, ctx.tenant_id, ctx.actor_user_id, prompt=p.brief, post=post, targets=targets, product_rows=rows, tone=p.tone,
            link_url=p.link_url, media=media[:1], model=result.model, extra={"source": "command_chat"})
        if p.media in ("generate_photo", "generate_video"):
            organic_service.start_media_generation(ctx.db, ctx.tenant_id, ctx.actor_user_id, content, p.media, {}, targets)
        ids.append(str(content.id))
    ctx.db.flush()
    from app.core.audit import write_audit_log

    write_audit_log(ctx.db, tenant_id=ctx.tenant_id, actor_user_id=ctx.actor_user_id, action="organic.created", resource_type="organic_content",
                    resource_id=ids[0], metadata={"count": len(ids), "source": "command_chat", "platforms": list(p.platforms)})
    short_of = f" (the AI model returned {len(ids)} of {p.count})" if len(ids) < p.count else ""
    return {"summary": f"{len(ids)} post draft(s) for {', '.join(p.platforms)}{short_of}; they need approval before publishing.",
            "content_ids": ids, "content_id": ids[0], "link": "/marketing/organic"}


def _create_organic_post(ctx: ExecContext, p: CreateOrganicPostParams) -> dict[str, Any]:
    from app.schemas.organic import AICreate, AIMedia, ManualCreate
    from app.services import organic_service

    media_ids = [p.media_id] if p.media_id else []
    targets = [{"platform": pl} for pl in p.platforms]
    if p.caption:
        content = organic_service.create_manual(ctx.db, ctx.tenant_id, ctx.actor_user_id, ManualCreate.model_validate(
            {"caption": p.caption, "media_ids": media_ids, "targets": targets, "link_url": p.link_url}))
    else:
        content = organic_service.create_ai(ctx.db, ctx.tenant_id, ctx.actor_user_id, AICreate.model_validate(
            {"prompt": p.brief, "targets": targets, "product_ids": _sku_ids(ctx, p.product_skus), "link_url": p.link_url,
             "media": AIMedia(mode="use" if media_ids else "none", media_ids=media_ids).model_dump()}))
    caption = (content["versions"][0]["caption"] if content["versions"] else content["caption"])[:200]
    return {"summary": f"Post drafted for {', '.join(p.platforms)}: “{caption}”", "content_id": content["id"], "content_ids": [content["id"]],
            "link": f"/marketing/organic/content/{content['id']}"}


def _regenerate_organic_copy(ctx: ExecContext, p: RegenerateOrganicCopyParams) -> dict[str, Any]:
    from app.services import organic_service

    content = organic_service.get_content(ctx.db, ctx.tenant_id, p.content_id)
    versions = [v for v in content["versions"] if not p.platforms or v["platform"] in p.platforms]
    if not versions:
        raise AppError("That post has no version for those platforms.", 422)
    for v in versions:
        content = organic_service.regenerate(ctx.db, ctx.tenant_id, ctx.actor_user_id, v["id"], list(p.parts), p.instruction)
    first = content["versions"][0]
    return {"summary": f"New {', '.join(p.parts)} for {', '.join(v['platform'] for v in versions)}; the media is unchanged. Now: “{first['caption'][:160]}”",
            "content_id": p.content_id, "link": f"/marketing/organic/content/{p.content_id}"}


def _schedule_organic(ctx: ExecContext, p: ScheduleOrganicParams) -> dict[str, Any]:
    from types import SimpleNamespace

    from app.services import organic_service

    ids = [p.content_ids] if isinstance(p.content_ids, str) else list(p.content_ids)
    zone = p.timezone or organic_service.tenant_tz(ctx.db, ctx.tenant_id)
    hour, minute = (int(x) for x in p.time_local.split(":"))
    import zoneinfo

    now_local = dt.datetime.now(zoneinfo.ZoneInfo(zone)).replace(tzinfo=None)
    start = p.start_date or now_local.date()
    if p.start_date is None and dt.datetime.combine(start, dt.time(hour, minute)) < now_local + dt.timedelta(minutes=5):
        start += dt.timedelta(days=1)  # today's slot has passed: start tomorrow
    scheduled: list[str] = []
    for i, content_id in enumerate(ids):
        day = start + dt.timedelta(days=i if p.spread == "one_per_day" else 0)
        local = dt.datetime.combine(day, dt.time(hour, minute))
        content = organic_service.get_content(ctx.db, ctx.tenant_id, content_id)
        if content["status"] == "needs_approval":
            # This step is a "change": it ran only after the plan's approval
            # (or the owner's own command), which approves the content too.
            organic_service.approve(ctx.db, ctx.tenant_id, ctx.actor_user_id, content_id)
        def wanted(v: dict[str, Any]) -> bool:
            # The chosen platforms; skip versions already published or already
            # scheduled/publishing (a cancelled or failed one can go again).
            active = v["post"] is not None and v["post"]["status"] in ("pending", "scheduled", "publishing")
            return (not p.platforms or v["platform"] in p.platforms) and v["status"] != "published" and not active

        items = [SimpleNamespace(version_id=v["id"], scheduled_at_local=local, timezone=zone) for v in content["versions"] if wanted(v)]
        if not items:
            continue
        organic_service.schedule_bulk(ctx.db, ctx.tenant_id, ctx.actor_user_id, content_id, items)
        scheduled.extend(f"{local:%a %d %b %H:%M}" for _ in items)
    if not scheduled:
        raise AppError("Nothing to schedule: those posts are already scheduled or published.", 409)
    days = sorted(set(scheduled))
    return {"summary": f"{len(scheduled)} post(s) scheduled ({zone}): {', '.join(days[:7])}{'…' if len(days) > 7 else ''}.",
            "content_ids": ids, "link": "/marketing/organic/calendar"}


def _publish_organic_now(ctx: ExecContext, p: OrganicContentRefParams) -> dict[str, Any]:
    from app.services import organic_service

    content = organic_service.get_content(ctx.db, ctx.tenant_id, p.content_id)
    if content["status"] == "needs_approval":
        organic_service.approve(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.content_id)
    posts = [organic_service.publish_now(ctx.db, ctx.tenant_id, ctx.actor_user_id, v["id"]) for v in content["versions"]
             if (not p.platforms or v["platform"] in p.platforms) and v["status"] != "published"]
    if not posts:
        raise AppError("Nothing to publish for that post.", 409)
    return {"summary": "; ".join(f"{r['platform']}: {r['status']}" + (f" ({r['error_message']})" if r["error_message"] else "") for r in posts),
            "content_id": p.content_id, "link": "/marketing/organic/history"}


def _cancel_organic(ctx: ExecContext, p: OrganicPostRefParams) -> dict[str, Any]:
    from app.services import organic_service

    post = organic_service.cancel(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.post_id)
    return {"summary": f"Cancelled the {post['platform']} post.", "post_id": p.post_id, "link": "/marketing/organic/calendar"}


def _reschedule_organic(ctx: ExecContext, p: RescheduleOrganicParams) -> dict[str, Any]:
    from app.services import organic_service

    hour, minute = (int(x) for x in p.time_local.split(":"))
    post = organic_service.reschedule(ctx.db, ctx.tenant_id, ctx.actor_user_id, p.post_id, dt.datetime.combine(p.date, dt.time(hour, minute)), p.timezone)
    return {"summary": f"Moved the {post['platform']} post to {post['local_time']} ({post['timezone']}).", "post_id": p.post_id,
            "link": "/marketing/organic/calendar"}


REGISTRY: dict[str, CommandAction] = {}


def _reg(action: CommandAction) -> None:
    REGISTRY[action.type] = action


for _a in (
    # E-Commerce
    CommandAction("inspect_products", "Show products", "ecommerce", "read", InspectProductsParams, _inspect_products, "List/search products, stock and low-stock flags.", min_role="viewer"),
    CommandAction("inspect_orders", "Show orders", "ecommerce", "read", InspectOrdersParams, _inspect_orders, "List recent orders, optionally by status or search text.", min_role="viewer"),
    CommandAction("inspect_inventory", "Show inventory", "ecommerce", "read", InspectInventoryParams, _inspect_inventory, "Inventory rows; low-stock only by default.", min_role="viewer"),
    CommandAction("adjust_inventory", "Adjust stock", "ecommerce", "change", AdjustInventoryParams, _adjust_inventory, "Set the on-hand count of one SKU."),
    CommandAction("create_pricing_rule", "Create pricing rule", "ecommerce", "change", PricingRuleParams, _create_pricing_rule, "Discount or fixed price for SKUs or all products, optional dates.", aliases=("adjust_pricing",)),
    CommandAction("update_product", "Update products", "ecommerce", "change", UpdateProductParams, _update_product, "Change status (or the title of one product)."),
    # Shipping
    CommandAction("inspect_shipping", "Show shipping setup", "shipping", "read", NoParams, _inspect_shipping, "Zones, methods, rates, thresholds, sync status.", min_role="viewer"),
    CommandAction("create_shipping_zone", "Create shipping zone", "shipping", "change", ShippingZoneParams, _create_shipping_zone, "New zone with ISO country codes and optional regions."),
    CommandAction("add_shipping_rate", "Add shipping method", "shipping", "change", ShippingRateParams, _add_shipping_rate, "Add a method/rate to a zone (zone_id from context or $n.zone_id)."),
    CommandAction("update_shipping_rate", "Update shipping method", "shipping", "change", UpdateShippingRateParams, _update_shipping_rate, "Change a rate's name, price, free-over threshold, SLA or active flag."),
    CommandAction("set_free_shipping_threshold", "Set free-shipping threshold", "shipping", "change", FreeShippingThresholdParams, _set_free_threshold, "Free shipping over an order amount for every paid rate in a zone."),
    CommandAction("enable_shipping_rate", "Enable shipping method", "shipping", "change", RateToggleParams, _rate_toggle(True), "Turn a rate on."),
    CommandAction("disable_shipping_rate", "Disable shipping method", "shipping", "change", RateToggleParams, _rate_toggle(False), "Turn a rate off."),
    CommandAction("sync_shipping", "Sync shipping from store", "shipping", "change", NoParams, _sync_shipping, "Import/refresh shipping from the connected Shopify/WooCommerce store."),
    # Marketing
    CommandAction("inspect_campaigns", "Show campaigns", "marketing", "read", NoParams, _inspect_campaigns, "All campaigns with status, budget and spend.", min_role="viewer"),
    CommandAction("inspect_campaign_results", "Show campaign results", "marketing", "read", CampaignResultsParams, _campaign_results, "Real imported Meta results (spend, CTR, ROAS, conversions).", min_role="viewer"),
    CommandAction("generate_content", "Generate ad copy", "marketing", "draft", GenerateContentParams, _generate_content, "AI creative drafts for products (nothing is published)."),
    CommandAction("send_message", "Send a message", "marketing", "change", NoParams, None, "", unavailable_reason="Outbound customer messaging isn't connected yet."),
    CommandAction("create_ai_campaign", "Create campaign with AI", "marketing", "draft", AICampaignParams, _create_ai_campaign,
                  "AI Ad Autopilot: plan, targeting, copy and images for 1-3 platforms from a brief; builds drafts and stops for review (never publishes)."),
    # Organic Marketing (SPEC-BE-078). Drafts run at once; scheduling and
    # publishing are "change" (approval by another manager+, the owner's own
    # command auto-approves); nothing here spends money.
    CommandAction("inspect_organic", "Show organic posts", "organic", "read", InspectOrganicParams, _inspect_organic,
                  "Organic posts: upcoming (status scheduled/none) or history (published/failed/cancelled).", min_role="viewer"),
    CommandAction("inspect_organic_analytics", "Show organic results", "organic", "read", OrganicAnalyticsParams, _organic_analytics,
                  "Imported organic post results (impressions, engagements); null = no data yet.", min_role="viewer"),
    CommandAction("organic_insights", "What's working (organic)", "organic", "read", OrganicInsightsParams, _organic_insights,
                  "What performed best: formats, posting hours, hashtags and top posts per platform (computed from imported results).",
                  min_role="viewer"),
    CommandAction("create_organic_posts", "Draft organic posts", "organic", "draft", CreateOrganicPostsParams, _create_organic_posts,
                  "AI writes `count` different organic posts adapted per platform (drafts needing approval). media: none | product_photos | generate_photo | generate_video. Returns content_ids."),
    CommandAction("create_organic_post", "Draft an organic post", "organic", "draft", CreateOrganicPostParams, _create_organic_post,
                  "One organic post: a given caption, or AI copy from brief; media_id from the media library or $n.media_id. Returns content_id."),
    CommandAction("generate_photo", "Generate a photo", "organic", "draft", GeneratePhotoParams, _generate_photo,
                  "Make an image/photo/picture: Nano Banana (Google) first, OpenAI images if it fails; for posts or ads (waits for it). Returns media_id."),
    CommandAction("generate_video", "Generate a video", "organic", "draft", GenerateVideoParams, _generate_video,
                  "Make a video clip: Google Flow (Veo 3.1, 4/6/8 s) first, an OpenAI image slideshow (4-30 s) if it fails; 16:9 or 9:16 (waits for it). Returns media_id."),
    CommandAction("regenerate_organic_copy", "Rewrite post text", "organic", "draft", RegenerateOrganicCopyParams, _regenerate_organic_copy,
                  "New caption/hashtags/cta/title for a post; the image/video is never changed. content_id from recent_organic."),
    CommandAction("schedule_organic_posts", "Schedule organic posts", "organic", "change", ScheduleOrganicParams, _schedule_organic,
                  "Approve and schedule posts at time_local (HH:MM, company timezone unless given) from start_date; spread one_per_day or all_at_once.",
                  aliases=("schedule_post",)),
    CommandAction("publish_organic_now", "Publish a post now", "organic", "change", OrganicContentRefParams, _publish_organic_now,
                  "Publish a post to its platforms immediately."),
    CommandAction("cancel_organic_post", "Cancel a scheduled post", "organic", "change", OrganicPostRefParams, _cancel_organic, "Cancel one scheduled post (post_id)."),
    CommandAction("reschedule_organic_post", "Reschedule a post", "organic", "change", RescheduleOrganicParams, _reschedule_organic,
                  "Move one scheduled or failed post to a new local date/time."),
    # Paid Marketing - Meta campaigns
    CommandAction("create_meta_campaign_draft", "Create Meta campaign draft", "meta", "draft", MetaCampaignDraftParams, _create_meta_draft, "Full campaign → ad set → ad draft on our side (nothing sent to Meta)."),
    CommandAction("validate_meta_campaign", "Validate Meta campaign", "meta", "read", CampaignRefParams, _validate_meta, "Local + Meta validation of a draft."),
    CommandAction("publish_meta_campaign", "Publish to Meta", "meta", "spend", PublishMetaParams, _publish_meta, "Create the campaign on Meta (active or paused)."),
    CommandAction("pause_meta", "Pause on Meta", "meta", "change", MetaStatusParams, _meta_status(False), "Pause a campaign, ad set or ad."),
    CommandAction("resume_meta", "Resume on Meta", "meta", "spend", MetaStatusParams, _meta_status(True), "Resume a campaign, ad set or ad."),
    CommandAction("update_meta_budget", "Change Meta budget", "meta", "spend", MetaBudgetParams, _meta_budget, "New daily or lifetime budget on a published campaign."),
    CommandAction("publish_zernio_campaign", "Publish ad campaign through Zernio", "marketing", "spend", ZernioCampaignParams, _publish_zernio,
                  "Facebook/Instagram campaign → ad set → ad created on Zernio. ad_account_id from zernio_ads.ad_accounts; media_id from recent_media or $n.media_id; mode paused unless the user asks to run/publish/launch."),
    CommandAction("launch_campaign", "Launch campaign", "marketing", "spend", CampaignRefParams, _launch_campaign, "Launch an existing wizard draft (non-Meta channels).", aliases=("launch_ad",)),
    CommandAction("adjust_budget", "Adjust ad budget", "marketing", "spend", NoParams, None, "", unavailable_reason="Use update_meta_budget for Meta campaigns."),
    # Workflows
    CommandAction("inspect_workflows", "Show workflows", "workflows", "read", WorkflowRefParams, _inspect_workflows, "List workflows, or describe one.", min_role="viewer"),
    CommandAction("create_workflow", "Create workflow", "workflows", "draft", WorkflowDraftParams, _create_workflow, "Save a new workflow (always disabled)."),
    CommandAction("update_workflow", "Edit workflow", "workflows", "draft", UpdateWorkflowParams, _update_workflow, "Save a new version of a workflow."),
    CommandAction("enable_workflow", "Turn workflow on", "workflows", "change", WorkflowIdParams, _set_workflow(True), "Enable a workflow (workflow_id or $n.workflow_id).", risk_fn=_enable_workflow_risk),
    CommandAction("disable_workflow", "Turn workflow off", "workflows", "change", WorkflowIdParams, _set_workflow(False), "Disable a workflow."),
    CommandAction("run_workflow", "Run workflow now", "workflows", "change", RunWorkflowParams, _run_workflow, "Run a workflow once with an input."),
    # General
    CommandAction("notify_owner", "Notify the owner", "general", "change", NotifyOwnerParams, _notify_owner, "In-app notification to the owner(s).", min_role="agent"),
    CommandAction("create_task", "Create a task", "general", "change", CreateTaskParams, _create_task, "Task notification for a role (e.g. draft a restock PO).", min_role="agent"),
    CommandAction("call_webhook", "Call a webhook", "general", "change", CallWebhookParams, _call_webhook, "POST to a public https URL."),
):
    _reg(_a)

ALIASES = {alias: a.type for a in REGISTRY.values() for alias in a.aliases}

# Read and draft actions run immediately; change and spend wait for approval
# (policy below). Overridable per tenant via tenants.settings.approval_policy =
# {"<action_type>": "auto" | "approval" | "owner"} (no UI in v1).
DEFAULT_POLICY = (
    "read -> runs now (any role). draft -> runs now (manager+), creates drafts only. "
    "change -> needs approval by a manager+ other than the requester; the owner's own "
    "command counts as approval. spend -> always needs an explicit owner approval."
)


def resolve(action_type: str) -> CommandAction | None:
    return REGISTRY.get(ALIASES.get(action_type, action_type))


def role_allows(role: str, minimum: str) -> bool:
    try:
        return role_at_least(role, Role(minimum))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Clarifying questions (fixed templates; LLM text is never echoed)
# ---------------------------------------------------------------------------
FIELD_QUESTIONS: dict[str, str] = {
    "budget": "What budget should I use (amount in your currency, and daily or total)?",
    "duration_days": "How many days should it run?",
    "countries": "Which countries should the ads target (for example BD)?",
    "destination_url": "Which https web page should the ad link to?",
    "landing_url": "Which https web page should the ads send people to?",
    "objective": "What's the goal: awareness, traffic, engagement, leads, app promotion or sales?",
    "name": "What should I call it?",
    "skus": "Which products (SKUs) does this cover?",
    "threshold": "At what order amount should shipping become free?",
    "zone_id": "Which shipping zone?",
    "rate_id": "Which shipping method?",
    "rate": "What should the shipping price be?",
    "country_codes": "Which countries does this zone cover (two-letter codes, e.g. BD)?",
    "trigger_type": "What should start the workflow (e.g. low stock, a new order, a schedule)?",
    "actions": "What should the workflow do when it runs?",
    "trigger_config.threshold": "What stock level counts as low (the workflow fires at or below it)?",
    "workflow_id": "Which workflow?",
    "campaign_id": "Which campaign?",
    "object_id": "Which campaign, ad set or ad?",
    "new_on_hand": "What should the new stock count be?",
    "sku": "Which SKU?",
    "value": "What discount or price value should I use?",
    "rule_type": "Should it be a percentage discount, a fixed discount or a fixed price?",
    "message": "What should the message say?",
    "title": "What should the title be?",
    "url": "Which https URL should I call?",
    "best_seller": "How should I decide a best seller: units sold in the last 30 days at or above what number?",
    # Organic Marketing (SPEC-BE-078)
    "content_id": "Which post do you mean?",
    "content_ids": "Which posts should I schedule?",
    "post_id": "Which scheduled post?",
    "time_local": "At what time should it go out (for example 20:00)?",
    "platforms": "Which platforms: Facebook, Instagram, TikTok or LinkedIn?",
    "count": "How many posts should I write?",
    "brief": "What should the posts be about?",
    "prompt": "Describe what you'd like me to generate.",
    "caption": "What should the post say (or what should it be about)?",
    "date": "Which day should it move to?",
    # Zernio ad campaigns (SPEC-BE-090)
    "ad_account_id": "Which ad account should the ads run on?",
    "media_id": "Which image or video should the ad use? I can generate one: say what it should show.",
    "goal": "What's the goal: awareness, traffic, engagement, video views or sales?",
}
GENERIC_FIELD_QUESTION = "What should “{field}” be for “{action}”?"


def question_for(action_label: str, field_path: str) -> str:
    leaf = field_path.split(".")[-1]
    return FIELD_QUESTIONS.get(field_path) or FIELD_QUESTIONS.get(leaf) or GENERIC_FIELD_QUESTION.format(
        field=leaf.replace("_", " "), action=action_label
    )


# ---------------------------------------------------------------------------
# Planning: LLM output -> validated actions or missing fields
# ---------------------------------------------------------------------------
@dataclass
class DraftAction:
    index: int  # 1-based
    type: str
    params: dict[str, Any]
    description: str
    depends_on: list[int]
    module: str = ""
    risk: Risk = "read"
    label: str = ""
    cost_estimate_cents: int | None = None


@dataclass
class Missing:
    index: int
    field: str
    question: str


@dataclass
class Dropped:
    index: int
    reason: Literal[
        "unknown_action_type", "not_available", "forbidden_for_role", "invalid_action", "bad_reference",
        # SPEC-BE-085: a step the user didn't ask for, and steps that need it.
        "not_requested", "depends_on_dropped",
    ]
    detail: str = ""


@dataclass
class CommandPlan:
    actions: list[DraftAction]
    missing: list[Missing]
    dropped: list[Dropped]
    summary: str
    new_request: bool
    raw_actions: list[dict[str, Any]]


def _refs(value: Any) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    if isinstance(value, str):
        m = REF_RE.match(value)
        if m:
            found.append((int(m.group(1)), m.group(2)))
    elif isinstance(value, dict):
        for v in value.values():
            found.extend(_refs(v))
    elif isinstance(value, list):
        for v in value:
            found.extend(_refs(v))
    return found


def _cost(action: CommandAction, params: BaseModel) -> int | None:
    # Cost basis (SPEC-BE-032 kept): only stated budgets count; never an estimate.
    if isinstance(params, MetaCampaignDraftParams):
        return _cents(params.budget) * (params.duration_days if params.budget_type == "daily" else 1)
    if isinstance(params, MetaBudgetParams):
        return _cents(params.budget)
    return 0 if action.risk != "spend" else None


def validate_actions(
    ctx: ExecContext,
    raw_actions: list[Any],
    extra_checks: Callable[[ExecContext, DraftAction, BaseModel], list[tuple[str, str]]] | None = None,
    pre_dropped: dict[int, Dropped] | None = None,
) -> tuple[list[DraftAction], list[Missing], list[Dropped]]:
    """Validates raw {type, params, description, depends_on} items. Role-gated,
    unavailable and unknown actions are dropped; schema failures become Missing
    entries (one question per field). `pre_dropped` (position -> Dropped) are
    steps the caller already left out (SPEC-BE-085 scope check); a step that
    depends on or references any dropped step is dropped too."""
    kept: list[DraftAction] = []
    missing: list[Missing] = []
    dropped: list[Dropped] = []
    for position, item in enumerate(raw_actions, start=1):
        if pre_dropped and position in pre_dropped:
            dropped.append(pre_dropped[position])
            continue
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            dropped.append(Dropped(position, "invalid_action"))
            continue
        action = resolve(item["type"])
        if action is None:
            dropped.append(Dropped(position, "unknown_action_type"))
            continue
        if not action.available:
            dropped.append(Dropped(position, "not_available", action.unavailable_reason or action.label))
            continue
        if not role_allows(ctx.actor_role, action.min_role):
            dropped.append(Dropped(position, "forbidden_for_role", action.label))
            continue
        raw_params = item.get("params") if isinstance(item.get("params"), dict) else {}
        depends = [d for d in item.get("depends_on") or [] if isinstance(d, int)]
        refs = _refs(raw_params)
        if any(n >= position or n < 1 for n, _ in refs):
            dropped.append(Dropped(position, "bad_reference", action.label))
            continue
        depends = sorted({*depends, *(n for n, _ in refs)} - {position})
        if {d.index for d in dropped} & set(depends):
            dropped.append(Dropped(position, "depends_on_dropped", action.label))
            continue
        try:
            params = action.params.model_validate(raw_params)
        except ValidationError as exc:
            seen: set[str] = set()
            for err in exc.errors():
                path = ".".join(str(p) for p in err["loc"] if not isinstance(p, int)) or "params"
                if path in seen:
                    continue
                seen.add(path)
                missing.append(Missing(position, path, question_for(action.label, path)))
            continue
        draft = DraftAction(
            index=position,
            type=action.type,
            params=params.model_dump(mode="json", exclude_none=True),
            description=(str(item.get("description") or action.label).strip()[:300]),
            depends_on=depends,
            module=action.module,
            risk=action.risk,
            label=action.label,
            cost_estimate_cents=_cost(action, params),
        )
        if extra_checks:
            for path, question in extra_checks(ctx, draft, params):
                missing.append(Missing(position, path, question))
        kept.append(draft)
    return kept, missing, dropped


def structural_problems(raw_actions: Any) -> list[str]:
    """Problems worth one more planner call (SPEC-BE-085 FR8): malformed steps,
    unknown action types and references to later steps. Missing values are not
    here: those are asked from the user."""
    if not isinstance(raw_actions, list):
        return ["\"actions\" must be a list."]
    problems: list[str] = []
    for position, item in enumerate(raw_actions, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            problems.append(f"Step {position} is not an object with a \"type\".")
            continue
        if resolve(item["type"]) is None:
            problems.append(f"Step {position}: “{item['type']}” is not an allowed action type.")
            continue
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        if any(n >= position or n < 1 for n, _ in _refs(params)):
            problems.append(f"Step {position} refers to a step that isn't before it.")
    return problems


def registry_prompt() -> str:
    """Compact action catalog for the system prompt."""
    lines = []
    for a in REGISTRY.values():
        if not a.available:
            continue
        schema = a.params.model_json_schema()
        props = {k: {kk: vv for kk, vv in v.items() if kk in ("type", "enum", "anyOf", "items", "maximum", "minimum", "pattern", "$ref")} for k, v in schema.get("properties", {}).items()}
        required = schema.get("required", [])
        lines.append(json.dumps({"type": a.type, "does": a.hint, "risk": a.risk, "required": required, "params": props}, separators=(",", ":")))
    return "\n".join(lines)


def parse_llm_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(match.group(0) if match else text)
    except (json.JSONDecodeError, TypeError):
        from app.ai.llm_client import LLMProviderError

        raise LLMProviderError("LLM returned an unparseable plan.") from None
    if not isinstance(data, dict):
        from app.ai.llm_client import LLMProviderError

        raise LLMProviderError("LLM returned an unparseable plan.")
    return data


def resolve_refs(params: Any, outputs: dict[int, dict[str, Any]]) -> Any:
    """Replaces "$n.field" with action n's output value; a missing value raises."""
    if isinstance(params, str):
        m = REF_RE.match(params)
        if not m:
            return params
        n, key = int(m.group(1)), m.group(2)
        value = (outputs.get(n) or {}).get(key)
        if value in (None, "", []):
            raise AppError(f"Step {n} didn't produce {key}.", 409)
        if isinstance(value, list):
            return [str(v) for v in value]  # e.g. $1.content_ids (SPEC-BE-078)
        return str(value)
    if isinstance(params, dict):
        return {k: resolve_refs(v, outputs) for k, v in params.items()}
    if isinstance(params, list):
        return [resolve_refs(v, outputs) for v in params]
    return params


def execute(ctx: ExecContext, action_type: str, params: dict[str, Any]) -> dict[str, Any]:
    action = resolve(action_type)
    if action is None or action.executor is None:
        raise AppError(f"Action {action_type} can't be executed.", 422)
    model = action.params.model_validate(params)
    return action.executor(ctx, model)


def effective_risk(ctx: ExecContext, draft: DraftAction, drafts: dict[int, DraftAction]) -> Risk:
    action = REGISTRY[draft.type]
    if action.type == "enable_workflow":
        ref = REF_RE.match(str(draft.params.get("workflow_id", "")))
        if ref and int(ref.group(1)) in drafts:
            steps = drafts[int(ref.group(1))].params.get("actions") or []
            return "spend" if {s.get("type") for s in steps} & _SPEND_WORKFLOW_ACTIONS else "change"
    if action.risk_fn is not None:
        return action.risk_fn(ctx, action.params.model_validate(draft.params))
    return action.risk
