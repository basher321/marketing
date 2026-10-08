"""Minimal MCP client (SPEC-BE-070): Streamable HTTP transport, JSON-RPC 2.0.

Used only to call *creative* tools on a company's MCP server (image or copy
generators). It never carries ad platform tokens: platform writes stay on the
direct-API path (user decision 2026-10-01). No new dependency: plain httpx,
through the shared, swappable client factory in base_adapter.

A server may answer a POST with JSON or with an SSE stream ("text/event-stream");
both are read. The session id from `initialize` (Mcp-Session-Id) is sent back.
"""
import base64
import itertools
import json
from typing import Any
from urllib.parse import urlparse

from app.integrations.base_adapter import PlatformError, http, short

PROTOCOL_VERSION = "2025-06-18"
MAX_IMAGE_BYTES = 30 * 1024 * 1024
_ids = itertools.count(1)


class MCPError(PlatformError):
    pass


def _check_url(url: str) -> str:
    from app.integrations import verify

    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise MCPError("The MCP server URL must start with https://.", 422)
    try:
        verify._require_public_host(parsed.hostname)
    except verify.VerifyError as exc:
        raise MCPError(str(exc), 422) from None
    return url.strip()


def _parse(resp: Any) -> dict[str, Any]:
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        last: dict[str, Any] = {}
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    last = json.loads(line[5:].strip())
                except ValueError:
                    continue
        return last
    try:
        return dict(resp.json())
    except ValueError:
        raise MCPError(f"The MCP server answered HTTP {resp.status_code} without JSON.", 502) from None


class MCPSession:
    def __init__(self, url: str, token: str | None) -> None:
        self.url = _check_url(url)
        self.token = token
        self.session_id: str | None = None

    def _rpc(self, method: str, params: dict[str, Any] | None = None, notify: bool = False) -> dict[str, Any]:
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            body["id"] = next(_ids)
        resp = http("POST", self.url, headers=headers, json=body, timeout=120.0)
        if resp.headers.get("mcp-session-id"):
            self.session_id = resp.headers["mcp-session-id"]
        if notify:
            return {}
        if resp.status_code in (401, 403):
            raise MCPError("The MCP server refused the token.", 409, auth=True)
        if resp.status_code >= 400:
            raise MCPError(f"The MCP server answered HTTP {resp.status_code}.", 502)
        data = _parse(resp)
        if data.get("error"):
            raise MCPError(f"MCP: {short((data['error'] or {}).get('message') or data['error'])}", 502)
        return dict(data.get("result") or {})

    def initialize(self) -> dict[str, Any]:
        result = self._rpc("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                          "clientInfo": {"name": "pilotsonic-ad-autopilot", "version": "1.0"}})
        self._rpc("notifications/initialized", notify=True)
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._rpc("tools/list").get("tools") or [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            text = " ".join(str(c.get("text", "")) for c in result.get("content") or [] if c.get("type") == "text")
            raise MCPError(f"MCP tool {name} failed: {short(text or 'no details')}", 502)
        return result


def first_image(result: dict[str, Any]) -> tuple[bytes, str]:
    """An image from a tools/call result: inline base64 `image` content, or a
    `resource_link` / embedded resource to an https image (downloaded with
    type and size checks)."""
    for item in result.get("content") or []:
        if item.get("type") == "image" and item.get("data"):
            data = base64.b64decode(item["data"])
            if len(data) > MAX_IMAGE_BYTES:
                raise MCPError("The MCP image is larger than 30 MB.", 422)
            return data, str(item.get("mimeType") or "image/png")
        uri = item.get("uri") or (item.get("resource") or {}).get("uri")
        if item.get("type") in ("resource_link", "resource") and uri:
            resp = http("GET", _check_url(str(uri)), timeout=60.0)
            if resp.status_code >= 400 or len(resp.content) > MAX_IMAGE_BYTES:
                raise MCPError("Couldn't download the MCP image.", 502)
            return resp.content, resp.headers.get("content-type", "image/png").split(";")[0]
    raise MCPError("The MCP tool returned no image.", 502)


MAX_VIDEO_BYTES = 1024 * 1024 * 1024


def first_video(result: dict[str, Any]) -> tuple[bytes, str]:
    """A video from a tools/call result (SPEC-BE-077): a resource_link /
    embedded resource, or structured {"video_url"}, to an https MP4/MOV,
    downloaded with the same host checks as images."""
    uris: list[str] = []
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and structured.get("video_url"):
        uris.append(str(structured["video_url"]))
    for item in result.get("content") or []:
        uri = item.get("uri") or (item.get("resource") or {}).get("uri")
        if item.get("type") in ("resource_link", "resource") and uri:
            uris.append(str(uri))
    for uri in uris:
        resp = http("GET", _check_url(uri), timeout=600.0)
        if resp.status_code >= 400 or len(resp.content) > MAX_VIDEO_BYTES:
            raise MCPError("Couldn't download the MCP video.", 502)
        return resp.content, resp.headers.get("content-type", "video/mp4").split(";")[0]
    raise MCPError("The MCP tool returned no video.", 502)


def first_json(result: dict[str, Any]) -> dict[str, Any]:
    """Structured output, or the first text content parsed as JSON."""
    if isinstance(result.get("structuredContent"), dict):
        return dict(result["structuredContent"])
    for item in result.get("content") or []:
        if item.get("type") == "text":
            try:
                value = json.loads(item.get("text") or "")
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    raise MCPError("The MCP tool returned no JSON.", 502)
