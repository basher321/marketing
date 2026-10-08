"""Cross-tenant access validation."""
from app.core.exceptions import TenantMismatchError


def assert_same_tenant(resource_tenant_id: str, current_tenant_id: str) -> None:
    if resource_tenant_id != current_tenant_id:
        raise TenantMismatchError()
