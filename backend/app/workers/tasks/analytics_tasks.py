"""Metric rollup jobs."""
import logging

import structlog

logger = logging.getLogger(__name__)
slog = structlog.get_logger(__name__)


async def rollup_metrics(tenant_id: str | None = None) -> dict:
    logger.info("rollup_metrics stub called (tenant_id=%s)", tenant_id)
    return {"tenant_id": tenant_id, "status": "not_implemented"}


def import_organic_metrics_all() -> int:
    """SPEC-BE-078: every 6 hours, import post results for each company with
    organic posts published in the last 30 days. One company's failure never
    stops the others."""
    from sqlalchemy import text

    from app.db.session import SessionLocal
    from app.services.analytics_service import import_organic_metrics

    db = SessionLocal()
    done = 0
    try:
        tenant_ids = [str(t) for (t,) in db.execute(text(
            "SELECT DISTINCT sp.tenant_id FROM scheduled_posts sp JOIN content_assets ca ON ca.id = sp.content_asset_id "
            "WHERE sp.status = 'published' AND ca.format = 'organic_post' AND sp.published_at >= now() - interval '30 days'"))]
        for tenant_id in tenant_ids:
            try:
                import_organic_metrics(db, tenant_id, None, throttle=False)
                done += 1
            except Exception:
                db.rollback()
                slog.exception("organic_metrics_import_failed", tenant_id=tenant_id)
    finally:
        db.close()
    return done
