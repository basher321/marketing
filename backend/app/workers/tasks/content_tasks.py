"""Async content generation jobs."""
import logging

logger = logging.getLogger(__name__)


async def generate_content_async(tenant_id: str | None = None, brief: str | None = None) -> dict:
    logger.info("generate_content_async stub called (tenant_id=%s)", tenant_id)
    return {"tenant_id": tenant_id, "status": "not_implemented"}
