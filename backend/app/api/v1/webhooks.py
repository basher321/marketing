"""/webhooks/{provider} inbound webhook receivers.

SPEC-BE-071 F10: a provider is enabled only together with its signature check;
every other provider answers 404 instead of accepting unauthenticated data.
- Twilio SMS (SPEC-BE-108): `X-Twilio-Signature`, form-encoded; answers TwiML.
- WhatsApp Cloud API (SPEC-BE-112): GET verify challenge with the Super admin's verify
  token; POST signed with the Meta app secret (`X-Hub-Signature-256`).

Every valid event is stored in `webhook_events`; a repeated event id is a no-op.
"""
import json

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations import twilio_sms, whatsapp_cloud
from app.services import inbox_service, platform_service, sms_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response/>'


def _twiml() -> Response:
    return Response(content=_TWIML, media_type="text/xml", status_code=200)


async def _twilio_params(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: str(v) for k, v in form.items()}


def _verified(request: Request, kind: str, params: dict[str, str], db: Session) -> bool:
    _, token = sms_service.credentials(db)
    given = request.headers.get("X-Twilio-Signature")
    return twilio_sms.valid_signature(token, sms_service.webhook_urls(kind, str(request.url)), params, given)


@router.post("/twilio/status", response_model=None, status_code=status.HTTP_200_OK)
async def twilio_status(request: Request, db: Session = Depends(get_db)) -> Response:
    params = await _twilio_params(request)
    sid = params.get("MessageSid") or params.get("SmsSid")
    state = params.get("MessageStatus") or params.get("SmsStatus")
    event_id = f"{sid}:{state}" if sid and state else None
    if not _verified(request, "status", params, db):
        sms_service.record_event(db, None, "status", None, params, request.headers.get("X-Twilio-Signature"), False)
        db.commit()
        return JSONResponse(status_code=403, content={"error": "Invalid signature."})
    if sms_service.record_event(db, None, "status", event_id, params, request.headers.get("X-Twilio-Signature"), True):
        sms_service.handle_status(db, params)
        sms_service.mark_processed(db, "twilio", event_id)
    db.commit()
    return _twiml()


@router.post("/twilio/inbound", response_model=None, status_code=status.HTTP_200_OK)
async def twilio_inbound(request: Request, db: Session = Depends(get_db)) -> Response:
    params = await _twilio_params(request)
    sid = params.get("MessageSid") or params.get("SmsSid")
    if not _verified(request, "inbound", params, db):
        sms_service.record_event(db, None, "inbound", None, params, request.headers.get("X-Twilio-Signature"), False)
        db.commit()
        return JSONResponse(status_code=403, content={"error": "Invalid signature."})
    tenant = sms_service.owner_of(db, params.get("To"))
    tenant_id = str(tenant.id) if tenant else None
    if sms_service.record_event(db, tenant_id, "inbound", sid, params, request.headers.get("X-Twilio-Signature"), True):
        error = None if tenant else "No company owns this number."
        if tenant is not None:
            sms_service.handle_inbound(db, tenant, params)
        sms_service.mark_processed(db, "twilio", sid, error)
    db.commit()
    return _twiml()


@router.get("/whatsapp", response_model=None, status_code=status.HTTP_200_OK)
def whatsapp_verify(
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge", max_length=200),
    db: Session = Depends(get_db),
) -> Response:
    expected = platform_service.value("whatsapp_app", "verify_token", db)
    if mode == "subscribe" and expected and token == expected and challenge:
        return PlainTextResponse(challenge)
    return JSONResponse(status_code=403, content={"error": "Verification failed."})


@router.post("/whatsapp", response_model=None, status_code=status.HTTP_200_OK)
async def whatsapp_events(request: Request, db: Session = Depends(get_db)) -> Response:
    body = await request.body()
    secret = platform_service.value("meta_app", "app_secret", db)
    signature = request.headers.get("X-Hub-Signature-256")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        payload = {}
    if not whatsapp_cloud.valid_signature(secret, body, signature):
        sms_service.record_event(db, None, "invalid_signature", None, payload if isinstance(payload, dict) else {},
                                 signature, False, provider="whatsapp")
        db.commit()
        return JSONResponse(status_code=403, content={"error": "Invalid signature."})
    if isinstance(payload, dict):
        inbox_service.handle_wa_webhook(db, payload)
    db.commit()
    return JSONResponse(status_code=200, content={"ok": True})


@router.post("/{provider}", status_code=status.HTTP_404_NOT_FOUND)
async def receive_webhook(provider: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "No webhook is enabled for this provider."})
