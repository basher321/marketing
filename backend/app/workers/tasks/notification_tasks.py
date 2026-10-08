"""Owner notifications."""
import logging

from app.workers.retry_policy import with_exponential_backoff

logger = logging.getLogger(__name__)


@with_exponential_backoff()
async def notify_owner(
    tenant_id: str | None = None, subject: str | None = None, body: str | None = None
) -> dict:
    logger.info("notify_owner stub called (tenant_id=%s, subject=%s)", tenant_id, subject)
    return {"tenant_id": tenant_id, "subject": subject, "status": "not_implemented"}
