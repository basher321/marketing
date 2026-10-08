"""HubSpot CRM adapter (stub)."""
from typing import Any

from app.integrations.base_adapter import BaseAdapter


class HubSpotAdapter(BaseAdapter):
    provider_name = "hubspot"

    def test_connection(self) -> bool:
        raise NotImplementedError

    def fetch_account_info(self) -> dict[str, Any]:
        raise NotImplementedError
