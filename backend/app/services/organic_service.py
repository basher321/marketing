"""Organic Marketing (SPEC-BE-076): master content -> platform versions ->
scheduled posts, plus the publishing job.

Storage:
- organic_contents  : the master (caption, hashtags, CTA, link, media, mode, status)
- content_assets    : one platform version per row (format 'organic_post',
                      channel = platform). `variants` keeps every generation of
                      {caption, hashtags, cta, title}; selected_variant_index is
                      the current one (regenerate appends, revert selects).
                      media_urls = media ids. metadata: organic_content_id,
                      post_format, platform_options, warnings, edited.
- scheduled_posts   : one row per schedule/publish of a version (history kept;
                      at most one active - scheduled/publishing - per version).

Status rules:
- master: draft (manual) | needs_approval (AI) -> approved -> archived. An AI
  master must be approved before any schedule (409). A manager scheduling a
  manual draft approves it implicitly.
- post: scheduled -> publishing -> published | failed; cancelled. ('pending'
  isn't used: unapproved content can't be scheduled at all.)
- version (content_status): draft -> approved -> published; archived when
  its platform is removed.

Every query filters by tenant_id; another tenant's row is a 404.
"""
from __future__ import annotations

import zoneinfo
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import Date, Text, cast, func, or_, select, text
from sqlalchemy.orm import Session

from app.ai import creative_providers as cp
from app.ai.prompts import organic_adapter as oa
from app.ai.retrieval import get_brand_voice
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.integrations.social_base import PLATFORMS, MediaItem, PostPayload, SocialError, adapter
from app.models.content import ContentAsset
from app.models.media import MediaAsset
from app.models.organic import OrganicContent
from app.models.scheduled_post import ScheduledPost
from app.models.tenant import Tenant
from app.services import media_service, social_account_service
from app.utils import locale_data

logger = structlog.get_logger(__name__)

FORMAT = "organic_post"
ACTIVE_POST = ("pending", "scheduled", "publishing")
RETRY_MINUTES = (1, 5, 15)
POLL_SECONDS = 30
STUCK_AFTER = timedelta(minutes=30)
MAX_AHEAD = timedelta(days=365)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


def tenant_tz(db: Session, tenant_id: str) -> str:
    return db.execute(select(Tenant.timezone).where(Tenant.id == tenant_id)).scalar() or "UTC"


def _audit(db: Session, tenant_id: str, actor: str | None, action: str, rid: str, **meta: Any) -> None:
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action=f"organic.{action}", resource_type="organic_content",
                    resource_id=rid, metadata={k: (str(v) if isinstance(v, datetime) else v) for k, v in meta.items()})


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def _content(db: Session, tenant_id: str, content_id: str, lock: bool = False) -> OrganicContent:
    q = db.query(OrganicContent).filter(OrganicContent.id == content_id, OrganicContent.tenant_id == tenant_id)
    row = (q.with_for_update() if lock else q).first()
    if row is None:
        raise NotFoundError("Content not found.")
    return row


def _versions(db: Session, tenant_id: str, content_id: str, include_archived: bool = False) -> list[ContentAsset]:
    q = db.query(ContentAsset).filter(
        ContentAsset.tenant_id == tenant_id, ContentAsset.format == FORMAT,
        ContentAsset.extra_metadata["organic_content_id"].astext == str(content_id),
    )
    if not include_archived:
        q = q.filter(ContentAsset.status != "archived")
    rows = q.all()
    return sorted(rows, key=lambda v: PLATFORMS.index(v.channel) if v.channel in PLATFORMS else 9)


def _version(db: Session, tenant_id: str, version_id: str, lock: bool = False) -> ContentAsset:
    q = db.query(ContentAsset).filter(ContentAsset.id == version_id, ContentAsset.tenant_id == tenant_id, ContentAsset.format == FORMAT)
    row = (q.with_for_update() if lock else q).first()
    if row is None or row.status == "archived":
        raise NotFoundError("Post version not found.")
    return row


def _post(db: Session, tenant_id: str, post_id: str, lock: bool = False) -> ScheduledPost:
    q = db.query(ScheduledPost).filter(ScheduledPost.id == post_id, ScheduledPost.tenant_id == tenant_id)
    row = (q.with_for_update() if lock else q).first()
    if row is None:
        raise NotFoundError("Post not found.")
    return row


def _active_post(db: Session, tenant_id: str, version_id: str) -> ScheduledPost | None:
    return (
        db.query(ScheduledPost)
        .filter(ScheduledPost.tenant_id == tenant_id, ScheduledPost.content_asset_id == version_id, ScheduledPost.status.in_(ACTIVE_POST))
        .first()
    )


def _latest_post(db: Session, tenant_id: str, version_id: str) -> ScheduledPost | None:
    return (
        db.query(ScheduledPost)
        .filter(ScheduledPost.tenant_id == tenant_id, ScheduledPost.content_asset_id == version_id)
        .order_by(ScheduledPost.created_at.desc())
        .first()
    )


def _media(db: Session, tenant_id: str, ids: list[str]) -> list[MediaAsset]:
    """Media rows in the given order; an unknown or foreign id is a 422."""
    return media_service.media_rows(db, tenant_id, ids)


def _media_ref(m: MediaAsset) -> dict[str, Any]:
    return {"id": str(m.id), "kind": m.kind, "url": media_service.signed_url(str(m.id)), "width": m.width,
            "height": m.height, "duration_ms": m.duration_ms}


def products(db: Session, tenant_id: str, ids: list[str] | None = None, skus: list[str] | None = None) -> list[dict[str, Any]]:
    if not ids and not skus:
        return []
    rows = db.execute(
        text(
            "SELECT id, sku, title, COALESCE(short_description, '') AS description FROM products "
            "WHERE tenant_id = :t AND deleted_at IS NULL AND (id::text = ANY(:ids) OR sku = ANY(:skus))"
        ),
        {"t": tenant_id, "ids": [str(i) for i in ids or []], "skus": list(skus or [])},
    ).all()
    found = [{"id": str(r.id), "sku": r.sku, "title": r.title, "description": r.description} for r in rows]
    if ids and len({f["id"] for f in found} & set(ids)) != len(set(ids)):
        raise AppError("Some products don't exist.", 422)
    return found


def product_photo_media(db: Session, tenant_id: str, actor: str | None, skus: list[str]) -> list[MediaAsset]:
    """The products' own https photos, copied into the media library
    (source 'catalog'; the same photo twice is one row). Products without a
    usable photo are skipped."""
    out: list[MediaAsset] = []
    for sku in skus:
        try:
            result = cp.CatalogImageProvider().generate(db, tenant_id, cp.CreativeRequest(kind="image", skus=[sku]))
        except cp.ProviderFailed:
            continue
        out.append(media_service.store(db, tenant_id, actor, result.image or b"", name=f"Product photo {sku}", source="catalog",
                                       metadata={"sku": sku}, audit=False))
    return out


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------
def _current(v: ContentAsset) -> dict[str, Any]:
    variants = v.variants or [{}]
    idx = v.selected_variant_index if v.selected_variant_index is not None and v.selected_variant_index < len(variants) else len(variants) - 1
    return dict(variants[idx])


def _set_current(v: ContentAsset, values: dict[str, Any], new_variant: bool) -> None:
    variants = [dict(x) for x in (v.variants or [])]
    if new_variant or not variants:
        variants.append(values)
        v.selected_variant_index = len(variants) - 1
    else:
        idx = v.selected_variant_index if v.selected_variant_index is not None else len(variants) - 1
        variants[idx] = values
    v.variants = variants[-20:]
    v.selected_variant_index = min(v.selected_variant_index or 0, len(v.variants) - 1)


def _meta(v: ContentAsset) -> dict[str, Any]:
    return dict(v.extra_metadata or {})


def _platform_media(db: Session, tenant_id: str, actor: str | None, platform: str, post_format: str,
                    media: list[MediaAsset]) -> tuple[list[str], list[str]]:
    """Media ids for one platform: an image outside the platform's ratio range
    is replaced by a centre crop in its preferred ratio (made once, reused).
    Videos are kept as they are (a warning is shown instead)."""
    rules = oa.PLATFORM_RULES[platform]
    rng = rules.ratio_range.get(post_format)
    pref = rules.preferred_ratio.get(post_format)
    out: list[str] = []
    notes: list[str] = []
    for m in media:
        if m.kind == "image" and rng and pref and m.width and m.height and not (rng[0] - 0.01 <= m.width / m.height <= rng[1] + 0.01):
            child = media_service.find_derived(db, tenant_id, str(m.id), pref) or media_service.derive(db, tenant_id, actor, str(m.id), pref, "crop")
            out.append(str(child.id))
            notes.append(f"Image cropped to {pref} for {rules.label}.")
        else:
            out.append(str(m.id))
    return out, notes


