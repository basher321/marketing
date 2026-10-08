"""WhatsApp Business Cloud API adapter (stub)."""
from typing import Any

from app.integrations.base_adapter import BaseAdapter


class WhatsAppAdapter(BaseAdapter):
    provider_name = "whatsapp"

    def test_connection(self) -> bool:
        raise NotImplementedError

    def fetch_account_info(self) -> dict[str, Any]:
        raise NotImplementedError
