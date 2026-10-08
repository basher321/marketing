"""Store sync jobs (SPEC-BE-058): re-import shipping from connected stores."""
import structlog

logger = structlog.get_logger(__name__)


def run_sync_tasks() -> int:
    from app.services import shipping_service

    synced = shipping_service.sync_all_stores()
    if synced:
        logger.info("shipping_scheduled_sync", tenants=synced)
    return synced


def refresh_social_tokens() -> dict[str, int]:
    """SPEC-BE-080: renew TikTok / LinkedIn sign-in tokens before they expire."""
    from app.services import social_oauth_service

    counts = social_oauth_service.refresh_due_tokens()
    if counts["refreshed"] or counts["expired"]:
        logger.info("social_tokens_refreshed", **counts)
    return counts