def _build_version(db: Session, tenant_id: str, actor: str | None, content: OrganicContent, target: dict[str, Any],
                   copy: dict[str, Any] | None, media: list[MediaAsset]) -> ContentAsset:
    platform = target["platform"]
    fmt = target.get("post_format") or oa.default_format(platform, [m.kind for m in media])
    media_ids, notes = _platform_media(db, tenant_id, actor, platform, fmt, media)
    master = {"caption": content.caption, "hashtags": list(content.hashtags or []), "cta": content.cta,
              "title": content.title, "link_url": content.link_url}
    if copy:
        values, warnings = oa.enforce(platform, copy.get("caption") or content.caption, list(copy.get("hashtags") or content.hashtags or []),
                                      copy.get("cta") if copy.get("cta") is not None else content.cta, copy.get("title"), content.link_url, bool(media))
    else:
        values, warnings = oa.rules_adapt(platform, master, bool(media))
    version = ContentAsset(
        tenant_id=tenant_id, title=content.title, channel=platform, format=FORMAT, variants=[values], selected_variant_index=0,
        media_urls=media_ids, status="approved" if content.status == "approved" else "draft",
        extra_metadata={"organic_content_id": str(content.id), "post_format": fmt, "platform_options": dict(target.get("platform_options") or {}),
                        "warnings": notes + warnings, "edited": False, "source": content.mode},
    )
    db.add(version)
    return version


