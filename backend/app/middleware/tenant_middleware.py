"""Tenant resolution from request."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.tenant_context import resolve_tenant_slug, set_current_tenant_id


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        slug = resolve_tenant_slug(request)
        request.state.tenant_slug = slug
        set_current_tenant_id(None)
        try:
            response = await call_next(request)
        finally:
            set_current_tenant_id(None)
        return response
