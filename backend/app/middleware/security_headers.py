"""HSTS, CSP, X-Frame-Options."""
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# FastAPI's Swagger UI (/docs) and ReDoc (/redoc) pages load their JS/CSS from
# cdn.jsdelivr.net, run an inline init script, and use FastAPI's favicon (ReDoc
# also pulls Google Fonts and spawns a blob: worker). The strict API policy
# blocks all of that and renders a blank page, so only these HTML pages get a
# policy that allows exactly those sources.
DOCS_PATHS = ("/docs", "/redoc")
DEFAULT_CSP = "default-src 'self'"
DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "worker-src 'self' blob:"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        is_docs = request.url.path.startswith(DOCS_PATHS)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = DOCS_CSP if is_docs else DEFAULT_CSP
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