def _adapt_all(db: Session, tenant_id: str, platforms: list[str], master: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """AI adaptation for several platforms in one call; on failure the rules
    adapter is used and the caller shows the returned warning."""
    voice = get_brand_voice(db, tenant_id)
    performance, _ = performance_context(db, tenant_id, platforms)
    try:
        result = cp.generate(db, tenant_id, cp.CreativeRequest(kind="copy", system=oa.SYSTEM, prompt=oa.adapt_prompt(master, platforms, voice, performance),
                                                              max_tokens=3000))
        data = oa.parse_json(result.text or "")
        out = {p: dict((data.get("platforms") or {}).get(p) or {}) for p in platforms}
        return {p: v for p, v in out.items() if v}, []
    except (cp.AllProvidersFailed, ValueError) as exc:
        logger.warning("organic_ai_adapt_failed", tenant_id=tenant_id, error=str(exc)[:200])
        return {}, ["AI adaptation wasn't available, so the versions were adapted by the platform rules."]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _local(post: ScheduledPost) -> tuple[str, str | None]:
    md = post.extra_metadata or {}
    return str(md.get("timezone") or "UTC"), md.get("local_time")


def _excerpt(text_: str, n: int = 140) -> str:
    t = " ".join((text_ or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def post_dict(post: ScheduledPost, version: ContentAsset | None = None) -> dict[str, Any]:
    tz, local = _local(post)
    cur = _current(version) if version is not None else {}
    return {
        "id": str(post.id),
        "version_id": str(post.content_asset_id),
        "content_id": _meta(version).get("organic_content_id") if version is not None else None,
        "platform": post.channel,
        "status": post.status,
        "scheduled_at": _utc(post.scheduled_at),
        "timezone": tz,
        "local_time": local,
        "published_at": _utc(post.published_at),
        "external_post_id": post.external_post_id,
        "external_url": post.external_url,
        "error_message": post.error_message,
        "retry_count": int(post.retry_count or 0),
        "title": version.title if version is not None else None,
        "excerpt": _excerpt(cur.get("caption") or ""),
    }


def _version_dict(db: Session, tenant_id: str, v: ContentAsset, accounts: dict[str, dict[str, Any]], link_url: str | None) -> dict[str, Any]:
    md = _meta(v)
    cur = _current(v)
    media = _media_safe(db, tenant_id, list(v.media_urls or []))
    post = _active_post(db, tenant_id, str(v.id)) or _latest_post(db, tenant_id, str(v.id))
    acct = accounts.get(v.channel) or {}
    return {
        "id": str(v.id),
        "platform": v.channel,
        "status": v.status,
        "post_format": md.get("post_format") or "post",
        "caption": cur.get("caption") or "",
        "hashtags": list(cur.get("hashtags") or []),
        "cta": cur.get("cta"),
        "title": cur.get("title"),
        "link_url": link_url,
        "media": [_media_ref(m) for m in media],
        "platform_options": dict(md.get("platform_options") or {}),
        "warnings": list(md.get("warnings") or []),
        "edited": bool(md.get("edited")),
        "variant_index": int(v.selected_variant_index or 0),
        "variant_count": len(v.variants or []),
        "account": {k: acct.get(k) for k in ("status", "account_name", "handle", "avatar_url", "extra", "limits")},
        "post": post_dict(post, v) if post else None,
    }


def _media_safe(db: Session, tenant_id: str, ids: list[str]) -> list[MediaAsset]:
    if not ids:
        return []
    rows = {str(m.id): m for m in db.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id, MediaAsset.id.in_(ids))}
    return [rows[i] for i in ids if i in rows]


def content_dict(db: Session, tenant_id: str, content: OrganicContent) -> dict[str, Any]:
    accounts = {a["platform"]: a for a in social_account_service.list_accounts(db, tenant_id)["items"]}
    md = dict(content.extra_metadata or {})
    return {
        "id": str(content.id),
        "title": content.title,
        "mode": content.mode,
        "prompt": content.prompt,
        "caption": content.caption,
        "hashtags": list(content.hashtags or []),
        "cta": content.cta,
        "link_url": content.link_url,
        "media": [_media_ref(m) for m in _media_safe(db, tenant_id, [str(i) for i in content.media_ids or []])],
        "product_ids": [str(i) for i in content.product_ids or []],
        "status": content.status,
        "approved_at": _utc(content.approved_at),
        "media_pending": list(md.get("media_pending") or []),
        "warnings": list(md.get("warnings") or []),
        "performance_used": bool(md.get("performance_used")),
        "versions": [_version_dict(db, tenant_id, v, accounts, content.link_url) for v in _versions(db, tenant_id, str(content.id))],
        "created_at": _utc(content.created_at),
        "updated_at": _utc(content.updated_at),
    }


def get_content(db: Session, tenant_id: str, content_id: str) -> dict[str, Any]:
    return content_dict(db, tenant_id, _content(db, tenant_id, content_id))


def list_contents(db: Session, tenant_id: str, status: str | None, platform: str | None, q: str | None, page: int, page_size: int = 25) -> dict[str, Any]:
    query = db.query(OrganicContent).filter(OrganicContent.tenant_id == tenant_id)
    if status:
        query = query.filter(OrganicContent.status == status)
    else:
        query = query.filter(OrganicContent.status != "archived")
    if q:
        query = query.filter(or_(OrganicContent.title.ilike(f"%{q}%"), OrganicContent.caption.ilike(f"%{q}%")))
    if platform:
        ids = select(ContentAsset.extra_metadata["organic_content_id"].astext).where(
            ContentAsset.tenant_id == tenant_id, ContentAsset.format == FORMAT, ContentAsset.channel == platform, ContentAsset.status != "archived")
        query = query.filter(cast(OrganicContent.id, Text).in_(ids))  # uuid vs the jsonb text value
    count = query.with_entities(func.count(OrganicContent.id)).scalar() or 0
    rows = query.order_by(OrganicContent.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for c in rows:
        versions = _versions(db, tenant_id, str(c.id))
        vids = [str(v.id) for v in versions]
        nxt = (db.query(func.min(ScheduledPost.scheduled_at)).filter(ScheduledPost.tenant_id == tenant_id, ScheduledPost.content_asset_id.in_(vids),
                                                                     ScheduledPost.status == "scheduled").scalar() if vids else None)
        published = (db.query(func.count(ScheduledPost.id)).filter(ScheduledPost.tenant_id == tenant_id, ScheduledPost.content_asset_id.in_(vids),
                                                                   ScheduledPost.status == "published").scalar() if vids else 0)
        thumb = _media_safe(db, tenant_id, [str(i) for i in (c.media_ids or [])[:1]])
        items.append({
            "id": str(c.id), "title": c.title, "mode": c.mode, "status": c.status, "excerpt": _excerpt(c.caption),
            "platforms": [v.channel for v in versions], "thumbnail_url": media_service.signed_url(str(thumb[0].id)) if thumb else None,
            "next_post_at": _utc(nxt), "published_count": int(published or 0), "created_at": _utc(c.created_at),
        })
    return {"count": int(count), "items": items}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def _check_targets(targets: list[dict[str, Any]]) -> None:
    seen = [t["platform"] for t in targets]
    if len(seen) != len(set(seen)):
        raise AppError("Each platform can be targeted once per post.", 422)


def create_manual(db: Session, tenant_id: str, actor: str, payload: Any) -> dict[str, Any]:
    targets = [t.model_dump() for t in payload.targets]
    _check_targets(targets)
    media = _media(db, tenant_id, payload.media_ids)
    content = OrganicContent(
        tenant_id=tenant_id, title=payload.title, mode="manual", caption=payload.caption.strip(),
        hashtags=oa.clean_hashtags(payload.hashtags), cta=payload.cta, link_url=payload.link_url,
        media_ids=[str(m.id) for m in media], status="draft", created_by=actor, extra_metadata={},
    )
    db.add(content)
    db.flush()
    copies: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    if payload.adapt == "ai":
        master = {"caption": content.caption, "hashtags": content.hashtags, "cta": content.cta, "link_url": content.link_url}
        copies, warnings = _adapt_all(db, tenant_id, [t["platform"] for t in targets], master)
    for t in targets:
        _build_version(db, tenant_id, actor, content, t, copies.get(t["platform"]), media)
    content.extra_metadata = {"warnings": warnings, "adapt": payload.adapt}
    db.flush()
    _audit(db, tenant_id, actor, "created", str(content.id), mode="manual", platforms=[t["platform"] for t in targets])
    return get_content(db, tenant_id, str(content.id))


def ai_posts(db: Session, tenant_id: str, brief: str, platforms: list[str], product_rows: list[dict[str, Any]],
             tone: str | None, link_url: str | None, count: int) -> tuple[list[dict[str, Any]], cp.CreativeResult]:
    """One LLM call -> `count` posts (master + per-platform copy + visual brief).
    No AI model working -> AppError 503 (never a mock). Each post carries
    "_performance_used" (SPEC-BE-081) for _create_ai_content."""
    voice = get_brand_voice(db, tenant_id)
    performance, used = performance_context(db, tenant_id, platforms)
    prompt = oa.generation_prompt(brief, platforms, product_rows, voice, tone, link_url, count, performance)
    try:
        result = cp.generate(db, tenant_id, cp.CreativeRequest(kind="copy", system=oa.SYSTEM, prompt=prompt, max_tokens=min(1500 * count + 1000, 12000)))
    except cp.AllProvidersFailed as exc:
        raise AppError(f"AI copy isn't available: {exc}"[:500], 503) from None
    try:
        posts = [p for p in oa.parse_json(result.text or "").get("posts") or [] if isinstance(p, dict)]
    except ValueError:
        raise AppError("The AI model's answer couldn't be read; try again.", 502) from None
    if not posts:
        raise AppError("The AI model returned no posts; try again.", 502)
    return [{**p, "_performance_used": used} for p in posts[:count]], result


def _create_ai_content(db: Session, tenant_id: str, actor: str, *, prompt: str, post: dict[str, Any], targets: list[dict[str, Any]],
                       product_rows: list[dict[str, Any]], tone: str | None, link_url: str | None, media: list[MediaAsset],
                       model: str, extra: dict[str, Any] | None = None) -> OrganicContent:
    master = dict(post.get("master") or {})
    content = OrganicContent(
        tenant_id=tenant_id, title=(str(post.get("title") or "") or prompt)[:200], mode="ai", prompt=prompt,
        caption=str(master.get("caption") or "").strip(), hashtags=oa.clean_hashtags(master.get("hashtags")),
        cta=master.get("cta"), link_url=link_url, media_ids=[str(m.id) for m in media],
        product_ids=[p["id"] for p in product_rows], status="needs_approval", created_by=actor,
        extra_metadata={"model": model, "tone": tone, "visual_brief": post.get("visual_brief"), "warnings": [],
                        "performance_used": bool(post.get("_performance_used")), **(extra or {})},
    )
    if not content.caption:
        raise AppError("The AI model returned an empty caption; try again.", 502)
    db.add(content)
    db.flush()
    platforms_copy = dict(post.get("platforms") or {})
    for t in targets:
        _build_version(db, tenant_id, actor, content, t, dict(platforms_copy.get(t["platform"]) or {}) or None, media)
    return content


def create_ai(db: Session, tenant_id: str, actor: str, payload: Any) -> dict[str, Any]:
    targets = [t.model_dump() for t in payload.targets]
    _check_targets(targets)
    product_rows = products(db, tenant_id, ids=payload.product_ids)
    media = _media(db, tenant_id, payload.media.media_ids) if payload.media.mode == "use" else []
    posts, result = ai_posts(db, tenant_id, payload.prompt, [t["platform"] for t in targets], product_rows, payload.tone, payload.link_url, 1)
    content = _create_ai_content(db, tenant_id, actor, prompt=payload.prompt, post=posts[0], targets=targets, product_rows=product_rows,
                                 tone=payload.tone, link_url=payload.link_url, media=media, model=result.model)
    if payload.media.mode in ("generate_photo", "generate_video"):
        start_media_generation(db, tenant_id, actor, content, payload.media.mode, dict(payload.media.generation or {}), targets)
    db.flush()
    _audit(db, tenant_id, actor, "created", str(content.id), mode="ai", platforms=[t["platform"] for t in targets], model=result.model)
    return get_content(db, tenant_id, str(content.id))


def start_media_generation(db: Session, tenant_id: str, actor: str, content: OrganicContent, mode: str,
                           generation: dict[str, Any], targets: list[dict[str, Any]]) -> list[str]:
    """Starts SPEC-BE-077 jobs for a content; their results are attached by
    attach_generated_media() when they finish."""
    from app.services import generation_service

    kind = "image" if mode == "generate_photo" else "video"
    target = targets[0]["platform"] if targets else None
    req = {
        "prompt": generation.get("prompt") or (content.extra_metadata or {}).get("visual_brief") or content.prompt or content.caption[:500],
        "product_ids": [str(p) for p in content.product_ids or []],
        "target_platform": generation.get("target_platform") or target,
        **{k: v for k, v in generation.items() if k in ("aspect_ratio", "duration_s", "style", "reference_media_ids")},
    }
    job = generation_service.start(db, tenant_id, actor, kind, req, organic_content_id=str(content.id))
    md = dict(content.extra_metadata or {})
    md["media_pending"] = list(md.get("media_pending") or []) + [job["id"]]
    content.extra_metadata = md
    return [job["id"]]


def attach_generated_media(db: Session, tenant_id: str, content_id: str, job_id: str, media_id: str | None, error: str | None) -> None:
    """Called by generation_service when a job linked to a content ends."""
    content = db.query(OrganicContent).filter(OrganicContent.id == content_id, OrganicContent.tenant_id == tenant_id).with_for_update().first()
    if content is None:
        return
    md = dict(content.extra_metadata or {})
    md["media_pending"] = [j for j in md.get("media_pending") or [] if j != job_id]
    if error:
        md["warnings"] = list(md.get("warnings") or []) + [f"Media generation failed: {error}"[:300]]
    content.extra_metadata = md
    if media_id:
        content.media_ids = [*[str(i) for i in content.media_ids or []], media_id]
        media = _media(db, tenant_id, [media_id])
        for v in _versions(db, tenant_id, content_id):
            fmt = _meta(v).get("post_format") or "post"
            if v.channel == "tiktok" and media[0].kind == "video":
                fmt = "video"
            elif v.channel == "instagram" and media[0].kind == "video" and fmt == "post":
                fmt = "reel"
            ids, notes = _platform_media(db, tenant_id, None, v.channel, fmt, media)
            v.media_urls = [*list(v.media_urls or []), *ids]
            vmd = _meta(v)
            vmd["post_format"] = fmt
            vmd["warnings"] = list(vmd.get("warnings") or []) + notes
            v.extra_metadata = vmd
    db.flush()


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------
def _editable(db: Session, tenant_id: str, v: ContentAsset) -> None:
    post = _active_post(db, tenant_id, str(v.id))
    if post is not None and post.status == "publishing":
        raise ConflictError("This post is being published right now; it can't be edited.")
    if v.status == "published":
        raise ConflictError("This version is already published; create a new post to change it.")


def update_content(db: Session, tenant_id: str, actor: str, content_id: str, payload: Any) -> dict[str, Any]:
    content = _content(db, tenant_id, content_id, lock=True)
    if content.status == "archived":
        raise ConflictError("This content is archived.")
    sent = payload.model_fields_set
    if "media_ids" in sent and payload.media_ids is not None:
        content.media_ids = [str(m.id) for m in _media(db, tenant_id, payload.media_ids)]
    for field in ("title", "caption", "cta", "link_url"):
        if field in sent:
            setattr(content, field, getattr(payload, field))
    if "hashtags" in sent and payload.hashtags is not None:
        content.hashtags = oa.clean_hashtags(payload.hashtags)
    if payload.readapt:
        master = {"caption": content.caption, "hashtags": list(content.hashtags or []), "cta": content.cta, "title": content.title, "link_url": content.link_url}
        media = _media_safe(db, tenant_id, [str(i) for i in content.media_ids or []])
        for v in _versions(db, tenant_id, content_id):
            md = _meta(v)
            if md.get("edited") or v.status == "published":
                continue
            values, warnings = oa.rules_adapt(v.channel, master, bool(media))
            _set_current(v, values, new_variant=False)
            ids, notes = _platform_media(db, tenant_id, actor, v.channel, md.get("post_format") or "post", media)
            v.media_urls = ids
            md["warnings"] = notes + warnings
            v.extra_metadata = md
    db.flush()
    _audit(db, tenant_id, actor, "updated", content_id, fields=sorted(sent), readapt=payload.readapt)
    return get_content(db, tenant_id, content_id)


def set_targets(db: Session, tenant_id: str, actor: str, content_id: str, payload: Any) -> dict[str, Any]:
    content = _content(db, tenant_id, content_id, lock=True)
    existing = {v.channel: v for v in _versions(db, tenant_id, content_id)}
    for platform in payload.remove:
        v = existing.get(platform)
        if v is None:
            continue
        if _active_post(db, tenant_id, str(v.id)) is not None:
            raise ConflictError(f"The {platform} version is scheduled; cancel it first.")
        v.status = "archived"
    media = _media_safe(db, tenant_id, [str(i) for i in content.media_ids or []])
    for t in payload.add:
        if t.platform in existing and t.platform not in payload.remove:
            raise AppError(f"{t.platform} is already a target.", 422)
        _build_version(db, tenant_id, actor, content, t.model_dump(), None, media)
    db.flush()
    _audit(db, tenant_id, actor, "targets_changed", content_id, add=[t.platform for t in payload.add], remove=list(payload.remove))
    return get_content(db, tenant_id, content_id)


def update_version(db: Session, tenant_id: str, actor: str, version_id: str, payload: Any) -> dict[str, Any]:
    v = _version(db, tenant_id, version_id, lock=True)
    _editable(db, tenant_id, v)
    sent = payload.model_fields_set
    cur = _current(v)
    for field in ("caption", "cta", "title"):
        if field in sent:
            cur[field] = getattr(payload, field)
    if "hashtags" in sent and payload.hashtags is not None:
        cur["hashtags"] = oa.clean_hashtags(payload.hashtags)
    md = _meta(v)
    if "media_ids" in sent and payload.media_ids is not None:
        v.media_urls = [str(m.id) for m in _media(db, tenant_id, payload.media_ids)]
    if "post_format" in sent and payload.post_format:
        md["post_format"] = payload.post_format
    if "platform_options" in sent and payload.platform_options is not None:
        md["platform_options"] = dict(payload.platform_options)
    content = _content(db, tenant_id, md["organic_content_id"])
    values, warnings = oa.enforce(v.channel, cur.get("caption") or "", list(cur.get("hashtags") or []), cur.get("cta"), cur.get("title"),
                                  content.link_url, bool(v.media_urls))
    _set_current(v, values, new_variant=False)
    md["warnings"] = warnings
    md["edited"] = True
    v.extra_metadata = md
    db.flush()
    _audit(db, tenant_id, actor, "version_edited", str(content.id), version_id=version_id, fields=sorted(sent))
    return get_content(db, tenant_id, str(content.id))


def regenerate(db: Session, tenant_id: str, actor: str, version_id: str, parts: list[str], instruction: str | None) -> dict[str, Any]:
    """New copy for the named parts only; everything else - including the
    media - is kept. The previous text stays in `variants` (revert)."""
    v = _version(db, tenant_id, version_id, lock=True)
    _editable(db, tenant_id, v)
    cur = _current(v)
    voice = get_brand_voice(db, tenant_id)
    performance, _ = performance_context(db, tenant_id, [v.channel])
    prompt = oa.regenerate_prompt(v.channel, {k: cur.get(k) for k in ("caption", "hashtags", "cta", "title")}, parts, instruction, voice,
                                  performance)
    try:
        result = cp.generate(db, tenant_id, cp.CreativeRequest(kind="copy", system=oa.SYSTEM, prompt=prompt, max_tokens=1500))
        data = oa.parse_json(result.text or "")
    except cp.AllProvidersFailed as exc:
        raise AppError(f"AI copy isn't available: {exc}"[:500], 503) from None
    except ValueError:
        raise AppError("The AI model's answer couldn't be read; try again.", 502) from None
    new = dict(cur)
    for part in parts:
        if data.get(part) is not None:
            new[part] = data[part]
    md = _meta(v)
    content = _content(db, tenant_id, md["organic_content_id"])
    values, warnings = oa.enforce(v.channel, str(new.get("caption") or ""), list(new.get("hashtags") or []), new.get("cta"), new.get("title"),
                                  content.link_url, bool(v.media_urls))
    for part in ("caption", "hashtags", "cta", "title"):
        if part not in parts:
            values[part] = cur.get(part)  # untouched parts stay exactly as they were
    _set_current(v, values, new_variant=True)
    md["warnings"] = warnings
    v.extra_metadata = md
    db.flush()
    _audit(db, tenant_id, actor, "regenerated", str(content.id), version_id=version_id, parts=parts, model=result.model)
    return get_content(db, tenant_id, str(content.id))


def revert(db: Session, tenant_id: str, actor: str, version_id: str, index: int) -> dict[str, Any]:
    v = _version(db, tenant_id, version_id, lock=True)
    _editable(db, tenant_id, v)
    if not 0 <= index < len(v.variants or []):
        raise AppError("No such earlier version of the text.", 422)
    v.selected_variant_index = index
    content_id = _meta(v)["organic_content_id"]
    db.flush()
    _audit(db, tenant_id, actor, "reverted", content_id, version_id=version_id, variant_index=index)
    return get_content(db, tenant_id, content_id)


def approve(db: Session, tenant_id: str, actor: str, content_id: str) -> dict[str, Any]:
    content = _content(db, tenant_id, content_id, lock=True)
    if content.status == "archived":
        raise ConflictError("This content is archived.")
    _approve(db, tenant_id, actor, content)
    db.flush()
    _audit(db, tenant_id, actor, "approved", content_id)
    return get_content(db, tenant_id, content_id)


def _approve(db: Session, tenant_id: str, actor: str, content: OrganicContent) -> None:
    if content.status != "approved":
        content.status = "approved"
        content.approved_by = actor
        content.approved_at = _now()
    for v in _versions(db, tenant_id, str(content.id)):
        if v.status == "draft":
            v.status = "approved"


def archive(db: Session, tenant_id: str, actor: str, content_id: str) -> None:
    content = _content(db, tenant_id, content_id, lock=True)
    for v in _versions(db, tenant_id, content_id):
        if _active_post(db, tenant_id, str(v.id)) is not None:
            raise ConflictError("A version of this content is scheduled; cancel it first.")
    content.status = "archived"
    db.flush()
    _audit(db, tenant_id, actor, "archived", content_id)


# ---------------------------------------------------------------------------
# Validation + preview
# ---------------------------------------------------------------------------
def _issues(db: Session, tenant_id: str, v: ContentAsset, content: OrganicContent, account: dict[str, Any]) -> tuple[list[str], list[str]]:
    md = _meta(v)
    cur = _current(v)
    rules = oa.PLATFORM_RULES[v.channel]
    media = _media_safe(db, tenant_id, list(v.media_urls or []))
    errors, warnings = oa.media_warnings(v.channel, md.get("post_format") or "post",
                                         [{"kind": m.kind, "width": m.width, "height": m.height, "duration_ms": m.duration_ms} for m in media])
    if len(media) != len(v.media_urls or []):
        errors.append("Some media of this version was deleted.")
    if (content.extra_metadata or {}).get("media_pending"):
        errors.append("Media is still being generated.")
    status = str(account.get("status") or "not_connected")
    if status != "connected":
        label = social_account_service.LABEL[v.channel]
        errors.append(f"{label} isn't connected." if status == "not_connected" else
                      f"{label} needs attention ({status.replace('_', ' ')}):{', '.join(account.get('missing_permissions') or []) or account.get('last_error') or 'reconnect it'}.")
    text_ = oa.compose(v.channel, cur.get("caption") or "", list(cur.get("hashtags") or []), cur.get("cta"), content.link_url, bool(media))
    if len(text_) > rules.caption_max:
        errors.append(f"The text is {len(text_):,} characters; {rules.label} allows {rules.caption_max:,}.")
    if not (cur.get("caption") or "").strip() and not media:
        errors.append("The post is empty.")
    via_sapi = account.get("connected_via") == "socialapi"  # SPEC-BE-104
    if via_sapi and v.channel == "instagram" and (md.get("post_format") or "post") == "story":
        errors.append("Instagram stories can't be posted through SocialAPI yet; choose a feed post or reel.")
    if v.channel == "tiktok" and not via_sapi:
        allowed = (account.get("extra") or {}).get("privacy_level_options") or []
        privacy = (md.get("platform_options") or {}).get("privacy_level")
        if not privacy:
            errors.append("Choose who can see the TikTok post (privacy level).")
        elif allowed and privacy not in allowed:
            errors.append(f"TikTok privacy must be one of: {', '.join(allowed)}.")
    return errors, list(md.get("warnings") or []) + warnings


def preview(db: Session, tenant_id: str, version_id: str) -> dict[str, Any]:
    v = _version(db, tenant_id, version_id)
    md = _meta(v)
    content = _content(db, tenant_id, md["organic_content_id"])
    account = social_account_service.account(db, tenant_id, v.channel)
    cur = _current(v)
    media = _media_safe(db, tenant_id, list(v.media_urls or []))
    errors, warnings = _issues(db, tenant_id, v, content, account)
    rules = oa.PLATFORM_RULES[v.channel]
    # Where the feed cuts the caption with "…more" (approximate, for the mock-up).
    cutoff = {"instagram": 125, "facebook": 480, "linkedin": 210, "tiktok": 150}.get(v.channel)
    return {
        "version_id": version_id, "platform": v.channel, "post_format": md.get("post_format") or "post",
        "text": oa.compose(v.channel, cur.get("caption") or "", list(cur.get("hashtags") or []), cur.get("cta"), content.link_url, bool(media)),
        "title": cur.get("title"), "link_url": content.link_url, "media": [_media_ref(m) for m in media],
        "account": {k: account.get(k) for k in ("status", "account_name", "handle", "avatar_url")},
        "warnings": warnings, "errors": errors, "caption_max": rules.caption_max, "more_cutoff": cutoff,
    }


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
def to_utc(db: Session, tenant_id: str, local: datetime, tz: str | None) -> tuple[datetime, str]:
    zone = (tz or tenant_tz(db, tenant_id)).strip()
    if not locale_data.is_timezone(zone):
        raise AppError(f"Unknown timezone {zone!r}.", 422)
    aware = local.replace(tzinfo=zoneinfo.ZoneInfo(zone))
    return aware.astimezone(timezone.utc), zone


def _check_time(when: datetime, now: datetime | None = None) -> None:
    now = now or _now()
    if when < now + timedelta(minutes=1):
        raise AppError("Pick a time at least a minute from now.", 422)
    if when > now + MAX_AHEAD:
        raise AppError("Posts can be scheduled up to a year ahead.", 422)


def _ready(db: Session, tenant_id: str, actor: str, v: ContentAsset) -> OrganicContent:
    """Approval + validation before a schedule/publish. A manual draft is
    approved implicitly by the manager scheduling it; AI content must have
    been approved (409)."""
    content = _content(db, tenant_id, _meta(v)["organic_content_id"], lock=True)
    if content.status == "archived":
        raise ConflictError("This content is archived.")
    if content.status == "needs_approval":
        raise ConflictError("Approve this AI-generated content before scheduling it.")
    if v.status == "published":
        raise ConflictError("This version is already published.")
    account = social_account_service.account(db, tenant_id, v.channel)
    if v.channel == "tiktok" and account.get("connected_via") != "socialapi":
        # TikTok's privacy options can change; read them fresh before checking.
        social_account_service.refresh_profile(db, tenant_id, v.channel)
        account = social_account_service.account(db, tenant_id, v.channel)
    errors, _ = _issues(db, tenant_id, v, content, account)
    if errors:
        raise AppError(f"{social_account_service.LABEL[v.channel]}: " + " ".join(errors), 422)
    _approve(db, tenant_id, actor, content)
    return content


def _new_post(db: Session, tenant_id: str, actor: str, v: ContentAsset, when: datetime, zone: str, local: datetime | None) -> ScheduledPost:
    if _active_post(db, tenant_id, str(v.id)) is not None:
        raise ConflictError("This version is already scheduled; reschedule or cancel it instead.")
    post = ScheduledPost(
        tenant_id=tenant_id, content_asset_id=str(v.id), channel=v.channel, scheduled_at=when, status="scheduled",
        retry_count=0, created_by=actor,
        extra_metadata={"timezone": zone, "local_time": (local or when.astimezone(zoneinfo.ZoneInfo(zone)).replace(tzinfo=None)).isoformat(timespec="minutes"),
                        "attempts": []},
    )
    db.add(post)
    db.flush()
    return post


def schedule_version(db: Session, tenant_id: str, actor: str, version_id: str, local: datetime, tz: str | None,
                     now: datetime | None = None) -> dict[str, Any]:
    v = _version(db, tenant_id, version_id, lock=True)
    when, zone = to_utc(db, tenant_id, local, tz)
    _check_time(when, now)
    content = _ready(db, tenant_id, actor, v)
    post = _new_post(db, tenant_id, actor, v, when, zone, local)
    _audit(db, tenant_id, actor, "scheduled", str(content.id), version_id=version_id, platform=v.channel, at=when, timezone=zone)
    return post_dict(post, v)


def schedule_bulk(db: Session, tenant_id: str, actor: str, content_id: str, items: list[Any], now: datetime | None = None) -> dict[str, Any]:
    """All-or-nothing: every item is validated before any post is created."""
    _content(db, tenant_id, content_id)
    planned = []
    for item in items:
        v = _version(db, tenant_id, item.version_id, lock=True)
        if _meta(v).get("organic_content_id") != str(content_id):
            raise AppError("A version doesn't belong to this content.", 422)
        when, zone = to_utc(db, tenant_id, item.scheduled_at_local, item.timezone)
        _check_time(when, now)
        _ready(db, tenant_id, actor, v)
        if _active_post(db, tenant_id, str(v.id)) is not None:
            raise ConflictError(f"The {v.channel} version is already scheduled.")
        planned.append((v, when, zone, item.scheduled_at_local))
    for v, when, zone, local in planned:
        _new_post(db, tenant_id, actor, v, when, zone, local)
    _audit(db, tenant_id, actor, "scheduled", content_id, platforms=[p[0].channel for p in planned])
    return get_content(db, tenant_id, content_id)


def publish_now(db: Session, tenant_id: str, actor: str, version_id: str) -> dict[str, Any]:
    from app.services.scheduler_service import run_soon

    v = _version(db, tenant_id, version_id, lock=True)
    content = _ready(db, tenant_id, actor, v)
    zone = tenant_tz(db, tenant_id)
    post = _new_post(db, tenant_id, actor, v, _now(), zone, None)
    md = dict(post.extra_metadata or {})
    md["publish_now"] = True
    post.extra_metadata = md
    _audit(db, tenant_id, actor, "publish_now", str(content.id), version_id=version_id, platform=v.channel)
    post_id = str(post.id)
    run_soon(publish_post_job, post_id, db=db, name=f"organic_publish:{post_id}")
    db.refresh(post)
    return post_dict(post, v)


def cancel(db: Session, tenant_id: str, actor: str, post_id: str) -> dict[str, Any]:
    post = _post(db, tenant_id, post_id, lock=True)
    if post.status not in ("scheduled", "pending"):
        raise ConflictError(f"A {post.status} post can't be cancelled.")
    post.status = "cancelled"
    v = db.get(ContentAsset, post.content_asset_id)
    _audit(db, tenant_id, actor, "cancelled", _meta(v).get("organic_content_id", "") if v else "", post_id=post_id)
    return post_dict(post, v)


def reschedule(db: Session, tenant_id: str, actor: str, post_id: str, local: datetime, tz: str | None, now: datetime | None = None) -> dict[str, Any]:
    post = _post(db, tenant_id, post_id, lock=True)
    if post.status not in ("scheduled", "pending", "failed"):
        raise ConflictError(f"A {post.status} post can't be rescheduled.")
    when, zone = to_utc(db, tenant_id, local, tz)
    _check_time(when, now)
    v = _version(db, tenant_id, str(post.content_asset_id), lock=True)
    if post.status == "failed":
        other = _active_post(db, tenant_id, str(v.id))
        if other is not None and str(other.id) != post_id:
            raise ConflictError("This version is already scheduled again.")
        _ready(db, tenant_id, actor, v)
    before = post.scheduled_at
    post.scheduled_at = when
    post.status = "scheduled"
    post.error_message = None
    md = dict(post.extra_metadata or {})
    md.update({"timezone": zone, "local_time": local.isoformat(timespec="minutes"), "next_attempt_at": None, "ref": None})
    post.extra_metadata = md
    _audit(db, tenant_id, actor, "rescheduled", _meta(v).get("organic_content_id", ""), post_id=post_id, before=before, at=when)
    return post_dict(post, v)


def retry(db: Session, tenant_id: str, actor: str, post_id: str) -> dict[str, Any]:
    from app.services.scheduler_service import run_soon

    post = _post(db, tenant_id, post_id, lock=True)
    if post.status != "failed":
        raise ConflictError("Only a failed post can be retried.")
    v = _version(db, tenant_id, str(post.content_asset_id), lock=True)
    other = _active_post(db, tenant_id, str(v.id))
    if other is not None:
        raise ConflictError("This version is already scheduled again.")
    _ready(db, tenant_id, actor, v)
    post.status = "scheduled"
    post.scheduled_at = _now()
    post.error_message = None
    post.retry_count = 0
    md = dict(post.extra_metadata or {})
    md.update({"next_attempt_at": None, "ref": None, "publishing_started_at": None})
    post.extra_metadata = md
    _audit(db, tenant_id, actor, "retried", _meta(v).get("organic_content_id", ""), post_id=post_id)
    run_soon(publish_post_job, post_id, db=db, name=f"organic_publish:{post_id}")
    db.refresh(post)
    return post_dict(post, v)


# ---------------------------------------------------------------------------
# Calendar / history / summary
# ---------------------------------------------------------------------------
def _local_day(tz: str) -> Any:
    return cast(func.timezone(tz, ScheduledPost.scheduled_at), Date)


def _with_versions(db: Session, tenant_id: str, posts: list[ScheduledPost]) -> list[dict[str, Any]]:
    ids = list({str(p.content_asset_id) for p in posts})
    versions = {str(v.id): v for v in db.query(ContentAsset).filter(ContentAsset.tenant_id == tenant_id, ContentAsset.id.in_(ids))} if ids else {}
    return [post_dict(p, versions.get(str(p.content_asset_id))) for p in posts]


def calendar(db: Session, tenant_id: str, start: date, end: date) -> dict[str, Any]:
    if end < start or (end - start).days > 62:
        raise AppError("The calendar range must be 0-62 days.", 422)
    tz = tenant_tz(db, tenant_id)
    day = _local_day(tz)
    posts = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.tenant_id == tenant_id, ScheduledPost.status.in_(("pending", "scheduled", "publishing", "published", "failed")),
                day >= start, day <= end)
        .order_by(ScheduledPost.scheduled_at, ScheduledPost.id)
        .all()
    )
    rows = _with_versions(db, tenant_id, posts)
    zone = zoneinfo.ZoneInfo(tz)
    days: dict[date, list[dict[str, Any]]] = {start + timedelta(days=i): [] for i in range((end - start).days + 1)}
    for r in rows:
        d = r["scheduled_at"].astimezone(zone).date()
        if d in days:
            days[d].append(r)
    return {"timezone": tz, "start": start, "end": end, "days": [{"date": d, "posts": p} for d, p in days.items()]}


def history(db: Session, tenant_id: str, status: str | None, platform: str | None, page: int, page_size: int = 25) -> dict[str, Any]:
    q = db.query(ScheduledPost).join(ContentAsset, ContentAsset.id == ScheduledPost.content_asset_id).filter(
        ScheduledPost.tenant_id == tenant_id, ContentAsset.tenant_id == tenant_id, ContentAsset.format == FORMAT,
        ScheduledPost.status.in_((status,) if status else ("published", "failed", "cancelled")),
    )
    if platform:
        q = q.filter(ScheduledPost.channel == platform)
    count = q.with_entities(func.count(ScheduledPost.id)).scalar() or 0
    posts = q.order_by(func.coalesce(ScheduledPost.published_at, ScheduledPost.scheduled_at).desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"count": int(count), "items": _with_versions(db, tenant_id, posts)}


def summary(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.services.scheduler_service import get_scheduler_status

    now = _now()
    base = db.query(ScheduledPost).join(ContentAsset, ContentAsset.id == ScheduledPost.content_asset_id).filter(
        ScheduledPost.tenant_id == tenant_id, ContentAsset.format == FORMAT)
    scheduled_7d = base.filter(ScheduledPost.status == "scheduled", ScheduledPost.scheduled_at <= now + timedelta(days=7)).count()
    published_30d = base.filter(ScheduledPost.status == "published", ScheduledPost.published_at >= now - timedelta(days=30)).count()
    failed = base.filter(ScheduledPost.status == "failed").count()
    by_platform: dict[str, dict[str, int]] = {p: {"scheduled": 0, "published_30d": 0, "failed": 0} for p in PLATFORMS}
    for channel, status_, n in (
        base.filter(or_(ScheduledPost.status.in_(("scheduled", "failed")),
                        (ScheduledPost.status == "published") & (ScheduledPost.published_at >= now - timedelta(days=30))))
        .with_entities(ScheduledPost.channel, ScheduledPost.status, func.count(ScheduledPost.id))
        .group_by(ScheduledPost.channel, ScheduledPost.status)
    ):
        key = {"published": "published_30d"}.get(status_, status_)
        if channel in by_platform:
            by_platform[channel][key] = int(n)
    awaiting = db.query(func.count(OrganicContent.id)).filter(OrganicContent.tenant_id == tenant_id, OrganicContent.status == "needs_approval").scalar()
    upcoming = base.filter(ScheduledPost.status.in_(("scheduled", "publishing"))).order_by(ScheduledPost.scheduled_at).limit(10).all()
    recent = base.filter(ScheduledPost.status.in_(("published", "failed"))).order_by(
        func.coalesce(ScheduledPost.published_at, ScheduledPost.scheduled_at).desc()).limit(5).all()
    sched = get_scheduler_status()
    return {
        "timezone": tenant_tz(db, tenant_id), "scheduled_next_7d": scheduled_7d, "published_30d": published_30d, "failed_open": failed,
        "awaiting_approval": int(awaiting or 0), "by_platform": by_platform,
        "upcoming": _with_versions(db, tenant_id, upcoming), "recent": _with_versions(db, tenant_id, recent),
        "scheduler": {"running": bool(sched.get("running")), "publishes": "publish_tasks" in (sched.get("jobs") or [])},
    }


# ---------------------------------------------------------------------------
# Publishing (the every-minute job + publish now)
# ---------------------------------------------------------------------------
def _media_item(m: MediaAsset) -> MediaItem:
    # Lazy: the public URL check and the file read happen only if the
    # platform needs them (Instagram fetches URLs; Facebook uploads bytes).
    def url() -> str:
        return media_service.platform_url(m)

    def read() -> bytes:
        return media_service.read_bytes(m)

    return MediaItem(str(m.id), m.kind, m.mime, int(m.bytes), m.width, m.height, m.duration_ms, public_url=url, read=read)


def _payload(db: Session, tenant_id: str, v: ContentAsset, content: OrganicContent) -> PostPayload:
    md = _meta(v)
    cur = _current(v)
    media = _media_safe(db, tenant_id, list(v.media_urls or []))
    items = [_media_item(m) for m in media]
    link = content.link_url
    text_ = oa.compose(v.channel, cur.get("caption") or "", list(cur.get("hashtags") or []), cur.get("cta"), link, bool(media))
    return PostPayload(text=text_, link_url=link if not media else None, media=items, post_format=md.get("post_format") or "post",
                       title=cur.get("title"), options=dict(md.get("platform_options") or {}))


def _attempt(post: ScheduledPost, outcome: str, detail: str | None = None) -> None:
    md = dict(post.extra_metadata or {})
    md["attempts"] = [*list(md.get("attempts") or [])[-9:], {"at": _now().isoformat(), "outcome": outcome, **({"detail": detail[:300]} if detail else {})}]
    post.extra_metadata = md


def _succeed(db: Session, post: ScheduledPost, v: ContentAsset | None, external_id: str | None, url: str | None) -> None:
    post.status = "published"
    post.published_at = _now()
    post.external_post_id = external_id
    post.external_url = url
    post.error_message = None
    md = dict(post.extra_metadata or {})
    md.update({"ref": None, "next_attempt_at": None})
    post.extra_metadata = md
    _attempt(post, "published")
    if v is not None:
        v.status = "published"
    _audit(db, str(post.tenant_id), None, "published", (_meta(v).get("organic_content_id") if v else "") or "", post_id=str(post.id),
           platform=post.channel, external_id=external_id)
    logger.info("organic_post_published", tenant_id=str(post.tenant_id), post_id=str(post.id), platform=post.channel)


def _fail(db: Session, post: ScheduledPost, message: str, v: ContentAsset | None) -> None:
    from app.workflow_engine.actions import _notifications, notify_role

    post.status = "failed"
    post.error_message = message[:1000]
    md = dict(post.extra_metadata or {})
    md.update({"next_attempt_at": None})
    post.extra_metadata = md
    _attempt(post, "failed", message)
    tenant_id = str(post.tenant_id)
    title = f"{social_account_service.LABEL.get(post.channel, post.channel)} post failed"
    body = f"{message[:400]}"
    link = "/marketing/organic/history"
    notify_role(db, tenant_id, "owner", "organic_publish_failed", title, body, link, {"post_id": str(post.id)})
    if post.created_by:
        owners = db.execute(text(
            "SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE ur.user_id = :u AND ur.tenant_id = :t AND r.type = 'owner'"),
            {"u": str(post.created_by), "t": tenant_id}).first()
        if owners is None:
            from sqlalchemy import insert

            db.execute(insert(_notifications).values(tenant_id=tenant_id, user_id=str(post.created_by), type="organic_publish_failed",
                                                     title=title, body=body, link_url=link, severity="info", metadata={"post_id": str(post.id)}))
    _audit(db, tenant_id, None, "publish_failed", (_meta(v).get("organic_content_id") if v else "") or "", post_id=str(post.id),
           platform=post.channel, error=message[:300])
    logger.warning("organic_post_failed", tenant_id=tenant_id, post_id=str(post.id), platform=post.channel)


def _retry_later(db: Session, post: ScheduledPost, message: str, v: ContentAsset | None) -> None:
    if (post.retry_count or 0) >= len(RETRY_MINUTES):
        _fail(db, post, f"{message} (gave up after {len(RETRY_MINUTES)} retries)", v)
        return
    wait = RETRY_MINUTES[post.retry_count or 0]
    post.retry_count = (post.retry_count or 0) + 1
    post.status = "scheduled"
    md = dict(post.extra_metadata or {})
    md["next_attempt_at"] = (_now() + timedelta(minutes=wait)).isoformat()
    md["publishing_started_at"] = None
    post.extra_metadata = md
    _attempt(post, "retry", message)
    db.commit()


def _handle_error(db: Session, post: ScheduledPost, v: ContentAsset | None, exc: Exception) -> None:
    if isinstance(exc, SocialError):
        if exc.auth:
            social_account_service.mark_expired(db, str(post.tenant_id), post.channel, exc.message)
            _fail(db, post, f"{exc.message} Reconnect the account in Integrations.", v)
        elif exc.transient:
            _retry_later(db, post, exc.message, v)
        else:
            _fail(db, post, exc.message, v)
    elif isinstance(exc, AppError):
        _fail(db, post, str(exc.detail), v)
    else:
        # Unknown failure: never retried automatically (it may have posted).
        logger.exception("organic_publish_unexpected", post_id=str(post.id))
        _fail(db, post, f"Unexpected error ({type(exc).__name__}); check the platform before retrying.", v)


def publish_one(db: Session, post: ScheduledPost) -> None:
    """Publishes a post that is already marked 'publishing' (committed)."""
    tenant_id = str(post.tenant_id)
    v = db.query(ContentAsset).filter(ContentAsset.id == post.content_asset_id, ContentAsset.tenant_id == tenant_id).first()
    try:
        if v is None:
            raise AppError("The post's content was deleted.", 409)
        content = _content(db, tenant_id, _meta(v)["organic_content_id"])
        conn = social_account_service.connection(db, tenant_id, post.channel)
        md = dict(post.extra_metadata or {})
        md["via"] = conn.get("via") or "direct"  # SPEC-BE-104: which path published it (results import)
        post.extra_metadata = md
        result = adapter(post.channel, conn.get("via")).publish(conn["fields"], _payload(db, tenant_id, v, content))
    except Exception as exc:  # noqa: BLE001 - classified below
        _handle_error(db, post, v, exc)
        return
    if result.state == "processing":
        md = dict(post.extra_metadata or {})
        md.update({"ref": result.ref, "next_attempt_at": (_now() + timedelta(seconds=POLL_SECONDS)).isoformat()})
        post.extra_metadata = md
        _attempt(post, "processing")
        db.commit()
        return
    _succeed(db, post, v, result.external_id, result.external_url)


def _poll_one(db: Session, post: ScheduledPost) -> None:
    tenant_id = str(post.tenant_id)
    v = db.query(ContentAsset).filter(ContentAsset.id == post.content_asset_id, ContentAsset.tenant_id == tenant_id).first()
    md = dict(post.extra_metadata or {})
    started = md.get("publishing_started_at")
    if started and _now() - datetime.fromisoformat(started) > STUCK_AFTER:
        _fail(db, post, "Publishing state unknown — check the platform before retrying.", v)
        return
    try:
        conn = social_account_service.connection(db, tenant_id, post.channel)
        result = adapter(post.channel, md.get("via")).poll(conn["fields"], dict(md.get("ref") or {}))
    except SocialError as exc:
        if exc.transient:
            md["next_attempt_at"] = (_now() + timedelta(seconds=POLL_SECONDS * 2)).isoformat()
            post.extra_metadata = md
            db.commit()
            return
        _handle_error(db, post, v, exc)
        return
    except Exception as exc:  # noqa: BLE001
        _handle_error(db, post, v, exc)
        return
    if result.state == "processing":
        md["ref"] = result.ref
        md["next_attempt_at"] = (_now() + timedelta(seconds=POLL_SECONDS)).isoformat()
        post.extra_metadata = md
        db.commit()
        return
    _succeed(db, post, v, result.external_id, result.external_url)


def _due(post: ScheduledPost, now: datetime) -> bool:
    nxt = (post.extra_metadata or {}).get("next_attempt_at")
    return not nxt or datetime.fromisoformat(nxt) <= now


def _claim(db: Session, post: ScheduledPost, now: datetime) -> None:
    post.status = "publishing"
    md = dict(post.extra_metadata or {})
    md["publishing_started_at"] = now.isoformat()
    post.extra_metadata = md
    db.commit()  # visible to other workers before the platform call


def run_due(db: Session, now: datetime | None = None, limit: int = 20) -> dict[str, int]:
    """One pass of the publishing job. Due scheduled posts are claimed with
    FOR UPDATE SKIP LOCKED (two concurrent runs never take the same post),
    marked 'publishing' and committed before the platform call. Async posts
    are polled; a post stuck in 'publishing' without a poll ref for over 30
    minutes is failed ("state unknown") rather than sent twice."""
    now = now or _now()
    stats = {"published": 0, "failed": 0, "retry": 0, "processing": 0}
    due = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.status == "scheduled", ScheduledPost.scheduled_at <= now)
        .order_by(ScheduledPost.scheduled_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    claimed = [p for p in due if _due(p, now) and _is_organic(db, p)]
    for p in claimed:
        _claim(db, p, now)
    for p in claimed:
        publish_one(db, p)
        stats[_bucket(p)] += 1
    polling = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.status == "publishing")
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    for p in polling:
        md = p.extra_metadata or {}
        if md.get("ref"):
            if _due(p, now):
                _poll_one(db, p)
                stats[_bucket(p)] += 1
        else:
            started = md.get("publishing_started_at")
            if started and now - datetime.fromisoformat(started) > STUCK_AFTER and _is_organic(db, p):
                v = db.get(ContentAsset, p.content_asset_id)
                _fail(db, p, "Publishing state unknown — check the platform before retrying.", v)
                stats["failed"] += 1
    db.commit()
    if any(stats.values()):
        logger.info("organic_publish_pass", **stats)
    return stats


def _bucket(p: ScheduledPost) -> str:
    if p.status == "published":
        return "published"
    if p.status == "failed":
        return "failed"
    if p.status == "publishing":
        return "processing"
    return "retry"


def _is_organic(db: Session, post: ScheduledPost) -> bool:
    fmt = db.query(ContentAsset.format).filter(ContentAsset.id == post.content_asset_id).scalar()
    return fmt == FORMAT


def publish_post_job(db: Session, post_id: str) -> None:
    """Publish one post now (publish-now / retry), via scheduler_service.run_soon."""
    post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).with_for_update(skip_locked=True).first()
    if post is None or post.status != "scheduled":
        return
    _claim(db, post, _now())
    publish_one(db, post)
    db.commit()


