"""Connected social accounts (SPEC-BE-075) and their sign-in (SPEC-BE-080)."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import social as s
from app.services import social_account_service as svc
from app.services import social_oauth_service as oauth

router = APIRouter(tags=["social"])
Manager = Depends(require_permission("manager"))


@router.get("/social/accounts", response_model=s.SocialAccountList, status_code=status.HTTP_200_OK)
def list_accounts(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.list_accounts(db, str(user.tenant_id))


@router.post("/social/accounts/use-meta", response_model=s.UseMetaResult, status_code=status.HTTP_200_OK)
def use_meta(db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.use_meta_connection(db, str(user.tenant_id), str(user.id))


@router.get("/social/oauth/{flow}/connect", response_model=s.OAuthConnectUrl, status_code=status.HTTP_200_OK)
def oauth_connect(flow: s.SocialFlow, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return oauth.connect_url(db, str(user.tenant_id), str(user.id), flow)


@router.post("/social/oauth/{flow}/callback", response_model=s.OAuthCallbackResult, status_code=status.HTTP_200_OK)
def oauth_callback(flow: s.SocialFlow, payload: s.OAuthCallback, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return oauth.callback(db, str(user.tenant_id), str(user.id), flow, payload.code, payload.state)


@router.post("/social/oauth/{flow}/select", response_model=s.OAuthSelectResult, status_code=status.HTTP_200_OK)
def oauth_select(flow: s.SocialFlow, payload: s.OAuthSelect, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return oauth.select(db, str(user.tenant_id), str(user.id), flow, payload.account_id, payload.include_instagram)
