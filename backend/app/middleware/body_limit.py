"""Request body size limit (SPEC-BE-071 F8).

Pure ASGI middleware (no buffering): rejects a request whose Content-Length
is over the limit, and stops a streamed (chunked) body as soon as it passes
the limit. Default 2 MB; upload routes keep their own, larger limits (their
services still validate type and size).
"""
import json
import re
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

DEFAULT_LIMIT = 2 * 1024 * 1024
ROUTE_LIMITS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"^/api/v1/ads/[a-z]+/media$"), 1024 * 1024 * 1024),  # ad videos (TikTok 500 MB, Meta 1 GB)
    (re.compile(r"^/api/v1/meta/media$"), 1024 * 1024 * 1024),
    (re.compile(r"^/api/v1/media$"), 1024 * 1024 * 1024),  # media library (SPEC-BE-074): videos up to 1 GB
    (re.compile(r"^/api/v1/tenants/me/branding/"), 2 * 1024 * 1024),  # 1 MB image + form overhead
)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class BodyTooLarge(Exception):
    pass


def limit_for(path: str) -> int:
    for pattern, limit in ROUTE_LIMITS:
        if pattern.match(path):
            return limit
    return DEFAULT_LIMIT


class BodyLimitMiddleware:
    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = limit_for(scope.get("path", ""))
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and length.isdigit() and int(length) > limit:
            await _too_large(send)
            return
        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge:
            if not started:
                await _too_large(send)


async def _too_large(send: Send) -> None:
    body = json.dumps({"error": "Request body too large."}).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
