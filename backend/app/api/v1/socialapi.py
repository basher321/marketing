"""SocialAPI.ai routes (SPEC-BE-083): another way to post and answer on social
media, next to the direct integrations (unchanged).

Roles: viewer+ reads; agent+ answers the inbox (messages, comment and review
replies, AI drafts) as in Customer Service; manager+ manages the key and the
accounts, and creates / publishes / deletes posts, as in Organic Marketing.
"""
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import socialapi as s
from app.services import socialapi_service as svc

router = APIRouter(prefix="/socialapi", tags=["socialapi"])
Viewer = Depends(get_current_user)
Agent = Depends(require_permission("agent"))
Manager = Depends(require_permission("manager"))
# SocialAPI ids (acc_â€¦, sapi_cmt_â€¦, platform post ids) - no slashes or spaces.
IdStr = Annotated[str, Path(min_length=1, max_length=300, pattern=r"^[A-Za-z0-9_.:=\-]+$")]
Cursor = Query(default=None, max_length=2000)
PlatformQ = Query(default=None, max_length=40, pattern=r"^[a-z]+$")


def _t(user: User) -> str:
    return str(user.tenant_id)


# --- Key ----------------------------------------------------------------------
@router.get("/key", response_model=s.KeyStatus, status_code=status.HTTP_200_OK)
def key_status(db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.key_status(db, _t(user))


@router.put("/key", response_model=s.KeyStatus, status_code=status.HTTP_200_OK)
def save_key(payload: s.KeyUpdate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.save_key(db, _t(user), str(user.id), payload.api_key)


@router.post("/key/test", response_model=s.KeyStatus, status_code=status.HTTP_200_OK)
def test_key(db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.test_key(db, _t(user), str(user.id))


@router.delete("/key", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_key(db: Session = Depends(get_db), user: User = Manager) -> Response:
    svc.delete_key(db, _t(user), str(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Accounts -----------------------------------------------------------------
@router.get("/accounts", response_model=s.AccountList, status_code=status.HTTP_200_OK)
def list_accounts(db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.list_accounts(db, _t(user))


@router.post("/accounts/connect", response_model=s.ConnectResult, status_code=status.HTTP_200_OK)
def connect(payload: s.ConnectRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.connect(db, _t(user), str(user.id), payload.platform)


@router.post("/accounts/callback", response_model=s.CallbackResult, status_code=status.HTTP_200_OK)
def callback(payload: s.CallbackRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.callback(db, _t(user), str(user.id), payload)


@router.post("/accounts/select", response_model=s.SelectResult, status_code=status.HTTP_200_OK)
def select(payload: s.SelectRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.select(db, _t(user), str(user.id), payload)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def disconnect(account_id: IdStr, db: Session = Depends(get_db), user: User = Manager) -> Response:
    svc.disconnect(db, _t(user), str(user.id), account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/accounts/{account_id}/boards", response_model=s.BoardList, status_code=status.HTTP_200_OK)
def boards(account_id: IdStr, db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.boards(db, _t(user), account_id)


@router.get("/accounts/{account_id}/facebook-pages", response_model=s.ChoiceList, status_code=status.HTTP_200_OK)
def facebook_pages(account_id: IdStr, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.facebook_pages(db, _t(user), account_id)


@router.post("/accounts/{account_id}/facebook-page", response_model=s.SelectResult, status_code=status.HTTP_200_OK)
def choose_facebook_page(payload: s.FacebookPageRequest, account_id: IdStr, db: Session = Depends(get_db),
                         user: User = Manager) -> dict[str, Any]:
    return svc.choose_facebook_page(db, _t(user), str(user.id), account_id, payload.page_id)


@router.get("/accounts/{account_id}/analytics", response_model=s.AccountAnalytics, status_code=status.HTTP_200_OK)
def account_analytics(account_id: IdStr, range_: Literal["7d", "30d", "90d"] = Query(default="30d", alias="range"),
                      db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.account_analytics(db, _t(user), account_id, int(range_.removesuffix("d")))


# --- Posts --------------------------------------------------------------------
@router.get("/constraints", response_model=s.ConstraintList, status_code=status.HTTP_200_OK)
def constraints(db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.constraints(db, _t(user))


@router.get("/posts", response_model=s.PostList, status_code=status.HTTP_200_OK)
def list_posts(
    status_: str | None = Query(default=None, alias="status",
                                pattern="^(draft|scheduled|publishing|published|partial|failed|cancelled)$"),
    platform: str | None = PlatformQ,
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = Cursor,
    db: Session = Depends(get_db),
    user: User = Viewer,
) -> dict[str, Any]:
    return svc.list_posts(db, _t(user), status_, platform, q, cursor)


@router.post("/posts", response_model=s.Post, status_code=status.HTTP_201_CREATED)
def create_post(payload: s.PostCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.create_post(db, _t(user), str(user.id), payload)


@router.get("/posts/{post_id}", response_model=s.Post, status_code=status.HTTP_200_OK)
def get_post(post_id: IdStr, db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.get_post(db, _t(user), post_id)


@router.post("/posts/{post_id}/publish", response_model=s.Post, status_code=status.HTTP_200_OK)
def publish_post(post_id: IdStr, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.publish_post(db, _t(user), str(user.id), post_id)


@router.post("/posts/{post_id}/retry", response_model=s.Post, status_code=status.HTTP_200_OK)
def retry_post(post_id: IdStr, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.retry_post(db, _t(user), str(user.id), post_id)


@router.delete("/posts/{post_id}", response_model=s.DeleteResult, status_code=status.HTTP_200_OK)
def delete_post(post_id: IdStr, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.delete_post(db, _t(user), str(user.id), post_id)


# --- Inbox --------------------------------------------------------------------
@router.get("/inbox/conversations", response_model=s.ConversationList, status_code=status.HTTP_200_OK)
def conversations(
    platform: str | None = PlatformQ,
    account_id: str | None = Query(default=None, max_length=200),
    status_: str | None = Query(default=None, alias="status", pattern="^(active|archived)$"),
    cursor: str | None = Cursor,
    db: Session = Depends(get_db),
    user: User = Viewer,
) -> dict[str, Any]:
    return svc.conversations(db, _t(user), platform, account_id, status_, cursor)


@router.get("/inbox/conversations/{conversation_id}/messages", response_model=s.MessageList, status_code=status.HTTP_200_OK)
def messages(conversation_id: IdStr, cursor: str | None = Cursor, db: Session = Depends(get_db),
             user: User = Viewer) -> dict[str, Any]:
    return svc.messages(db, _t(user), conversation_id, cursor)


@router.post("/inbox/conversations/{conversation_id}/messages", response_model=s.ActionResult, status_code=status.HTTP_201_CREATED)
def send_message(payload: s.SendMessage, conversation_id: IdStr, db: Session = Depends(get_db),
                 user: User = Agent) -> dict[str, Any]:
    return svc.send_message(db, _t(user), str(user.id), conversation_id, payload)


@router.get("/inbox/comments", response_model=s.CommentedPostList, status_code=status.HTTP_200_OK)
def commented_posts(
    platform: str | None = PlatformQ,
    account_id: str | None = Query(default=None, max_length=200),
    cursor: str | None = Cursor,
    db: Session = Depends(get_db),
    user: User = Viewer,
) -> dict[str, Any]:
    return svc.commented_posts(db, _t(user), platform, account_id, cursor)


@router.get("/inbox/comments/{post_id}", response_model=s.CommentList, status_code=status.HTTP_200_OK)
def comments(post_id: IdStr, account_id: str = Query(min_length=1, max_length=200), cursor: str | None = Cursor,
             db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.comments(db, _t(user), post_id, account_id, cursor)


@router.post("/inbox/comments/{post_id}/reply", response_model=s.ActionResult, status_code=status.HTTP_201_CREATED)
def reply_comment(payload: s.CommentReply, post_id: IdStr, db: Session = Depends(get_db),
                  user: User = Agent) -> dict[str, Any]:
    return svc.reply_comment(db, _t(user), str(user.id), post_id, payload)


@router.post("/inbox/comments/{post_id}/{comment_id}/moderate", response_model=s.ActionResult, status_code=status.HTTP_200_OK)
def moderate_comment(payload: s.CommentAction, post_id: IdStr, comment_id: IdStr, db: Session = Depends(get_db),
                     user: User = Agent) -> dict[str, Any]:
    return svc.moderate_comment(db, _t(user), str(user.id), post_id, comment_id, payload)


@router.get("/inbox/reviews/{account_id}", response_model=s.ReviewList, status_code=status.HTTP_200_OK)
def reviews(account_id: IdStr, cursor: str | None = Cursor, db: Session = Depends(get_db),
            user: User = Viewer) -> dict[str, Any]:
    return svc.reviews(db, _t(user), account_id, cursor)


@router.post("/inbox/reviews/{review_id}/reply", response_model=s.ActionResult, status_code=status.HTTP_201_CREATED)
def reply_review(payload: s.ReviewReply, review_id: IdStr, db: Session = Depends(get_db),
                 user: User = Agent) -> dict[str, Any]:
    return svc.reply_review(db, _t(user), str(user.id), review_id, payload)


@router.post("/inbox/draft-reply", response_model=s.DraftResult, status_code=status.HTTP_200_OK)
def draft_reply(payload: s.DraftRequest, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.draft_reply(db, _t(user), payload)