# ---------------------------------------------------------------------------
# Insights as AI feedback (SPEC-BE-081). Computed from imported post results
# (SPEC-BE-078), never generated or estimated. Engagements = likes + comments
# + shares + saves (the known ones), engagement rate = engagements /
# impressions x 100: the definitions of Organic Analytics. A post without
# impressions or engagements has no rate and is left out.
# ---------------------------------------------------------------------------
INSIGHT_MIN_POSTS = 3  # per platform
INSIGHT_MIN_BUCKET = 2  # per hour / format
INSIGHT_NO_DATA = "Not enough results yet: insights need at least 3 published posts with imported results on a platform."
PERFORMANCE_MAX_CHARS = 1200
PLATFORM_LABEL = {"facebook": "Facebook", "instagram": "Instagram", "tiktok": "TikTok", "linkedin": "LinkedIn"}
FORMAT_PLURAL = {"post": "single posts", "reel": "reels", "carousel": "carousels", "video": "videos", "story": "stories"}


def _scored_posts(db: Session, tenant_id: str, days: int, tz: str) -> list[dict[str, Any]]:
    from app.services.analytics_service import ENGAGEMENT_METRICS, ORGANIC_EVENT

    rows = list(db.execute(
        text(
            """
            SELECT sp.id::text AS id, sp.channel::text AS platform, sp.external_url, sp.published_at,
                   EXTRACT(HOUR FROM sp.published_at AT TIME ZONE :tz)::int AS hour,
                   ca.variants, ca.selected_variant_index, ca.metadata AS md
            FROM scheduled_posts sp JOIN content_assets ca ON ca.id = sp.content_asset_id AND ca.tenant_id = sp.tenant_id
            WHERE sp.tenant_id = :t AND sp.status = 'published' AND ca.format = :f
              AND sp.published_at >= now() - make_interval(days => :d)"""
        ),
        {"t": tenant_id, "tz": tz, "f": FORMAT, "d": days},
    ))
    if not rows:
        return []
    latest: dict[str, dict[str, float]] = {}
    for r in db.execute(
        text(
            """
            SELECT DISTINCT ON (entity_id, metric) entity_id::text AS id, metric, value
            FROM analytics_events
            WHERE tenant_id = :t AND event_type = :e AND entity_id::text = ANY(:ids)
            ORDER BY entity_id, metric, event_time DESC"""
        ),
        {"t": tenant_id, "e": ORGANIC_EVENT, "ids": [r.id for r in rows]},
    ):
        latest.setdefault(r.id, {})[r.metric] = float(r.value)
    out = []
    for r in rows:
        m = latest.get(r.id, {})
        known = [m[k] for k in ENGAGEMENT_METRICS if k in m]
        impressions = m.get("impressions")
        if not known or not impressions:
            continue
        engagements = float(sum(known))
        variants = r.variants or [{}]
        idx = r.selected_variant_index if r.selected_variant_index is not None and r.selected_variant_index < len(variants) else 0
        current = variants[idx] or {}
        out.append({
            "post_id": r.id, "platform": r.platform, "post_format": str((r.md or {}).get("post_format") or "post"),
            "excerpt": _excerpt(str(current.get("caption") or ""), 120), "hashtags": len(current.get("hashtags") or []),
            "hour": int(r.hour), "engagements": engagements, "impressions": impressions,
            "engagement_rate": round(engagements * 100 / impressions, 2),
            "published_at": r.published_at.astimezone(timezone.utc), "external_url": r.external_url,
        })
    return out


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2)


