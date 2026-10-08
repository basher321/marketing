"""Content generation orchestration."""
from collections.abc import Sequence
from dataclasses import asdict
from datetime import timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.ai.llm_client import llm_client
from app.ai.prompts.content_generator import build_content_prompt, generate_creative_variants
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.campaign import Campaign
from app.models.content import ContentAsset

logger = structlog.get_logger(__name__)

# content_assets.format for generated text ad creative (SPEC-BE-030).
CREATIVE_FORMAT = "ad_text"


def generate_content(brief: str, tone: str = "friendly", voice_guidelines: str = "") -> str:
    prompt = build_content_prompt(brief, tone, voice_guidelines)
    return llm_client.complete("You are a marketing copywriter.", prompt)


# Campaign Wizard creative variants (SPEC-BE-030). Generation is SPEC-BE-029's
# generate_creative_variants(), called as-is - no retrieval, LLM or moderation
# logic lives here, and its llm_call span (with token counts) is not re-logged.
# One generate call persists one content_assets row holding all variants in
# its `variants` JSONB array ([{"headline", "description"}], exactly as
# SPEC-BE-029 returned them); selected_variant_index stays NULL until a variant
# is selected. Every query filters by tenant_id; another tenant's asset or
# campaign is indistinguishable from a missing one (404).
def _asset_payload(asset: ContentAsset) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "campaign_id": str(asset.campaign_id) if asset.campaign_id else None,
        "title": asset.title,
        "channel": asset.channel,
        "format": asset.format,
        "status": asset.status,
        "variants": [
            {"index": i, "headline": v.get("headline", ""), "description": v.get("description", "")}
            for i, v in enumerate(asset.variants or [])
        ],
        "selected_variant_index": asset.selected_variant_index,
        "generated_by_model": asset.generated_by_model,
        "created_at": asset.created_at.astimezone(timezone.utc),
    }


def _require_asset(
    db: Session, tenant_id: str, asset_id: str, lock: bool = False
) -> ContentAsset:
    query = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.tenant_id == tenant_id
    )
    if lock:
        query = query.with_for_update()
    asset = query.first()
    if asset is None:
        raise NotFoundError("Content asset not found.")
    return asset


def generate_creative_asset(
    db: Session,
    tenant_id: str,
    user_id: str,
    objective: str,
    skus: Sequence[str],
    brief: str,
    channel: str,
    campaign_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    if campaign_id is not None:
        # campaign_id has no FK in the live table, so it is checked here.
        # Column-level query: the Campaign model maps columns the live table
        # lacks.
        found = (
            db.query(Campaign.id)
            .filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
            .first()
        )
        if found is None:
            raise NotFoundError("Campaign not found.")

    # SPEC-BE-029's typed errors (LLMProviderError 503, CreativeRejectedError
    # 422, input AppError 422) propagate unchanged; nothing is written before
    # generation succeeds.
    result = generate_creative_variants(db, tenant_id, objective, skus, brief)

    asset = ContentAsset(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        title=title,
        channel=channel,
        format=CREATIVE_FORMAT,
        variants=[asdict(variant) for variant in result.variants],
        selected_variant_index=None,
        status="draft",
        generated_by_model=result.model,
        moderation_status="passed",
        moderation_details={
            "moderation_rejections": result.moderation_rejections,
            "discarded": result.discarded,
            "regeneration_rounds": result.regeneration_rounds,
        },
        extra_metadata={
            "objective": objective,
            "skus": result.products,
            "brief": brief,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        },
    )
    db.add(asset)
    db.flush()
    asset_id = str(asset.id)
    # write_audit_log commits: the row and its audit entry land together.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        action="content.creative_generated",
        resource_type="content_asset",
        resource_id=asset_id,
        metadata={"campaign_id": campaign_id, "variant_count": len(result.variants)},
    )
    logger.info(
        "creative_asset_persisted",
        tenant_id=tenant_id,
        asset_id=asset_id,
        variants=len(result.variants),
    )
    return get_creative_asset(db, tenant_id, asset_id)


