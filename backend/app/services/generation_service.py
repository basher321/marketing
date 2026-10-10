"""Photo and video generation (SPEC-BE-077).

prompt -> provider (creative_providers, in the company's order for the kind)
-> media library (SPEC-BE-074) -> preview -> regenerate / edit -> approve ->
use in an organic post (SPEC-BE-076).

Jobs run in the background (scheduler_service.run_soon; inline when the
scheduler is off). Images finish in one call. Video starts a provider job,
stores its ref, and polls every POLL_INTERVAL_S up to VIDEO_TIMEOUT_S; a
running job whose process died is resumed by workers/tasks/generation_tasks.
Provider fallback only happens before a job starts (not set up, or a start
error); a started job that fails reports its error.

Durations and ratios are what the provider really makes; the job's
`effective` and `notes` say so (e.g. "15 s requested -> 8 s generated").
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.ai import creative_providers as cp
from app.ai.moderation import moderate_text
from app.ai.prompts import organic_adapter as oa
from app.ai.retrieval import get_brand_voice
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.generation import GenerationJob
from app.models.media import MediaAsset
from app.services import media_service

logger = structlog.get_logger(__name__)

POLL_INTERVAL_S = 10.0
VIDEO_TIMEOUT_S = 600
STALE_AFTER = timedelta(minutes=2)
LABELS = {"openai_image": "OpenAI images", "gemini_image": "Gemini images", "gemini_video": "Google Veo", "openai_video": "OpenAI Sora",
          "openai_slideshow": "OpenAI slideshow"}
SETUP_HINT = "Choose an image or video model for OpenAI or Gemini in Integrations › AI Models (or add an MCP creative tool)."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(v: datetime | None) -> datetime | None:
    return v.astimezone(timezone.utc) if v else None


def _job(db: Session, tenant_id: str, job_id: str, lock: bool = False) -> GenerationJob:
    q = db.query(GenerationJob).filter(GenerationJob.id == job_id, GenerationJob.tenant_id == tenant_id)
    job = (q.with_for_update() if lock else q).first()
    if job is None:
        raise NotFoundError("Generation not found.")
    return job


def job_dict(db: Session, job: GenerationJob) -> dict[str, Any]:
    media = db.get(MediaAsset, job.result_media_id) if job.result_media_id else None
    eff = dict(job.effective or {})
    return {
        "id": str(job.id), "kind": job.kind, "status": job.status, "request": dict(job.request or {}),
        "effective": {k: v for k, v in eff.items() if k in ("duration_s", "aspect_ratio", "provider")},
        "provider": job.provider, "model": job.model, "attempts": list(job.attempts or []),
        "media": media_service.media_dict(media) if media is not None and media.deleted_at is None else None,
        "parent_job_id": str(job.parent_job_id) if job.parent_job_id else None, "approved_at": _utc(job.approved_at),
        "cost_cents": int(job.cost_cents or 0), "error": job.error, "notes": list(eff.get("notes") or []),
        "content_id": eff.get("content_id") or (job.request or {}).get("organic_content_id"),
        "created_at": _utc(job.created_at), "finished_at": _utc(job.finished_at),
    }


def get_job(db: Session, tenant_id: str, job_id: str) -> dict[str, Any]:
    return job_dict(db, _job(db, tenant_id, job_id))


def list_jobs(db: Session, tenant_id: str, kind: str | None, status: str | None, page: int, page_size: int = 24) -> dict[str, Any]:
    q = db.query(GenerationJob).filter(GenerationJob.tenant_id == tenant_id)
    if kind:
        q = q.filter(GenerationJob.kind == kind)
    if status:
        q = q.filter(GenerationJob.status == status)
    count = q.with_entities(func.count(GenerationJob.id)).scalar() or 0
    rows = q.order_by(GenerationJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"count": int(count), "items": [job_dict(db, j) for j in rows]}


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------
def _providers(db: Session, tenant_id: str, kind: str, only: list[str] | None = None) -> list[Any]:
    """The ready providers for a kind, in the company order. A request's
    `providers` list (SPEC-BE-092/093: Command Chat's chain, Google then
    OpenAI) replaces that order with exactly those providers, tried in that
    order; regenerate/edit inherit it."""
    if only:
        pinned = [p for p in (cp.provider(k) for k in only) if p is not None and kind in p.kinds]
        return [p for p in pinned if p.available(db, tenant_id)]
    return [p for p in cp.ordered(db, tenant_id, kind) if p.available(db, tenant_id)]


def readiness(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.services.ai_model_service import image_model, video_model

    out: dict[str, Any] = {"image": [], "video": []}
    for kind in ("image", "video"):
        for p in cp.ordered(db, tenant_id, kind):
            ready = p.available(db, tenant_id)
            base = p.key.split("_")[0]
            model = (image_model if kind == "image" else video_model)(db, tenant_id, base) if base in ("openai", "gemini") else None
            durations = list(getattr(p, "DURATIONS", ())) if kind == "video" else []
            ratios = list(getattr(p, "RATIOS", ()) or getattr(p, "SIZES", {}) or ())
            out[kind].append({
                "key": p.key, "label": LABELS.get(p.key, p.key.replace("mcp:", "MCP: ")), "ready": ready,
                "reason": None if ready else ("Save a key and choose a model in AI Models." if base in ("openai", "gemini") else "Turned off or not set up."),
                "model": model, "durations": durations, "aspect_ratios": [str(r) for r in ratios],
                "reference_images": p.key in ("openai_image", "gemini_image", "gemini_video", "openai_video"),
            })
    out["image_ready"] = any(p["ready"] for p in out["image"])
    out["video_ready"] = any(p["ready"] for p in out["video"])
    out["setup_hint"] = SETUP_HINT
    return out


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
def _video_estimate(provider: Any, req: dict[str, Any]) -> int:
    """What this provider would really make for the request: Veo/Sora are
    priced per generated second at the length they support (Veo max 8 s);
    the OpenAI slideshow is priced per image (SPEC-BE-093 amendment)."""
    creq = cp.CreativeRequest(kind="video", aspect_ratio=req.get("aspect_ratio"), duration_s=int(req.get("duration_s") or 8))
    seconds = int(provider.supported(creq).get("duration_s") or creq.duration_s or 8)
    if provider.key == "openai_slideshow":
        return int(provider.frames(seconds)) * cp.IMAGE_COST_CENTS["openai_image"]
    return cp.VIDEO_CENTS_PER_SECOND.get(provider.key, max(cp.VIDEO_CENTS_PER_SECOND.values())) * seconds


def _estimate(kind: str, req: dict[str, Any], count: int, providers: list[Any]) -> int:
    """Worst case over the providers that may run (any of them can end up
    making it), not the requested length at the highest per-second rate."""
    if kind == "image":
        return max(cp.IMAGE_COST_CENTS.values()) * count
    return max((_video_estimate(p, req) for p in providers), default=0)


def _cost_guard(db: Session, tenant_id: str, estimate: int) -> None:
    """The company's daily AI limit (tenants.llm_daily_cap_cents, shared
    with the AI Autopilot): last 24 h of runs + generations + this estimate."""
    cap = db.execute(text("SELECT llm_daily_cap_cents FROM tenants WHERE id = :t"), {"t": tenant_id}).scalar() or 0
    if cap <= 0:
        return
    since = _now() - timedelta(days=1)
    spent = db.execute(text("SELECT COALESCE(SUM(cost_cents), 0) FROM ai_campaign_runs WHERE tenant_id = :t AND created_at >= :d"),
                       {"t": tenant_id, "d": since}).scalar() or 0
    spent += db.query(func.coalesce(func.sum(GenerationJob.cost_cents), 0)).filter(
        GenerationJob.tenant_id == tenant_id, GenerationJob.created_at >= since).scalar() or 0
    if int(spent) + estimate > cap:
        left = max(0, cap - int(spent))
        raise AppError(f"Today's AI spending limit is reached: {left / 100:.2f} USD left of {cap / 100:.2f} (estimate {estimate / 100:.2f}).", 429)


def _moderate(db: Session, tenant_id: str, prompt: str) -> None:
    passed, hits = moderate_text(prompt, get_brand_voice(db, tenant_id).forbidden_terms)
    if not passed:
        raise AppError(f"The prompt contains blocked words: {', '.join(hits)}.", 422)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
def _normalise(kind: str, req: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in req.items() if v not in (None, "", [])}
    platform = out.get("target_platform")
    if not out.get("aspect_ratio"):
        if platform:
            fmt = "video" if kind == "video" and platform == "tiktok" else ("reel" if kind == "video" and platform in ("instagram", "facebook") else oa.DEFAULT_FORMAT[platform])
            out["aspect_ratio"] = oa.PLATFORM_RULES[platform].preferred_ratio.get(fmt) or ("9:16" if kind == "video" else "1:1")
        else:
            out["aspect_ratio"] = "9:16" if kind == "video" else "1:1"
    if kind == "video":
        out["duration_s"] = int(out.get("duration_s") or 8)
    return out


def start(db: Session, tenant_id: str, actor: str | None, kind: str, req: dict[str, Any], *, count: int = 1,
          organic_content_id: str | None = None, parent_job_id: str | None = None, run: bool = True) -> dict[str, Any]:
    """Validate, check limits and queue job(s). Returns the first job; all
    job ids are in jobs_started (photo count > 1)."""
    if kind not in ("image", "video"):
        raise AppError("Unknown generation kind.", 422)
    req = _normalise(kind, req)
    prompt = str(req.get("prompt") or "").strip()
    if len(prompt) < 3:
        raise AppError("Write a prompt for the generation.", 422)
    _moderate(db, tenant_id, prompt + " " + str(req.get("style") or ""))
    refs = [str(i) for i in req.get("reference_media_ids") or []]
    for m in media_service.media_rows(db, tenant_id, refs):
        if m.kind != "image":
            raise AppError("Reference media must be images.", 422)
    if req.get("product_ids"):
        from app.services.organic_service import products

        products(db, tenant_id, ids=[str(p) for p in req["product_ids"]])
    ready = _providers(db, tenant_id, kind, req.get("providers"))
    if not ready:
        what = "a video" if kind == "video" else "an image"
        raise ConflictError(f"Set up {what} model in Integrations › AI Models first.")
    _cost_guard(db, tenant_id, _estimate(kind, req, count, ready))
    if organic_content_id:
        req["organic_content_id"] = organic_content_id
    jobs = []
    for _ in range(count):
        job = GenerationJob(tenant_id=tenant_id, kind=kind, status="queued", request=req, effective={}, attempts=[],
                            parent_job_id=parent_job_id, created_by=actor, cost_cents=0)
        db.add(job)
        db.flush()
        jobs.append(job)
    ids = [str(j.id) for j in jobs]
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action="generation.started", resource_type="generation",
                    resource_id=ids[0], metadata={"kind": kind, "count": count, "parent_job_id": parent_job_id, "prompt": prompt[:200]})
    if run:
        from app.services.scheduler_service import run_soon

        for jid in ids:
            run_soon(run_job, jid, db=db, name=f"generation:{jid}")
    first = db.get(GenerationJob, ids[0])
    out = job_dict(db, first) if first is not None else {"id": ids[0]}
    out["jobs_started"] = ids
    return out


def start_photo(db: Session, tenant_id: str, actor: str, payload: Any) -> list[dict[str, Any]]:
    req = payload.model_dump(exclude={"count"})
    first = start(db, tenant_id, actor, "image", req, count=payload.count)
    return [get_job(db, tenant_id, jid) for jid in first["jobs_started"]]


def start_video(db: Session, tenant_id: str, actor: str, payload: Any) -> list[dict[str, Any]]:
    first = start(db, tenant_id, actor, "video", payload.model_dump())
    return [get_job(db, tenant_id, first["id"])]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def _creative_request(db: Session, job: GenerationJob) -> cp.CreativeRequest:
    req = dict(job.request or {})
    tenant_id = str(job.tenant_id)
    prompt = str(req.get("prompt") or "")
    skus: list[str] = []
    if req.get("product_ids"):
        from app.services.organic_service import products

        rows = products(db, tenant_id, ids=[str(p) for p in req["product_ids"]])
        skus = [r["sku"] for r in rows]
        prompt += " Featuring: " + "; ".join(f"{r['title']} ({r['description'][:120]})" for r in rows)
    if job.kind == "image" and req.get("style"):
        prompt += f" Style: {req['style']}."
    if job.kind == "image":
        prompt += " No text, no logos, no watermarks."
    references: list[tuple[bytes, str]] = []
    for m in media_service.media_rows(db, tenant_id, [str(i) for i in req.get("reference_media_ids") or []]):
        references.append((media_service.read_bytes(m), m.mime))
    return cp.CreativeRequest(kind=job.kind, prompt=prompt.strip(), aspect_ratio=req.get("aspect_ratio"), skus=skus,
                              duration_s=req.get("duration_s"), style=req.get("style") if job.kind == "video" else None,
                              negative_prompt=req.get("negative_prompt"), reference_images=references)


def _notes(req: dict[str, Any], eff: dict[str, Any], provider: str) -> list[str]:
    notes = []
    want, got = req.get("duration_s"), eff.get("duration_s")
    if want and got and int(want) != int(got):
        why = "the longest this provider makes in one clip" if int(got) < int(want) else "the nearest length this provider makes"
        notes.append(f"{want} s requested → {got} s generated ({why}).")
    if req.get("aspect_ratio") and eff.get("aspect_ratio") and req["aspect_ratio"] != eff["aspect_ratio"]:
        notes.append(f"{req['aspect_ratio']} requested → {eff['aspect_ratio']} generated ({LABELS.get(provider, provider)} supports {eff['aspect_ratio']}).")
    return notes


def _attempt(job: GenerationJob, provider: str, outcome: str) -> None:
    job.attempts = [*list(job.attempts or []), {"provider": provider, "outcome": outcome[:300], "at": _now().isoformat()}]


def _fail(db: Session, job: GenerationJob, message: str) -> None:
    job.status = "failed"
    job.error = message[:1000]
    job.finished_at = _now()
    _link_content(db, job, None, message)
    write_audit_log(db, tenant_id=str(job.tenant_id), actor_user_id=None, action="generation.failed", resource_type="generation",
                    resource_id=str(job.id), metadata={"error": message[:300]})
    logger.warning("generation_failed", tenant_id=str(job.tenant_id), job_id=str(job.id), error=message[:200])


def _link_content(db: Session, job: GenerationJob, media_id: str | None, error: str | None) -> None:
    content_id = (job.request or {}).get("organic_content_id")
    if content_id:
        from app.services.organic_service import attach_generated_media

        attach_generated_media(db, str(job.tenant_id), str(content_id), str(job.id), media_id, error)


def _finish(db: Session, job: GenerationJob, result: cp.CreativeResult) -> None:
    db.refresh(job)
    if job.status == "cancelled":
        logger.info("generation_result_discarded", job_id=str(job.id))
        return
    data = result.image if job.kind == "image" else result.video
    prompt = str((job.request or {}).get("prompt") or "")
    media = media_service.store(
        db, str(job.tenant_id), str(job.created_by) if job.created_by else None, data or b"",
        name=f"{'AI photo' if job.kind == 'image' else 'AI video'}: {prompt[:60]}", source="ai_image" if job.kind == "image" else "ai_video",
        generation_job_id=str(job.id), metadata={"prompt": prompt[:2000], "provider": result.provider, "model": result.model}, audit=False,
    )
    job.result_media_id = str(media.id)
    job.provider = result.provider
    job.model = result.model
    job.cost_cents = int(job.cost_cents or 0) + int(result.cost_cents or 0)
    job.status = "succeeded"
    job.error = None
    job.finished_at = _now()
    if job.kind == "image" and media.width and media.height:
        eff = dict(job.effective or {})
        eff.setdefault("aspect_ratio", (job.request or {}).get("aspect_ratio"))
        job.effective = eff
    if result.notes:  # SPEC-BE-094: e.g. "Voiceover added (alloy)." or why there's no sound
        eff = dict(job.effective or {})
        eff["notes"] = [*list(eff.get("notes") or []), *result.notes]
        job.effective = eff
    _attempt(job, result.provider, "succeeded")
    _link_content(db, job, str(media.id), None)
    write_audit_log(db, tenant_id=str(job.tenant_id), actor_user_id=None, action="generation.succeeded", resource_type="generation",
                    resource_id=str(job.id), metadata={"provider": result.provider, "model": result.model, "media_id": str(media.id)})
    logger.info("generation_succeeded", tenant_id=str(job.tenant_id), job_id=str(job.id), provider=result.provider)


def run_job(db: Session, job_id: str) -> None:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).with_for_update(skip_locked=True).first()
    if job is None or job.status != "queued":
        return
    job.status = "running"
    db.commit()
    tenant_id = str(job.tenant_id)
    try:
        creq = _creative_request(db, job)
    except AppError as exc:
        _fail(db, job, str(exc.detail))
        return
    pinned = bool((job.request or {}).get("providers"))
    providers = _providers(db, tenant_id, job.kind, (job.request or {}).get("providers"))
    if job.kind == "image" and pinned:
        # A pinned chain (SPEC-BE-093) records every failed provider, also
        # when a later one succeeds, so the chat can say who made it and why.
        failed: list[tuple[str, str]] = []
        for provider in providers:
            try:
                result = cp.generate(db, tenant_id, creq, [provider])
            except cp.AllProvidersFailed as exc:
                failed += exc.attempts
                for key, err in exc.attempts:
                    _attempt(job, key, err)
                continue
            db.commit()  # _finish refreshes the job; keep the recorded attempts
            _finish(db, job, result)
            return
        _fail(db, job, str(cp.AllProvidersFailed("image", failed)))
        return
    if job.kind == "image":
        try:
            result = cp.generate(db, tenant_id, creq, providers)
        except cp.AllProvidersFailed as exc:
            for key, err in exc.attempts:
                _attempt(job, key, err)
            _fail(db, job, str(exc))
            return
        _finish(db, job, result)
        return
    for provider in providers:
        eff = provider.supported(creq)
        try:
            started = provider.start(db, tenant_id, creq)
        except cp.ProviderFailed as exc:
            _attempt(job, provider.key, f"start failed: {exc}")
            continue
        job.provider = provider.key
        job.effective = {**eff, "provider": provider.key, "notes": _notes(job.request or {}, eff, provider.key),
                         "last_poll_at": _now().isoformat()}
        if isinstance(started, cp.CreativeResult):
            db.commit()  # _finish refreshes the job; keep effective/notes/attempts
            _finish(db, job, started)
            return
        job.provider_ref = started
        _attempt(job, provider.key, "started")
        db.commit()
        # A pinned chain (SPEC-BE-093) moves on when the provider fails while
        # running; the last provider, and unpinned jobs, fail the job as before.
        more = pinned and provider is not providers[-1]
        try:
            _poll_until_done(db, job, provider, fail_job=not more)
        except cp.ProviderFailed:
            job.provider, job.provider_ref = None, None
            db.commit()
            continue
        return
    _fail(db, job, "No video provider could start: " + "; ".join(a["outcome"] for a in job.attempts or []))


def _poll_once(db: Session, job: GenerationJob, provider: Any, fail_job: bool = True) -> bool:
    """True when the job ended (succeeded / failed / cancelled). With
    fail_job=False a provider failure is recorded and re-raised instead, so
    run_job can try the next provider of a pinned chain."""
    db.refresh(job)
    if job.status != "running":
        return True
    try:
        result = provider.poll(db, str(job.tenant_id), str(job.provider_ref))
    except cp.ProviderFailed as exc:
        _attempt(job, provider.key, str(exc))
        if not fail_job:
            db.commit()
            raise
        _fail(db, job, f"{LABELS.get(provider.key, provider.key)}: {exc}")
        return True
    if result is None:
        eff = dict(job.effective or {})
        eff["last_poll_at"] = _now().isoformat()
        job.effective = eff
        db.commit()
        return False
    _finish(db, job, result)
    return True


def _poll_until_done(db: Session, job: GenerationJob, provider: Any, fail_job: bool = True) -> None:
    deadline = time.monotonic() + VIDEO_TIMEOUT_S
    while time.monotonic() < deadline:
        if _poll_once(db, job, provider, fail_job):
            return
        time.sleep(POLL_INTERVAL_S)
    _fail(db, job, f"Timed out after {VIDEO_TIMEOUT_S // 60} minutes.")


def _provider(db: Session, tenant_id: str, key: str) -> Any:
    return cp.provider(key) or cp.mcp_providers(db, tenant_id).get(key)


def resume_stale(db: Session) -> int:
    """generation_tasks (every minute): jobs a dead process left behind.
    Running video jobs not polled for 2 minutes are polled once; queued jobs
    older than 2 minutes are started."""
    cutoff = _now() - STALE_AFTER
    done = 0
    for job in db.query(GenerationJob).filter(GenerationJob.status == "running", GenerationJob.provider_ref.isnot(None)).limit(20).all():
        last = (job.effective or {}).get("last_poll_at")
        if last and datetime.fromisoformat(last) > cutoff:
            continue
        provider = _provider(db, str(job.tenant_id), str(job.provider))
        if provider is None:
            _fail(db, job, "The video provider is no longer set up.")
        elif job.created_at and _now() - job.created_at.astimezone(timezone.utc) > timedelta(seconds=VIDEO_TIMEOUT_S * 2):
            _fail(db, job, "Timed out.")
        else:
            _poll_once(db, job, provider)
        done += 1
    for job in db.query(GenerationJob).filter(GenerationJob.status == "queued", GenerationJob.created_at < cutoff).limit(5).all():
        run_job(db, str(job.id))
        done += 1
    db.commit()
    return done


# ---------------------------------------------------------------------------
# Regenerate / edit / cancel / approve
# ---------------------------------------------------------------------------
def regenerate(db: Session, tenant_id: str, actor: str, job_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    parent = _job(db, tenant_id, job_id)
    req = {k: v for k, v in dict(parent.request or {}).items() if k != "organic_content_id"}
    req.update({k: v for k, v in changes.items() if v is not None})
    return start(db, tenant_id, actor, parent.kind, req, parent_job_id=str(parent.id))


def edit(db: Session, tenant_id: str, actor: str, job_id: str, instruction: str) -> dict[str, Any]:
    """Image only: the previous result is the reference for the new one."""
    parent = _job(db, tenant_id, job_id)
    if parent.kind != "image":
        raise AppError("Only images can be edited; regenerate a video with a changed prompt instead.", 422)
    if parent.status != "succeeded" or not parent.result_media_id:
        raise ConflictError("Only a finished image can be edited.")
    req = {k: v for k, v in dict(parent.request or {}).items() if k != "organic_content_id"}
    req["prompt"] = f"Edit this image: {instruction}. Keep everything else the same."
    req["reference_media_ids"] = [str(parent.result_media_id)]
    req["edit_instruction"] = instruction
    return start(db, tenant_id, actor, "image", req, parent_job_id=str(parent.id))


def cancel(db: Session, tenant_id: str, actor: str, job_id: str) -> dict[str, Any]:
    job = _job(db, tenant_id, job_id, lock=True)
    if job.status not in ("queued", "running"):
        raise ConflictError(f"A {job.status} generation can't be cancelled.")
    job.status = "cancelled"
    job.finished_at = _now()
    _link_content(db, job, None, "cancelled")
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action="generation.cancelled", resource_type="generation", resource_id=job_id)
    return get_job(db, tenant_id, job_id)


def approve(db: Session, tenant_id: str, actor: str, job_id: str, create: Any | None) -> dict[str, Any]:
    from app.schemas.organic import AICreate, AIMedia, ManualCreate
    from app.services import organic_service

    job = _job(db, tenant_id, job_id, lock=True)
    if job.status != "succeeded" or not job.result_media_id:
        raise ConflictError("Only a finished generation can be approved.")
    media = media_service.require(db, tenant_id, str(job.result_media_id))
    media_service.mark_approved(db, tenant_id, actor, media)
    job.approved_at = job.approved_at or _now()
    job.approved_by = actor
    content_id = None
    if create is not None:
        if create.caption:
            content = organic_service.create_manual(db, tenant_id, actor, ManualCreate(
                caption=create.caption, media_ids=[str(media.id)], targets=create.targets, adapt=create.adapt))
        else:
            content = organic_service.create_ai(db, tenant_id, actor, AICreate(
                prompt=str((job.request or {}).get("prompt") or "")[:4000], targets=create.targets,
                product_ids=[str(p) for p in (job.request or {}).get("product_ids") or []],
                media=AIMedia(mode="use", media_ids=[str(media.id)])))
        content_id = content["id"]
        organic_service.approve(db, tenant_id, actor, content_id)
        eff = dict(job.effective or {})
        eff["content_id"] = content_id
        job.effective = eff
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action="generation.approved", resource_type="generation",
                    resource_id=job_id, metadata={"media_id": str(media.id), "content_id": content_id})
    return get_job(db, tenant_id, job_id)
