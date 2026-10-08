"""Login rate-limit safety net (SPEC-BE-039)."""
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.rate_limiter import rate_limiter

# Only POST /auth/login is limited, and only FAILED attempts (401 responses) are counted, per
# client IP: RATE_LIMIT_LOGIN_ATTEMPTS failures within RATE_LIMIT_LOGIN_WINDOW_MINUTES block
# further logins from that IP until the oldest failure leaves the window. Successful logins
# never count. Per-account password-guessing protection is the lockout in auth_service.login;
# this catches one network spraying many accounts. Add a separate RateLimiter for any
# general API limit rather than widening this one.
LOGIN_PATH = "/api/v1/auth/login"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method != "POST" or request.url.path.rstrip("/") != LOGIN_PATH:
            return await call_next(request)

        key = request.client.host if request.client else "anonymous"
        wait = rate_limiter.retry_after(key)
        if wait:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many failed login attempts from this network. "
                    f"Try again in {wait} seconds."
                },
                headers={"Retry-After": str(wait)},
            )
        response = await call_next(request)
        if response.status_code == 401:
            rate_limiter.record(key)
        return response