def get_creative_asset(db: Session, tenant_id: str, asset_id: str) -> dict[str, Any]:
    return _asset_payload(_require_asset(db, tenant_id, asset_id))


def select_variant(
    db: Session, tenant_id: str, user_id: str, asset_id: str, variant_index: int
) -> dict[str, Any]:
    # No variants yet -> 409; index outside 0..len-1 -> 422. Both reject
    # before anything is written. Re-selecting the current index is still an
    # action and is audited.
    asset = _require_asset(db, tenant_id, asset_id, lock=True)
    count = len(asset.variants or [])
    if count == 0:
        raise ConflictError("This content asset has no variants to select.")
    if not 0 <= variant_index < count:
        raise AppError(f"variant_index out of range (0-{count - 1}).", 422)
    previous = asset.selected_variant_index
    asset.selected_variant_index = variant_index
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        action="content.variant_selected",
        resource_type="content_asset",
        resource_id=asset_id,
        metadata={"previous_index": previous, "variant_index": variant_index},
    )
    logger.info(
        "creative_variant_selected", tenant_id=tenant_id, asset_id=asset_id, index=variant_index
    )
    return get_creative_asset(db, tenant_id, asset_id)


# Hand-written creatives and variant edits (SPEC-BE-046). They work without an
# LLM provider (LLM_PROVIDER=mock makes generation answer 503). A manual asset
# is marked metadata.source = "manual", has no generated_by_model, and starts
# with variant 0 selected. No LLM moderation runs on hand-written copy.
def create_manual_creative(
    db: Session,
    tenant_id: str,
    user_id: str,
    channel: str,
    variants: Sequence[dict[str, str]],
    campaign_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    if campaign_id is not None:
        # campaign_id has no FK in the live table, so it is checked here.
        found = (
            db.query(Campaign.id)
            .filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
            .first()
        )
        if found is None:
            raise AppError("Unknown campaign.", 422)
    asset = ContentAsset(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        title=title,
        channel=channel,
        format=CREATIVE_FORMAT,
        variants=[{"headline": v["headline"], "description": v["description"]} for v in variants],
        selected_variant_index=0,
        status="draft",
        generated_by_model=None,
        extra_metadata={"source": "manual"},
    )
    db.add(asset)
    db.flush()
    asset_id = str(asset.id)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        action="content.creative_manual",
        resource_type="content_asset",
        resource_id=asset_id,
        metadata={"campaign_id": campaign_id, "variant_count": len(variants)},
    )
    logger.info("creative_manual_created", tenant_id=tenant_id, asset_id=asset_id)
    return get_creative_asset(db, tenant_id, asset_id)


def edit_variant(
    db: Session,
    tenant_id: str,
    user_id: str,
    asset_id: str,
    index: int,
    headline: str | None,
    description: str | None,
) -> dict[str, Any]:
    # Replaces one variant's text; the selection is unchanged. Edited indexes
    # are recorded so a human-edited AI variant stays traceable.
    asset = _require_asset(db, tenant_id, asset_id, lock=True)
    variants = [dict(v) for v in (asset.variants or [])]
    if not 0 <= index < len(variants):
        raise NotFoundError("Variant not found.")
    before = dict(variants[index])
    if headline is not None:
        variants[index]["headline"] = headline
    if description is not None:
        variants[index]["description"] = description
    asset.variants = variants
    meta = dict(asset.extra_metadata or {})
    meta["edited_indexes"] = sorted(set(meta.get("edited_indexes") or []) | {index})
    asset.extra_metadata = meta
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        action="content.variant_edit",
        resource_type="content_asset",
        resource_id=asset_id,
        metadata={"index": index, "before": before, "after": variants[index]},
    )
    logger.info("creative_variant_edited", tenant_id=tenant_id, asset_id=asset_id, index=index)
    return get_creative_asset(db, tenant_id, asset_id)
