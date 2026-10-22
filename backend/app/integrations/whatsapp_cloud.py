"""WhatsApp Business through Meta's WhatsApp Cloud API (SPEC-BE-112).

Companies connect with Embedded Signup (Facebook Login for Business with the
WhatsApp configuration): the browser gets a code plus the WABA and phone number
ids; the server exchanges the code with PilotSonic's Meta app for a business
token. Calls go through base_adapter.http (dev fakes / MockTransport in tests).
Tokens are never logged or put in an error message.

Meta's rules this module relies on:
- Free-form messages only within 24 hours of the customer's last message
  (the "customer service window"); after that only approved templates.
- Webhooks are signed with the app secret: X-Hub-Signature-256 = sha256=HMAC(body).
"""
import hashlib
import hmac
from typing import Any

from app.config import get_settings
from app.integrations import base_adapter

SERVICE_WINDOW_HOURS = 24


class WhatsAppError(Exception):
    def __init__(self, message: str, status_code: int = 502, auth: bool = False, code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.auth = auth
        self.code = code


def _graph() -> str:
    return f"https://graph.facebook.com/{get_settings().META_GRAPH_VERSION}"


def _call(method: str, path: str, token: str | None = None, **kwargs: Any) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = base_adapter.http(method, f"{_graph()}/{path.lstrip('/')}", headers=headers, **kwargs)
    except base_adapter.PlatformError as exc:
        raise WhatsAppError(f"WhatsApp: {exc.message}", exc.status_code) from None
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        err = data.get("error") if isinstance(data, dict) else None
        err = err if isinstance(err, dict) else {}
        code = err.get("code")
        auth = resp.status_code == 401 or code == 190
        message = base_adapter.short(err.get("error_user_msg") or err.get("message") or f"HTTP {resp.status_code}")
        raise WhatsAppError(f"WhatsApp: {message}", 502, auth=auth, code=code if isinstance(code, int) else None)
    return data if isinstance(data, dict) else {}


def exchange_code(app_id: str, app_secret: str, code: str) -> str:
    data = _call("GET", "oauth/access_token", params={"client_id": app_id, "client_secret": app_secret, "code": code})
    token = data.get("access_token")
    if not token:
        raise WhatsAppError("WhatsApp: Meta didn't return a token.")
    return str(token)


def phone_number(token: str, phone_number_id: str) -> dict[str, Any]:
    data = _call("GET", phone_number_id, token, params={"fields": "display_phone_number,verified_name,quality_rating"})
    return {"display_phone_number": data.get("display_phone_number"), "verified_name": data.get("verified_name")}


def subscribe(token: str, waba_id: str) -> None:
    _call("POST", f"{waba_id}/subscribed_apps", token)


def send_text(token: str, phone_number_id: str, to: str, body: str) -> str:
    data = _call("POST", f"{phone_number_id}/messages", token, json={
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to.lstrip("+"),
        "type": "text", "text": {"preview_url": True, "body": body},
    })
    return str((data.get("messages") or [{}])[0].get("id") or "")


def send_image(token: str, phone_number_id: str, to: str, link: str, caption: str | None) -> str:
    image: dict[str, Any] = {"link": link}
    if caption:
        image["caption"] = caption
    data = _call("POST", f"{phone_number_id}/messages", token, json={
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to.lstrip("+"),
        "type": "image", "image": image,
    })
    return str((data.get("messages") or [{}])[0].get("id") or "")


def valid_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def sign(app_secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
