"""Ad metrics: tenant-wide CTR (7d) (SPEC-BE-011, SPEC-BE-056)."""
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.base_adapter import AD_RESULT_SOURCES

logger = structlog.get_logger(__name__)


def get_ctr_7d(db: Session, tenant_id: str) -> float | None:
    # CTR (7d) = SUM(link_clicks) / SUM(impressions) * 100 over the tenant's
    # imported ad results (analytics_events, source in AD_RESULT_SOURCES: Meta
    # SPEC-BE-056, the other ad platforms SPEC-BE-062) in
    # the trailing 7 days. None when no impressions were imported - shown as
    # "-", never an estimated value or a 0% placeholder.
    clicks, impressions = db.execute(
        text(
            "SELECT SUM(value) FILTER (WHERE metric = 'link_clicks'), SUM(value) FILTER (WHERE metric = 'impressions') "
            "FROM analytics_events WHERE tenant_id = :t AND source = ANY(:sources) AND event_time >= now() - interval '7 days'"
        ),
        {"t": tenant_id, "sources": list(AD_RESULT_SOURCES)},
    ).one()
    ctr = round(float(clicks or 0) / float(impressions) * 100, 2) if impressions else None
    logger.info("ad_ctr_7d_computed", tenant_id=tenant_id, ctr_7d_pct=ctr)
    return ctr
