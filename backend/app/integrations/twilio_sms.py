"""Twilio Programmable SMS client (SPEC-BE-108).

PilotSonic has one Twilio account (the Super admin's `twilio` platform setting);
each company sends from its own number. Every call goes through
base_adapter.http, so the dev fakes and httpx.MockTransport answer it in tests.
Credentials are never logged or put in an error message.
"""
import base64
import hashlib
import hmac
from typing import Any

from app.integrations import base_adapter

API = "https://api.twilio.com/2010-04-01"


class SmsError(Exception):
    """A Twilio call failed. `message` is safe to show; `code` is Twilio's error code."""

    def __init__(self, message: str, status_code: int = 502, code: str | None = None, auth: bool = False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.auth = auth


def _call(method: str, url: str, sid: str, token: str, **kwargs: Any) -> dict[str, Any]:
    try:
        resp = base_adapter.http(method, url, auth=(sid, token), **kwargs)
    except base_adapter.PlatformError as exc:
        raise SmsError(f"Twilio: {exc.message}", exc.status_code) from None
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code == 401:
        raise SmsError("Twilio rejected the account SID or auth token.", 502, "20003", auth=True)
    if resp.status_code >= 400:
        message = base_adapter.short(data.get("message") or f"HTTP {resp.status_code}")
        raise SmsError(f"Twilio: {message}", 502, str(data.get("code") or "") or None)
    return data if isinstance(data, dict) else {}


def account(sid: str, token: str) -> dict[str, Any]:
    data = _call("GET", f"{API}/Accounts/{sid}.json", sid, token)
    return {"name": data.get("friendly_name"), "status": data.get("status")}


def numbers(sid: str, token: str) -> list[dict[str, Any]]:
    """The account's phone numbers that can send SMS."""
    data = _call("GET", f"{API}/Accounts/{sid}/IncomingPhoneNumbers.json", sid, token, params={"PageSize": 100})
    out = []
    for n in data.get("incoming_phone_numbers") or []:
        caps = n.get("capabilities") or {}
        out.append({
            "number": n.get("phone_number"), "name": n.get("friendly_name"),
            "sms": bool(caps.get("sms") or caps.get("SMS")),
        })
    return out


def send(sid: str, token: str, from_number: str, to_number: str, body: str, status_callback: str | None) -> dict[str, Any]:
    form = {"From": from_number, "To": to_number, "Body": body}
    if status_callback:
        form["StatusCallback"] = status_callback
    data = _call("POST", f"{API}/Accounts/{sid}/Messages.json", sid, token, data=form)
    return {"sid": data.get("sid"), "status": data.get("status") or "queued"}


def signature(token: str, url: str, params: dict[str, str]) -> str:
    """Twilio's X-Twilio-Signature: base64(HMAC-SHA1(url + each key+value, keys sorted))."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def valid_signature(token: str, urls: list[str], params: dict[str, str], given: str | None) -> bool:
    if not token or not given:
        return False
    return any(hmac.compare_digest(signature(token, u, params), given) for u in urls)


def segments(body: str) -> int:
    """SMS segments: GSM-7 text is 160 (153 when split), anything else UCS-2 70 (67)."""
    gsm = all(ord(ch) < 128 for ch in body)
    single, multi = (160, 153) if gsm else (70, 67)
    n = len(body)
    return 1 if n <= single else -(-n // multi)
