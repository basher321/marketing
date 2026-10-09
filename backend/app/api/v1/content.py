"""/content/generate endpoints."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.content import (
    ContentGenerateRequest,
    ContentGenerateResponse,
    CreativeAssetRead,
    CreativeGenerateRequest,
    CreativeManualCreate,
    VariantEditRequest,
    VariantSelectRequest,
)
from app.services import content_service

router = APIRouter(prefix="/content", tags=["content"])


@router.post("/generate", response_model=ContentGenerateResponse)
# SPEC-BE-071 F5: legacy AI text generation spends AI credits -> manager and up.
def generate(
    payload: ContentGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
):
    text = content_service.generate_content(db, str(current_user.tenant_id), payload.prompt)
    return ContentGenerateResponse(content=text)


# Campaign Wizard creative variants (SPEC-BE-030). Generate and select are
# manager+; get is any authenticated user of the tenant. No image generation,
# edit, or campaign-launch endpoint.
@router.post("/creatives", response_model=CreativeAssetRead, status_code=201)
def generate_creatives(
    payload: CreativeGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> CreativeAssetRead:
    return CreativeAssetRead.model_validate(
        content_service.generate_creative_asset(
            db,
            current_user.tenant_id,
            current_user.id,
            payload.objective,
            payload.skus,
            payload.brief,
            payload.channel,
            str(payload.campaign_id) if payload.campaign_id else None,
            payload.title,
        )
    )


# Hand-written creative (SPEC-BE-046); declared before /creatives/{asset_id}.
@router.post("/creatives/manual", response_model=CreativeAssetRead, status_code=201)
def create_manual_creative(
    payload: CreativeManualCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> CreativeAssetRead:
    return CreativeAssetRead.model_validate(
        content_service.create_manual_creative(
            db,
            current_user.tenant_id,
            current_user.id,
            payload.channel,
            [v.model_dump() for v in payload.variants],
            str(payload.campaign_id) if payload.campaign_id else None,
            payload.title,
        )
    )


@router.patch(
    "/creatives/{asset_id}/variants/{index}", response_model=CreativeAssetRead, status_code=200
)
def edit_creative_variant(
    asset_id: uuid.UUID,
    index: int,
    payload: VariantEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> CreativeAssetRead:
    return CreativeAssetRead.model_validate(
        content_service.edit_variant(
            db,
            current_user.tenant_id,
            current_user.id,
            str(asset_id),
            index,
            payload.headline,
            payload.description,
        )
    )


@router.get("/creatives/{asset_id}", response_model=CreativeAssetRead, status_code=200)
def get_creatives(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CreativeAssetRead:
    return CreativeAssetRead.model_validate(
        content_service.get_creative_asset(db, current_user.tenant_id, str(asset_id))
    )


@router.post("/creatives/{asset_id}/select", response_model=CreativeAssetRead, status_code=200)
def select_creative_variant(
    asset_id: uuid.UUID,
    payload: VariantSelectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> CreativeAssetRead:
    return CreativeAssetRead.model_validate(
        content_service.select_variant(
            db, current_user.tenant_id, current_user.id, str(asset_id), payload.variant_index
        )
    )
