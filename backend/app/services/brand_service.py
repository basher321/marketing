"""Brand settings business logic (SPEC-BE-012)."""
from typing import Any

import structlog
from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import ReturningInsert

from app.core.audit import write_audit_log
from app.models.brand import BrandSettings
from app.schemas.brand import BrandSettingsUpdate

logger = structlog.get_logger(__name__)

# Documented defaults returned by GET before the tenant has ever saved (no row is created by
# reading). They match ai/retrieval.get_brand_voice()'s no-row defaults: no brand name,
# tone 50, style 50, English only, no forbidden terms.
DEFAULT_VOICE_VALUE = 50
DEFAULTS: dict[str, Any] = {
    "brand_name": "",
    "tone": DEFAULT_VOICE_VALUE,
    "style": DEFAULT_VOICE_VALUE,
    "primary_language": "en",
    "supported_languages": ["en"],
    "forbidden_terms": [],
}


def _voice_value(voice_config: dict[str, Any], key: str) -> int:
    # voice_config->'tone' / ->'style' are integers 0-100; a missing or malformed value reads
    # as the default, same rule as ai/retrieval.get_brand_voice().
    value = voice_config.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
        return value
    return DEFAULT_VOICE_VALUE


def get_brand_settings(db: Session, tenant_id: str) -> dict[str, Any]:
    row = db.scalars(select(BrandSettings).where(BrandSettings.tenant_id == tenant_id)).first()
    if row is None:
        # Fresh list objects, so a caller can never mutate the shared DEFAULTS.
        return {**DEFAULTS, "supported_languages": ["en"], "forbidden_terms": []}
    voice = row.voice_config if isinstance(row.voice_config, dict) else {}
    return {
        "brand_name": row.brand_name,
        "tone": _voice_value(voice, "tone"),
        "style": _voice_value(voice, "style"),
        "primary_language": row.primary_language,
        "supported_languages": list(row.supported_languages or []),
        "forbidden_terms": list(row.forbidden_terms or []),
    }


def save_brand_settings(
    db: Session, tenant_id: str, actor_user_id: str, payload: BrandSettingsUpdate
) -> dict[str, Any]:
    """Replace the tenant's brand settings in one statement (upsert on UNIQUE tenant_id).

    INSERT ... ON CONFLICT (tenant_id) DO UPDATE, so the first save creates the row and two
    concurrent first saves can't create two. tone/style are merged into the existing
    voice_config (jsonb ||), so any other keys stored there are kept. write_audit_log()
    commits, making the upsert and its audit row one transaction.
    """
    voice = {"tone": payload.tone, "style": payload.style}
    stmt = insert(BrandSettings).values(
        tenant_id=tenant_id,
        brand_name=payload.brand_name,
        voice_config=voice,
        forbidden_terms=payload.forbidden_terms,
        primary_language=payload.primary_language,
        supported_languages=list(payload.supported_languages),
    )
    upsert: ReturningInsert[Any] = stmt.on_conflict_do_update(
        index_elements=[BrandSettings.tenant_id],
        set_={
            "brand_name": stmt.excluded.brand_name,
            "voice_config": BrandSettings.voice_config.op("||")(stmt.excluded.voice_config),
            "forbidden_terms": stmt.excluded.forbidden_terms,
            "primary_language": stmt.excluded.primary_language,
            "supported_languages": stmt.excluded.supported_languages,
        },
        # xmax = 0 only for a freshly inserted row: tells a first save from an update.
    ).returning(BrandSettings.id, literal_column("(xmax = 0)").label("inserted"))
    row = db.execute(upsert).one()

    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="brand.updated",
        resource_type="brand_settings",
        resource_id=str(row.id),
        metadata={"created": bool(row.inserted)},
    )
    logger.info("brand.updated", tenant_id=tenant_id, created=bool(row.inserted))
    return get_brand_settings(db, tenant_id)
