"""/ai-models endpoints: per-company LLM keys and fallback order (SPEC-BE-053)."""
from typing import Any

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.ai_model import (
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
    return ai_model_service.set_order(db, str(current_user.tenant_id), str(current_user.id), list(payload.order))


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
    return ai_model_service.save_mcp_tool(db, str(current_user.tenant_id), str(current_user.id), tool_id, payload)


@router.delete("/mcp/{tool_id}", response_model=CreativeSettings, status_code=status.HTTP_200_OK)
def delete_mcp_tool(tool_id: str = Path(pattern=MCP_ID), db: Session = Depends(get_db), current_user: User = Depends(require_permission("manager"))) -> dict[str, Any]:
    return ai_model_service.delete_mcp_tool(db, str(current_user.tenant_id), str(current_user.id), tool_id)


@router.post("/mcp/{tool_id}/test", response_model=MCPToolTest, status_code=status.HTTP_200_OK)
def test_mcp_tool(tool_id: str = Path(pattern=MCP_ID), db: Session = Depends(get_db), current_user: User = Depends(require_permission("manager"))) -> dict[str, Any]:
    return ai_model_service.test_mcp_tool(db, str(current_user.tenant_id), str(current_user.id), tool_id)


@router.put("/{provider}", response_model=AIModelList, status_code=status.HTTP_200_OK)
def update_ai_model(
    provider: ProviderName,
    payload: AIModelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ai_model_service.update_provider(db, str(current_user.tenant_id), str(current_user.id), provider, payload)


@router.get("/{provider}/models", response_model=ProviderModels, status_code=status.HTTP_200_OK)
def list_provider_models(
    provider: ProviderName,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ai_model_service.list_models(db, str(current_user.tenant_id), provider)


@router.post("/{provider}/test", response_model=AIModelTestResult, status_code=status.HTTP_200_OK)
def test_ai_model(
    provider: ProviderName,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ai_model_service.test_provider(db, str(current_user.tenant_id), str(current_user.id), provider)


@router.delete("/{provider}", response_model=AIModelList, status_code=status.HTTP_200_OK)
def delete_ai_model_key(
    provider: ProviderName,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ai_model_service.delete_key(db, str(current_user.tenant_id), str(current_user.id), provider)