def _groups(posts: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Buckets with >= INSIGHT_MIN_BUCKET posts, best average rate first."""
    buckets: dict[Any, list[float]] = {}
    for p in posts:
        buckets.setdefault(p[key], []).append(p["engagement_rate"])
    rows = [{"key": k, "avg": _avg(v), "posts": len(v)} for k, v in buckets.items() if len(v) >= INSIGHT_MIN_BUCKET]
    return sorted(rows, key=lambda x: (-x["avg"], -x["posts"], str(x["key"])))


def insights(db: Session, tenant_id: str, days: int = 60) -> dict[str, Any]:
    tz = tenant_tz(db, tenant_id)
    posts = _scored_posts(db, tenant_id, days, tz)
    platforms_out: list[dict[str, Any]] = []
    first: list[dict[str, str]] = []  # format / hour lines (the most useful)
    later: list[dict[str, str]] = []  # hashtags, averages
    for platform in PLATFORMS:
        rows = [p for p in posts if p["platform"] == platform]
        if len(rows) < INSIGHT_MIN_POSTS:
            continue
        label = PLATFORM_LABEL[platform]
        hours = [{"hour": h["key"], "label": f"{h['key']:02d}:00–{(h['key'] + 1) % 24:02d}:00", "avg_engagement_rate": h["avg"], "posts": h["posts"]}
                 for h in _groups(rows, "hour")[:3]]
        formats = [{"post_format": f["key"], "avg_engagement_rate": f["avg"], "posts": f["posts"]} for f in _groups(rows, "post_format")]
        ranked = sorted(rows, key=lambda p: -p["engagement_rate"])
        third = max(1, len(ranked) // 3)
        top_tags = _avg([float(p["hashtags"]) for p in ranked[:third]])
        bottom_tags = _avg([float(p["hashtags"]) for p in ranked[-third:]])
        avg = _avg([p["engagement_rate"] for p in rows])
        platforms_out.append({
            "platform": platform, "posts_with_results": len(rows), "avg_engagement_rate": avg, "best_hours": hours,
            "best_format": formats[0] if formats else None, "formats": formats,
            "hashtags_top_third": top_tags, "hashtags_bottom_third": bottom_tags,
        })
        if len(formats) >= 2:
            best, worst = formats[0], formats[-1]
            first.append({"platform": platform, "text": (
                f"{label}: {FORMAT_PLURAL.get(best['post_format'], best['post_format'])} averaged {best['avg_engagement_rate']:.1f}% engagement "
                f"vs {worst['avg_engagement_rate']:.1f}% for {FORMAT_PLURAL.get(worst['post_format'], worst['post_format'])} "
                f"({best['posts'] + worst['posts']} posts).")})
        if hours:
            h = hours[0]
            first.append({"platform": platform, "text": (
                f"{label} posts published {h['label']} did best ({h['avg_engagement_rate']:.1f}% average, {h['posts']} posts).")})
        if len(ranked) >= 2 * INSIGHT_MIN_POSTS and abs(top_tags - bottom_tags) >= 1:
            later.append({"platform": platform, "text": (
                f"{label}: the best-performing third used about {top_tags:.0f} hashtags, the lowest third about {bottom_tags:.0f}.")})
        later.append({"platform": platform, "text": f"{label}: {len(rows)} posts with results averaged {avg:.1f}% engagement."})
    eligible = [p for p in posts if any(x["platform"] == p["platform"] for x in platforms_out)]
    ranked_all = sorted(eligible, key=lambda p: -p["engagement_rate"])
    public = ("post_id", "platform", "post_format", "excerpt", "engagement_rate", "engagements", "impressions", "published_at", "external_url")
    has_data = bool(platforms_out)
    return {
        "has_data": has_data,
        "reason": None if has_data else INSIGHT_NO_DATA,
        "days": days,
        "timezone": tz,
        "platforms": platforms_out,
        "top_posts": [{k: p[k] for k in public} for p in ranked_all[:5]],
        # Lowest first, never repeating a top post.
        "bottom_posts": [{k: p[k] for k in public} for p in ranked_all[5:][::-1][:3]],
        "lines": (first + later)[:6],
        "generated_at": _now(),
    }


def performance_context(db: Session, tenant_id: str, platforms: list[str]) -> tuple[str, bool]:
    """The <performance> block for the AI copy prompts: insight lines for these
    platforms plus up to 3 top-post excerpts. ("", False) without data."""
    data = insights(db, tenant_id, 60)
    if not data["has_data"]:
        return "", False
    lines = [f"- {line['text']}" for line in data["lines"] if line["platform"] in platforms]
    examples = [p for p in data["top_posts"] if p["platform"] in platforms][:3]
    if not lines and not examples:
        return "", False
    parts = lines + (["Examples that performed well (learn the angle, don't copy):"] if examples else []) + [
        f'- [{p["platform"]}, {p["engagement_rate"]:.1f}%] "{p["excerpt"]}"' for p in examples
    ]
    text_ = "\n".join(parts)
    return text_[:PERFORMANCE_MAX_CHARS], True
