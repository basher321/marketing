"""Master v1 router aggregating all routes."""
from fastapi import APIRouter

from app.api.v1 import (
    ads,
    ai_models,
    analytics,
    approvals,
    audiences,
    auth,
    brand,
    campaigns,
    content,
    conversations,
    customers,
    faqs,
    integrations,
    inventory,
    kb,
    generation,
    media,
    organic,
    paid,
    social,
    socialapi,
    ads_builder,
    ai_campaigns,
    meta,
    orchestrator,
    orders,
    policies,
    pricing,
    products,
    scheduled_posts,
    shipping,
    tenants,
    users,
    webhooks,
    workflows,
    zernio,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(users.router)
api_router.include_router(orchestrator.router)
api_router.include_router(products.router)
api_router.include_router(inventory.router)
api_router.include_router(pricing.router)
api_router.include_router(shipping.router)
api_router.include_router(orders.router)
api_router.include_router(customers.router)
api_router.include_router(conversations.router)
api_router.include_router(faqs.router)
api_router.include_router(policies.router)
api_router.include_router(brand.router)
api_router.include_router(kb.router)
api_router.include_router(campaigns.router)
api_router.include_router(audiences.router)
api_router.include_router(content.router)
api_router.include_router(scheduled_posts.router)
api_router.include_router(media.router)
api_router.include_router(social.router)
api_router.include_router(socialapi.router)  # SPEC-BE-083
api_router.include_router(organic.router)
api_router.include_router(generation.router)
api_router.include_router(ads.router)
api_router.include_router(meta.router)
api_router.include_router(ads_builder.router)
api_router.include_router(paid.router)
api_router.include_router(ai_campaigns.router)
api_router.include_router(zernio.router)  # SPEC-BE-084
api_router.include_router(analytics.router)
api_router.include_router(workflows.router)
api_router.include_router(approvals.router)
api_router.include_router(integrations.router)
api_router.include_router(ai_models.router)
api_router.include_router(webhooks.router)
