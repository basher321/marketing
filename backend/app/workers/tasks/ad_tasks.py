"""Ad results jobs (SPEC-BE-056, SPEC-BE-062): import Meta insights + statuses and
the other ad platforms' daily results every 3 hours."""
import structlog

logger = structlog.get_logger(__name__)


def run_ad_tasks() -> int:
    from app.services import ads_builder_service, campaign_service

    synced = campaign_service.sync_all_meta_results()
    if synced:
        logger.info("meta_insights_scheduled_sync", tenants=synced)
    # TikTok, Google/YouTube, LinkedIn, X, Snapchat, Pinterest (SPEC-BE-062).
    platforms = ads_builder_service.sync_all_results()
    if platforms:
        logger.info("platform_results_scheduled_sync", tenants=platforms)
    return synced + platforms
