"""Multi-tenant context resolver (subdomain/header-based) using a ContextVar."""
from contextvars import ContextVar
from typing import Optional

from starlette.requests import Request

# Not part of the SPEC-BE-002/003 config surface yet — hardcoded here rather
# than added to Settings without a spec update. Move these into config.py
# (with real Field(...) entries) if they need to vary per environment.
_TENANT_HEADER = "X-Tenant-ID"
_ROOT_DOMAIN = "localhost"

_current_tenant_id: ContextVar[Optional[str]] = ContextVar("current_tenant_id", default=None)


def set_current_tenant_id(tenant_id: Optional[str]) -> None:
    _current_tenant_id.set(tenant_id)


def get_current_tenant_id() -> Optional[str]:
    return _current_tenant_id.get()


def resolve_tenant_slug(request: Request) -> Optional[str]:
    """Resolve a tenant identifier from header first, then subdomain."""
    header_value = request.headers.get(_TENANT_HEADER)
    if header_value:
        return header_value

    host = request.headers.get("host", "")
    host = host.split(":")[0]
    if host and host != _ROOT_DOMAIN and host.endswith(f".{_ROOT_DOMAIN}"):
        subdomain = host[: -len(f".{_ROOT_DOMAIN}")]
        if subdomain and subdomain != "www":
            return subdomain
    return None
