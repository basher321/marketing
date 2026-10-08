"""SMTP/SendGrid email adapter (stub — see app/utils/email_sender.py for the working dev-mode sender)."""
from typing import Any

from app.integrations.base_adapter import BaseAdapter


class EmailAdapter(BaseAdapter):
    provider_name = "email"

    def test_connection(self) -> bool:
        raise NotImplementedError

    def fetch_account_info(self) -> dict[str, Any]:
        raise NotImplementedError
