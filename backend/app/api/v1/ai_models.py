"""/ai-models endpoints (SPEC-BE-053). SPEC-BE-101: the keys, models and order
are PilotSonic's (the Super admin manages them under /platform/ai-models); a
company reads them here, and the routes that managed keys answer 409. The
company's own creative order and slideshow sound settings stay here."""
from typing import Any

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.ai_model import (
    VideoAudioSave,
    VideoAudioSettings,
    MCP_ID,
    AIModelList,
    AIModelOrder,
    AIModelTestResult,
    AIModelUpdate,
    CreativeOrder,
    CreativeSettings,
    MCPToolSave,
    MCPToolTest,
    ProviderModels,
    ProviderName,
)
from app.services import ai_model_service

router = APIRouter(prefix="/ai-models", tags=["ai-models"])


@router.get("", response_model=AIModelList, status_code=status.HTTP_200_OK)
def list_ai_models(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return ai_model_service.list_providers(db, str(current_user.tenant_id))


# /order is declared before /{provider}.
@router.put("/order", response_model=AIModelList, status_code=status.HTTP_200_OK)
def set_ai_model_order(
    payload: AIModelOrder,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    raise ConflictError(ai_model_service.PROVIDED)  # SPEC-BE-101: keys are PilotSonic's


# --- Sound for AI slideshow videos (SPEC-BE-094), before /{provider} ---
@router.get("/video-audio", response_model=VideoAudioSettings, status_code=status.HTTP_200_OK)
def get_video_audio(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return ai_model_service.video_audio(db, str(current_user.tenant_id))


@router.put("/video-audio", response_model=VideoAudioSettings, status_code=status.HTTP_200_OK)
def put_video_audio(payload: VideoAudioSave, db: Session = Depends(get_db),
                    current_user: User = Depends(require_permission("manager"))) -> dict[str, Any]:
    return ai_model_service.set_video_audio(db, str(current_user.tenant_id), str(current_user.id), payload)


# --- Creative providers + MCP creative tools (SPEC-BE-070), before /{provider} ---
@router.get("/creative", response_model=CreativeSettings, status_code=status.HTTP_200_OK)
def get_creative(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return ai_model_service.creative_settings(db, str(current_user.tenant_id))


@router.put("/creative", response_model=CreativeSettings, status_code=status.HTTP_200_OK)
def put_creative(payload: CreativeOrder, db: Session = Depends(get_db), current_user: User = Depends(require_permission("manager"))) -> dict[str, Any]:
    return ai_model_service.set_creative_order(db, str(current_user.tenant_id), str(current_user.id), {str(k): v for k, v in payload.order.items()})


@router.put("/mcp/{tool_id}", response_model=CreativeSettings, status_code=status.HTTP_200_OK)
def put_mcp_tool(
    payload: MCPToolSave, tool_id: str = Path(pattern=MCP_ID), db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    raise ConflictError(ai_model_service.PROVIDED)  # SPEC-BE-101: keys are PilotSonic's


@router.delete("/mcp/{tool_id}", response_model=CreativeSettings, status_code=status.HTTP_200_OK)
def delete_mcp_tool(tool_id: str = Path(pattern=MCP_ID), db: Session = Depends(get_db), current_user: User = Depends(require_permission("manager"))) -> dict[str, Any]:
    raise ConflictError(ai_model_service.PROVIDED)  # SPEC-BE-101: keys are PilotSonic's


@router.post("/mcp/{tool_id}/test", response_model=MCPToolTest, status_code=status.HTTP_200_OK)
def test_mcp_tool(tool_id: str = Path(pattern=MCP_ID), db: Session = Depends(get_db), current_user: User = Depends(require_permission("manager"))) -> dict[str, Any]:
    raise ConflictError(ai_model_service.PROVIDED)  # SPEC-BE-101: keys are PilotSonic's


@router.put("/{provider}", response_model=AIModelList, status_code=status.HTTP_200_OK)
def update_ai_model(
    provider: ProviderName,
    payload: AIModelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    raise ConflictError(ai_model_service.PROVIDED)  # SPEC-BE-101: keys are PilotSonic's


@router.get("/{provider}/models", response_model=ProviderModels, status_code=status.HTTP_200_OK)
def list_provider_models(
    provider: ProviderName,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    raise ConflictError(ai_model_service.PROVIDED)  # SPEC-BE-101: keys are PilotSonic's


@router.post("/{provider}/test", response_model=AIModelTestResult, status_code=status.HTTP_200_OK)
def test_ai_model(
    provider: ProviderName,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    raise ConflictError(ai_model_service.PROVIDED)  # SPEC-BE-101: keys are PilotSonic's


@router.delete("/{provider}", response_model=AIModelList, status_code=status.HTTP_200_OK)
def delete_ai_model_key(
    provider: ProviderName,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    raise ConflictError(ai_model_service.PROVIDED)  # SPEC-BE-101: keys are PilotSonic's
