"""AI Ad Autopilot (SPEC-BE-069): prompt -> complete campaign drafts -> review.

A deterministic pipeline of bounded stages (context, plan, targeting, copy,
visuals, safety, assemble). AI is used only inside the stages that create
something, through the creative providers (SPEC-BE-070); every platform write
goes through the existing builder services (meta_builder_service,
ads_builder_service), so validation, all-or-nothing publishing, the spend-cap
approval and the audit trail are the manual builder's own.

User decision 2026-10-02: an AI run NEVER publishes by itself. Every run ends
at `ready_for_review`; publishing is a separate, manager+ action that also
refuses safety errors and needs warnings acknowledged.

Each stage's output is kept in run.stages[i]["output"], so any stage can be
retried and later stages reuse earlier outputs. The pipeline commits after
every stage, so the run page sees progress while it runs in the background.
"""
import base64
import re
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import creative_providers as cp
from app.ai.prompts import ad_planner as ap
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.ai_campaign_run import AICampaignRun
from app.models.campaign import Campaign
from app.models.tenant import Tenant
from app.schemas import ai_campaign as s

logger = structlog.get_logger(__name__)

STAGES = ("context", "plan", "targeting", "copy", "visuals", "safety", "assemble")
MAX_LLM_CALLS = 20
MAX_IMAGES = 12
MAX_SECONDS = 600
MAX_PREVIEW_BYTES = 1_500_000
# Rough LLM price for the company's daily AI limit guard only (providers don't
# return a price): US cents per 1,000 input / output tokens.
LLM_CENTS_PER_1K = (Decimal("0.3"), Decimal("1.5"))
LOOKUP_KIND = {"locations": "locations", "languages": "languages", "interests": "interests", "topics": "topics",
               "job_titles": "titles", "industries": "industries", "seniorities": "seniorities", "skills": "skills"}
FREE_TEXT_KEYS = ("keywords", "negative_keywords")
META_SEARCH = {"locations": "adgeolocation", "interests": "adinterest", "languages": "adlocale"}
DEFAULT_GROUP_FIELDS: dict[str, dict[str, Any]] = {
    "tiktok": {"placement": "AUTOMATIC", "bid_strategy": "LOWEST_COST"},
    "linkedin": {"bid_strategy": "MAXIMUM_DELIVERY"},
    "x": {"bid_strategy": "AUTO", "placements": ["ALL_ON_TWITTER"]},
    "snapchat": {"bid_strategy": "AUTO_BID", "placement": "AUTOMATIC"},
    "pinterest": {"bid_strategy": "AUTOMATIC_BID", "placement": "ALL"},
}
CTA = {"sales": "SHOP_NOW", "conversions": "SHOP_NOW", "leads": "SIGN_UP", "app_promotion": "DOWNLOAD"}

# Swappable in tests (the pipeline's only entry points to AI and to the web).
creative_generate = cp.generate


class StageFailed(Exception):
    pass


class NeedsInput(Exception):
    def __init__(self, questions: list[str]):
        super().__init__("needs input")
        self.questions = questions


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _audit(db: Session, tenant_id: str, actor: str | None, action: str, run_id: str, meta: dict[str, Any] | None = None) -> None:
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action=action, resource_type="ai_campaign_run",
                    resource_id=str(run_id), metadata=meta or {})


def _run(db: Session, tenant_id: str, run_id: str, lock: bool = False) -> AICampaignRun:
    query = db.query(AICampaignRun).filter(AICampaignRun.tenant_id == tenant_id, AICampaignRun.id == run_id)
    if lock:
        query = query.with_for_update()
    try:
        run = query.first()
    except Exception:  # noqa: BLE001 - a malformed id is a 404
        db.rollback()
        run = None
    if run is None:
        raise NotFoundError("AI campaign run not found.")
    return run


def _blank_stages() -> list[dict[str, Any]]:
    return [{"name": n, "status": "pending"} for n in STAGES]


def _stage(run: AICampaignRun, name: str) -> dict[str, Any]:
    return next(st for st in run.stages if st["name"] == name)


def _out(run: AICampaignRun, name: str) -> dict[str, Any]:
    return dict(_stage(run, name).get("output") or {})


def _set_stage(run: AICampaignRun, name: str, **values: Any) -> None:
    stages = [dict(st) for st in run.stages]
    for st in stages:
        if st["name"] == name:
            st.update({k: (_iso(v) if isinstance(v, datetime) else v) for k, v in values.items()})
    run.stages = stages


def _counters(run: AICampaignRun) -> dict[str, Any]:
    return dict((run.request or {}).get("_counters") or {"llm_calls": 0, "images": 0})


def _bump(run: AICampaignRun, key: str, n: int = 1, cost: int = 0) -> None:
    req = dict(run.request or {})
    counters = _counters(run)
    counters[key] = int(counters.get(key, 0)) + n
    req["_counters"] = counters
    run.request = req
    run.cost_cents = int(run.cost_cents or 0) + cost


def _guard(db: Session, run: AICampaignRun, kind: str) -> None:
    """Per-run limits and the company's daily AI limit, before each paid call."""
    counters = _counters(run)
    if kind == "llm" and counters.get("llm_calls", 0) >= MAX_LLM_CALLS:
        raise StageFailed(f"This run reached its limit of {MAX_LLM_CALLS} AI calls.")
    if kind == "image" and counters.get("images", 0) >= MAX_IMAGES:
        raise StageFailed(f"This run reached its limit of {MAX_IMAGES} generated images.")
    started = (run.request or {}).get("_started_at")
    if started and (_now() - datetime.fromisoformat(started)).total_seconds() > MAX_SECONDS:
        raise StageFailed("This run took longer than 10 minutes and was stopped; retry it.")
    cap = db.execute(text("SELECT llm_daily_cap_cents FROM tenants WHERE id = :t"), {"t": run.tenant_id}).scalar() or 0
    if cap > 0:
        spent = db.execute(text("SELECT COALESCE(SUM(cost_cents), 0) FROM ai_campaign_runs WHERE tenant_id = :t AND created_at >= :d AND id <> :r"),
                           {"t": run.tenant_id, "d": _now() - timedelta(days=1), "r": run.id}).scalar() or 0
        if int(spent) + int(run.cost_cents or 0) >= cap:
            raise StageFailed("Today's AI spending limit for your company is reached (Settings › limits); try again tomorrow.")


def _llm(db: Session, run: AICampaignRun, kind: str, system: str, user: str, max_tokens: int = 3000) -> tuple[dict[str, Any], str]:
    """One text call through the creative providers -> parsed JSON + provider label."""
    _guard(db, run, "llm")
    try:
        result = creative_generate(db, str(run.tenant_id), cp.CreativeRequest(kind=kind, system=system, prompt=user, max_tokens=max_tokens))
    except cp.AllProvidersFailed as exc:
        raise StageFailed(f"No AI model could do this step: {exc}") from None
    cost = int(((Decimal(result.input_tokens) * LLM_CENTS_PER_1K[0] + Decimal(result.output_tokens) * LLM_CENTS_PER_1K[1]) / 1000).to_integral_value(rounding="ROUND_CEILING")) + result.cost_cents
    _bump(run, "llm_calls", 1, cost)
    try:
        return ap.extract_json(result.text or ""), result.provider
    except ValueError as exc:
        return {"_parse_error": str(exc)}, result.provider


# ---------------------------------------------------------------------------
# Creating and reading runs
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Readiness (SPEC-FE-046 amendment): what the form may offer, from real data
# only. create_run enforces the same rules, so the API can't be bypassed.
# ---------------------------------------------------------------------------
YOUTUBE_LINK = re.compile(r"^(https://(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9_-]{11}|[A-Za-z0-9_-]{11})")


def _text_ai(db: Session, tenant_id: str) -> dict[str, Any]:
    """Mirrors what the plan/copy stages will use (llm_client): the company's
    enabled AI models in order; only when there are none, the server default."""
    from app.ai.llm_client import llm_client
    from app.services import ai_model_service

    listed = ai_model_service.list_providers(db, tenant_id)
    enabled = [p for p in listed["providers"] if p["enabled"]]
    models = [{"provider": p["provider"], "label": p["label"], "model": p["model"], "last_error": p["last_error"]} for p in enabled]
    if enabled:
        working = [p for p in enabled if not p["last_error"]]
        if working:
            return {"ready": True, "models": models, "reason": None}
        return {"ready": False, "models": models,
                "reason": "Every AI model you enabled failed its last call (" + "; ".join(f"{p['label']}: {str(p['last_error'])[:120]}" for p in enabled)
                          + "). PilotSonic's AI is unavailable right now; tell the Super admin if it keeps failing."}
    if llm_client.provider == "fixture" or listed["env_fallback"]["configured"]:
        return {"ready": True, "models": [{"provider": "server", "label": "Server default", "model": llm_client.model, "last_error": None}], "reason": None}
    return {"ready": False, "models": [], "reason": "PilotSonic's AI isn't set up yet (the Super admin adds the keys)."}


def _image_ai(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.services import ai_model_service

    sources = []
    no_model = []
    for key in cp.ordered(db, tenant_id, "image"):
        if key.key in ("openai_image", "gemini_image"):
            provider = "openai" if key.key == "openai_image" else "gemini"
            saved = next((p for p in ai_model_service.list_providers(db, tenant_id)["providers"] if p["provider"] == provider), None)
            label = "OpenAI images" if provider == "openai" else "Gemini images"
            # A saved key and a chosen image model are all we can check without
            # a paid image call (SPEC-BE-070 amendment 2026-10-02).
            if saved and saved["has_key"] and saved["image_model"]:
                sources.append({"key": key.key, "label": label, "note": f"{saved['image_model']} with PilotSonic's key"})
            elif saved and saved["has_key"]:
                no_model.append(saved["label"])
        elif key.available(db, tenant_id):
            sources.append({"key": key.key, "label": key.key.replace("mcp:", "MCP: "), "note": "MCP creative tool"})
    reason = None
    if not sources:
        reason = (f"PilotSonic has no image model chosen for {' or '.join(no_model)} yet (the Super admin chooses it)." if no_model else
                  "PilotSonic's image generation isn't set up yet (the Super admin adds an OpenAI or Gemini key with an image model).")
    return {"ready": bool(sources), "sources": sources, "reason": reason}


def _products(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    out = []
    for p in db.execute(text("SELECT sku, title, status::text AS status, default_price_cents, compare_at_price_cents, currency, images FROM products "
                             "WHERE tenant_id = :t AND deleted_at IS NULL ORDER BY title"), {"t": tenant_id}).all():
        price = Decimal(p.default_price_cents or 0) / 100
        was = Decimal(p.compare_at_price_cents) / 100 if p.compare_at_price_cents else None
        discount = int(((was - price) / was * 100).to_integral_value(rounding=ROUND_HALF_UP)) if was and was > price else 0
        photos = [i for i in (p.images or []) if str(i if isinstance(i, str) else (i or {}).get("url") or "").startswith("https://")]
        reason = None if p.status == "active" else {"draft": "Draft product", "out_of_stock": "Out of stock", "archived": "Archived"}.get(p.status, p.status)
        out.append({"sku": p.sku, "title": p.title, "status": p.status, "price": float(price), "compare_at": float(was) if was else None,
                    "discount_pct": discount, "currency": (p.currency or "").strip(), "has_photo": bool(photos), "selectable": reason is None, "reason": reason})
    return out


def readiness(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.services import ads_builder_service

    tenant = db.get(Tenant, tenant_id)
    platforms = []
    for p in ads_builder_service.platforms(db, tenant_id)["platforms"]:
        reason = None
        if not p["connected"]:
            reason = f"Connect {p['label']} in Integrations"
        elif p["publishing"] == "not_built":
            reason = f"Publishing to {p['label']} isn't available yet"
        platforms.append({"key": p["key"], "label": p["label"], "usable": reason is None, "reason": reason})
    brand = db.execute(text("SELECT brand_name, logo_url, forbidden_terms FROM brand_settings WHERE tenant_id = :t"), {"t": tenant_id}).first()
    return {
        "platforms": platforms,
        "text_ai": _text_ai(db, tenant_id),
        "image_ai": _image_ai(db, tenant_id),
        "products": _products(db, tenant_id),
        "brand": {"name": (brand.brand_name if brand else None) or (tenant.name if tenant else ""), "has_logo": bool(brand and (brand.logo_url or "").startswith("https://")),
                  "forbidden_terms": list(brand.forbidden_terms or []) if brand else []},
        "currency": (tenant.currency or "USD").strip() if tenant else "USD",
        "country": (tenant.country_code or "").strip() if tenant else "",
    }


def create_run(db: Session, tenant_id: str, actor: str, payload: s.AICampaignCreate) -> dict[str, Any]:
    from app.services import ads_builder_service
    from app.services.scheduler_service import run_soon

    registry = {p["key"]: p for p in ads_builder_service.platforms(db, tenant_id)["platforms"]}
    missing = [registry[p]["label"] for p in payload.platforms if not registry[p]["connected"]]
    if missing:
        raise ConflictError(f"Connect {', '.join(missing)} in Integrations first; AI campaigns are built against the real ad account.")
    not_built = [registry[p]["label"] for p in payload.platforms if registry[p]["publishing"] == "not_built"]
    if not_built:
        raise ConflictError(f"Publishing to {', '.join(not_built)} isn't available yet.")
    if "youtube" in payload.platforms and not payload.youtube_video:
        raise AppError("YouTube ads need your video: paste its YouTube link.", 422)
    # SPEC-FE-046 amendment: the same checks the form shows, enforced here.
    if payload.youtube_video and not YOUTUBE_LINK.match(payload.youtube_video.strip()):
        raise AppError("The YouTube video must be a youtube.com / youtu.be link or an 11-character video ID.", 422)
    text_ai = _text_ai(db, tenant_id)
    if not text_ai["ready"]:
        raise AppError(str(text_ai["reason"]), 422)
    products = {p["sku"]: p for p in _products(db, tenant_id)}
    unknown = [sku for sku in payload.skus if sku not in products]
    if unknown:
        raise AppError(f"These products don't exist: {', '.join(unknown)}.", 422)
    blocked = [f"{products[sku]['title']} ({products[sku]['reason']})" for sku in payload.skus if not products[sku]["selectable"]]
    if blocked:
        raise AppError(f"Only active products can be featured: {', '.join(blocked)}.", 422)
    if payload.visuals == "products":
        no_photo = [products[sku]["title"] for sku in payload.skus if not products[sku]["has_photo"]]
        if no_photo:
            raise AppError(f"These products have no photo to use: {', '.join(no_photo)}. Add photos or choose another image option.", 422)
    if payload.visuals == "generate":
        image_ai = _image_ai(db, tenant_id)
        if not image_ai["ready"]:
            raise AppError(str(image_ai["reason"]), 422)
    if payload.schedule.ends_at and payload.schedule.ends_at <= _now():
        raise AppError("The end date has already passed.", 422)
    request = payload.model_dump(mode="json")
    run = AICampaignRun(tenant_id=tenant_id, created_by=actor, prompt=payload.prompt, request=request, status="queued",
                        stages=_blank_stages(), campaign_ids=[], cost_cents=0)
    db.add(run)
    db.flush()
    _audit(db, tenant_id, actor, "ai_campaign.created", run.id, {"platforms": payload.platforms, "visuals": payload.visuals})
    run_id = str(run.id)
    run_soon(run_pipeline, tenant_id, run_id, actor, db=db, name=f"ai_campaign:{run_id}")
    return read_run(db, tenant_id, run_id)


def list_runs(db: Session, tenant_id: str, status: str | None = None) -> dict[str, Any]:
    query = db.query(AICampaignRun).filter(AICampaignRun.tenant_id == tenant_id)
    if status:
        query = query.filter(AICampaignRun.status == status)
    items = []
    for r in query.order_by(AICampaignRun.created_at.desc()).limit(50).all():
        items.append({"id": str(r.id), "status": r.status, "stage": r.stage, "prompt": r.prompt[:160], "platforms": (r.request or {}).get("platforms", []),
                      "cost_cents": r.cost_cents, "campaign_ids": [str(c) for c in r.campaign_ids or []], "created_by": str(r.created_by) if r.created_by else None,
                      "created_at": r.created_at.astimezone(timezone.utc), "error": r.error})
    return {"items": items}


def _issues(run: AICampaignRun) -> list[dict[str, Any]]:
    return list(_out(run, "safety").get("issues") or []) + list(_out(run, "assemble").get("issues") or [])


def read_run(db: Session, tenant_id: str, run_id: str) -> dict[str, Any]:
    from app.services import ads_builder_service

    run = _run(db, tenant_id, run_id)
    if run.status == "awaiting_approval":
        refresh_status(db, tenant_id, run)
        db.flush()
    plan = _out(run, "plan")
    copy = _out(run, "copy").get("ads") or {}
    visuals = _out(run, "visuals").get("ads") or {}
    assembled = _out(run, "assemble")
    registry = {k: v["label"] for k, v in ads_builder_service.PLATFORMS.items()}
    campaigns, ads = [], []
    for p in plan.get("platforms") or []:
        cid = (assembled.get("campaigns") or {}).get(p["platform"])
        status = None
        if cid:
            row = db.query(Campaign.status).filter(Campaign.tenant_id == tenant_id, Campaign.id == cid).first()
            status = row[0] if row else None
        groups = []
        for gi, g in enumerate(p.get("groups") or []):
            groups.append({"name": g.get("name"), "audience": (_out(run, "targeting").get("groups") or {}).get(f"{p['platform']}:g{gi}", {}).get("summary") or g.get("audience")})
            for ai, ad in enumerate(g.get("ads") or []):
                ref = f"{p['platform']}:g{gi}:a{ai}"
                ads.append({"ref": ref, "platform": p["platform"], "format": ad.get("format"), "group": g.get("name") or f"Group {gi + 1}",
                            "copy": {k: v for k, v in (copy.get(ref) or {}).items() if k != "visual_brief"},
                            "images": [{"ratio": m.get("ratio"), "preview": m.get("preview"), "source": m.get("source")} for m in visuals.get(ref) or []],
                            "angle": ad.get("angle")})
        campaigns.append({"platform": p["platform"], "label": registry.get(p["platform"], p["platform"]), "campaign_id": cid, "name": p.get("campaign_name") or "",
                          "objective": p.get("objective") or "", "campaign_type": p.get("campaign_type"), "budget": float(p.get("_budget") or 0),
                          "budget_mode": (run.request or {}).get("budget", {}).get("mode", "total"), "status": status, "groups": groups})
    issues = _issues(run)
    errors = [i for i in issues if i["severity"] == "error"]
    can_publish = run.status in ("ready_for_review", "failed") and bool(assembled.get("campaigns")) and not errors
    note = None
    if run.status == "ready_for_review":
        note = ("Fix the errors in the safety report first (edit in the builder or regenerate), then publish."
                if errors else "Publishing follows your normal rules: over the daily spend cap, a manager's publish goes to the owner for approval.")
    return {
        "id": str(run.id), "status": run.status, "stage": run.stage, "prompt": run.prompt,
        "request": {k: v for k, v in (run.request or {}).items() if not k.startswith("_")},
        "stages": [{k: st.get(k) for k in ("name", "status", "started_at", "ended_at", "provider", "note", "error")} for st in run.stages],
        "questions": list(_out(run, "plan").get("questions") or []) if run.status == "needs_input" else [],
        "summary": plan.get("summary"), "campaigns": campaigns, "ads": ads, "safety": issues,
        "can_publish": can_publish, "publish_note": note, "cost_cents": run.cost_cents, "error": run.error,
        "created_by": str(run.created_by) if run.created_by else None,
        "created_at": run.created_at.astimezone(timezone.utc), "updated_at": run.updated_at.astimezone(timezone.utc),
    }


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------
def run_pipeline(db: Session, tenant_id: str, run_id: str, actor: str, from_stage: str | None = None) -> None:
    run = _run(db, tenant_id, run_id)
    if run.status in ("cancelled", "published", "publishing"):
        return
    start = STAGES.index(from_stage) if from_stage else 0
    req = dict(run.request or {})
    req["_started_at"] = _now().isoformat()
    req["_counters"] = {"llm_calls": 0, "images": 0} if start == 0 else _counters(run)
    run.request = req
    run.status, run.error = "running", None
    for name in STAGES[start:]:
        _set_stage(run, name, status="pending", error=None, note=None)
    db.commit()
    for name in STAGES[start:]:
        db.refresh(run)
        if run.status == "cancelled":
            return
        run.stage = name
        _set_stage(run, name, status="running", started_at=_now())
        db.commit()
        try:
            output, provider, note = STAGE_FUNCS[name](db, run, actor)
            _set_stage(run, name, status="done", ended_at=_now(), output=output, provider=provider, note=note)
            db.commit()
        except NeedsInput as exc:
            db.rollback()
            run = _run(db, tenant_id, run_id)
            _set_stage(run, name, status="done", ended_at=_now(), output={**_out(run, name), "questions": exc.questions}, note="Waiting for your answers")
            run.status = "needs_input"
            db.commit()
            _audit(db, tenant_id, actor, "ai_campaign.needs_input", run_id, {"questions": len(exc.questions)})
            return
        except Exception as exc:  # noqa: BLE001 - every failure ends the run with a reason
            db.rollback()
            run = _run(db, tenant_id, run_id)
            if isinstance(exc, AppError):
                message = str(exc.detail)
            elif isinstance(exc, StageFailed):
                message = str(exc)
            else:
                logger.exception("ai_campaign_stage_crashed", tenant_id=tenant_id, run_id=run_id, stage=name)
                message = f"Unexpected error ({type(exc).__name__}); retry this step."
            _set_stage(run, name, status="failed", ended_at=_now(), error=message[:500])
            run.status, run.error = "failed", f"{name}: {message}"[:600]
            db.commit()
            _audit(db, tenant_id, actor, "ai_campaign.failed", run_id, {"stage": name, "error": message[:200]})
            logger.warning("ai_campaign_failed", tenant_id=tenant_id, run_id=run_id, stage=name, error=message[:200])
            return
    run.status, run.stage = "ready_for_review", None
    db.commit()
    _audit(db, tenant_id, actor, "ai_campaign.ready_for_review", run_id,
           {"campaigns": len(run.campaign_ids or []), "errors": sum(1 for i in _issues(run) if i["severity"] == "error"), "cost_cents": run.cost_cents})


# --- 1. context -----------------------------------------------------------------
def _context(db: Session, run: AICampaignRun, actor: str) -> tuple[dict[str, Any], str | None, str | None]:
    from app.services import ads_builder_service

    tid = str(run.tenant_id)
    req = run.request
    tenant = db.get(Tenant, tid)
    brand_row = db.execute(text("SELECT brand_name, tagline, voice_config, palette, logo_url, forbidden_terms, required_disclaimers, primary_language "
                                "FROM brand_settings WHERE tenant_id = :t"), {"t": tid}).first()
    brand: dict[str, Any] = {"name": tenant.name if tenant else "", "language": "en"}
    forbidden: list[str] = []
    disclaimers: list[str] = []
    logo = None
    if brand_row:
        voice = brand_row.voice_config or {}
        brand.update(name=brand_row.brand_name or brand["name"], tagline=brand_row.tagline, language=brand_row.primary_language or "en",
                     tone=voice.get("tone"), style=voice.get("style"), palette=brand_row.palette or {})
        forbidden = [t for t in brand_row.forbidden_terms or [] if t]
        disclaimers = [t for t in brand_row.required_disclaimers or [] if t]
        logo = brand_row.logo_url if (brand_row.logo_url or "").startswith("https://") else None
    products = []
    for p in db.execute(text("SELECT sku, title, short_description, default_price_cents, compare_at_price_cents, currency, images FROM products "
                             "WHERE tenant_id = :t AND sku = ANY(:s) AND deleted_at IS NULL"), {"t": tid, "s": list(req.get("skus") or []) or [""]}).all():
        price = Decimal(p.default_price_cents or 0) / 100
        was = Decimal(p.compare_at_price_cents) / 100 if p.compare_at_price_cents else None
        discount = int(((was - price) / was * 100).to_integral_value(rounding=ROUND_HALF_UP)) if was and was > price else 0
        products.append({"sku": p.sku, "title": p.title, "summary": p.short_description, "price": f"{price:.2f}", "was": f"{was:.2f}" if was else None,
                         "discount_pct": discount, "currency": (p.currency or "").strip(),
                         "image_urls": [i if isinstance(i, str) else (i or {}).get("url") for i in (p.images or []) if (i if isinstance(i, str) else (i or {}).get("url"))][:4]})
    missing = sorted(set(req.get("skus") or []) - {p["sku"] for p in products})
    if missing:
        raise StageFailed(f"These products weren't found: {', '.join(missing)}.")
    past = [{"campaign": r.name, "ctr_pct": float(r.ctr)} for r in db.execute(text(
        "SELECT c.name, ROUND(SUM(e.value) FILTER (WHERE e.metric = 'link_clicks') * 100.0 / NULLIF(SUM(e.value) FILTER (WHERE e.metric = 'impressions'), 0), 2) AS ctr "
        "FROM analytics_events e JOIN campaigns c ON c.id::text = e.dimensions->>'campaign_id' AND c.tenant_id = e.tenant_id "
        "WHERE e.tenant_id = :t AND e.event_time >= now() - interval '90 days' GROUP BY c.name HAVING SUM(e.value) FILTER (WHERE e.metric = 'impressions') > 0 "
        "ORDER BY 2 DESC NULLS LAST LIMIT 3"), {"t": tid}).all() if r.ctr is not None]
    registry = {p["key"]: p for p in ads_builder_service.platforms(db, tid)["platforms"]}
    ctx = {"prompt": run.prompt, "platforms": list(req["platforms"]), "goal": req.get("goal"), "variants": int(req.get("variants_per_group") or 2),
           "currency": (tenant.currency or "USD").strip() if tenant else "USD", "timezone": tenant.timezone if tenant else "UTC",
           "country": (tenant.country_code or "").strip() if tenant else "", "brand": brand, "forbidden": forbidden, "disclaimers": disclaimers,
           "logo_url": logo, "products": products, "past": past, "landing_url": req["landing_url"],
           "registry": {k: {"objectives": v["objectives"], "campaign_types": v["campaign_types"], "creative": v["creative"]} for k, v in registry.items()}}
    return ctx, None, f"{len(products)} product(s), brand voice {'set' if brand_row else 'default'}"


# --- 2. plan --------------------------------------------------------------------
def _plan(db: Session, run: AICampaignRun, actor: str) -> tuple[dict[str, Any], str | None, str | None]:
    ctx = {**_out(run, "context"), "answers": (run.request or {}).get("answers")}
    system, user = ap.plan_prompts(ctx)
    feedback: list[str] = []
    provider = None
    for _attempt in range(3):
        plan, provider = _llm(db, run, "plan", system, user + ("\nFix these problems and answer again in full:\n- " + "\n- ".join(feedback) if feedback else ""))
        feedback = [plan["_parse_error"]] if "_parse_error" in plan else ap.check_plan(plan, ctx)
        if not feedback:
            break
    if feedback:
        raise StageFailed("The AI plan didn't follow the platform rules: " + "; ".join(feedback[:4]))
    questions = [str(q)[:200] for q in plan.get("questions") or [] if str(q).strip()][:3]
    if questions and not ctx.get("answers"):
        raise NeedsInput(questions)
    # Split the budget by the plan's shares (normalised to 100 %), in cents.
    req = run.request
    total = Decimal(str(req["budget"]["amount"]))
    shares = [Decimal(str(max(float(p.get("budget_share_pct") or 0), 0))) for p in plan["platforms"]]
    whole = sum(shares) or Decimal(1)
    left = total
    for i, p in enumerate(plan["platforms"]):
        amount = left if i == len(plan["platforms"]) - 1 else (total * shares[i] / whole).quantize(Decimal("0.01"))
        left -= amount
        p["_budget"] = str(amount)
    return {"summary": str(plan.get("summary") or "")[:500], "platforms": plan["platforms"], "questions": questions}, provider, f"{sum(len(p['groups']) for p in plan['platforms'])} group(s)"


# --- 3. targeting ----------------------------------------------------------------
def _pick(items: list[dict[str, Any]], word: str) -> dict[str, Any] | None:
    w = word.strip().lower()
    for it in items:
        if str(it.get("name", "")).strip().lower() == w:
            return it
    for it in items:
        if w in str(it.get("name", "")).lower():
            return it
    return items[0] if items else None


def _targeting(db: Session, run: AICampaignRun, actor: str) -> tuple[dict[str, Any], str | None, str | None]:
    from app.services import ads_builder_service, meta_builder_service

    tid = str(run.tenant_id)
    plan = _out(run, "plan")
    groups: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    for p in plan["platforms"]:
        name = p["platform"]
        for gi, g in enumerate(p["groups"]):
            key = f"{name}:g{gi}"
            aud = g.get("audience") or {}
            resolved: dict[str, Any] = {}
            summary: dict[str, list[str]] = {}
            for field in ap.AUDIENCE_KEYS[name]:
                words = [str(w).strip() for w in aud.get(field) or [] if str(w).strip()][:10]
                if not words:
                    continue
                if field in FREE_TEXT_KEYS:
                    resolved[field] = [{"id": None, "name": w, **({"match": "PHRASE"} if name == "google" else {})} for w in words]
                    summary[field] = words
                    continue
                found = []
                for w in words:
                    try:
                        if name == "meta":
                            items = meta_builder_service.targeting_search(db, tid, META_SEARCH[field], w)
                        else:
                            items = ads_builder_service.lookup(db, tid, name, LOOKUP_KIND[field], w)
                    except AppError as exc:
                        warnings.append({"ref": key, "severity": "warning", "rule": "targeting", "message": f"Couldn't look up {field} “{w}”: {exc.detail}", "source": "targeting"})
                        continue
                    hit = _pick(items, w)
                    if hit is None:
                        warnings.append({"ref": key, "severity": "warning", "rule": "targeting", "message": f"{field.replace('_', ' ').capitalize()} “{w}” isn't in {name}'s list; left out.", "source": "targeting"})
                        continue
                    found.append(hit)
                if found:
                    resolved[field] = found
                    summary[field] = [str(f.get("name")) for f in found]
            if not resolved.get("locations"):
                raise StageFailed(f"No location of {name} group {gi + 1} matched the platform's list ({', '.join(aud.get('locations') or []) or 'none given'}).")
            if name not in ap.NO_DEMOGRAPHICS:
                for k in ("age_min", "age_max"):
                    if isinstance(aud.get(k), int):
                        resolved[k] = max(13, min(65, aud[k]))
                        summary[k] = [str(resolved[k])]
                genders = [x for x in aud.get("genders") or [] if x in ("female", "male")]
                if genders:
                    resolved["genders"] = genders
                    summary["genders"] = genders
            groups[key] = {"resolved": resolved, "summary": summary}
    return {"groups": groups, "warnings": warnings}, None, f"{len(groups)} audience(s), {len(warnings)} left out"


# --- 4. copy ---------------------------------------------------------------------
def _ad_list(run: AICampaignRun) -> list[dict[str, Any]]:
    out = []
    for p in _out(run, "plan")["platforms"]:
        for gi, g in enumerate(p["groups"]):
            for ai, ad in enumerate(g.get("ads") or []):
                out.append({"ref": f"{p['platform']}:g{gi}:a{ai}", "platform": p["platform"], "format": ad["format"], "angle": ad.get("angle") or "",
                            "audience": g.get("audience")})
    return out


def _write_copy(db: Session, run: AICampaignRun, ctx: dict[str, Any], ads: list[dict[str, Any]], extra_feedback: list[str] | None = None) -> tuple[dict[str, Any], list[str], str | None]:
    feedback = list(extra_feedback or [])
    best: dict[str, Any] = {}
    errors: list[str] = []
    provider = None
    for _attempt in range(3):
        system, user = ap.copy_prompts(ctx, ads, feedback or None)
        out, provider = _llm(db, run, "copy", system, user, max_tokens=4000)
        if "_parse_error" in out:
            errors = feedback = [out["_parse_error"]]
            continue
        best, errors = ap.check_copy(ads, out)
        if not errors:
            break
        feedback = errors
    return best, errors, provider


def _copy(db: Session, run: AICampaignRun, actor: str) -> tuple[dict[str, Any], str | None, str | None]:
    ctx = _out(run, "context")
    ads = _ad_list(run)
    best, errors, provider = _write_copy(db, run, ctx, ads)
    if not best:
        raise StageFailed("The AI couldn't write usable copy: " + "; ".join(errors[:3]))
    return {"ads": best, "errors": errors}, provider, f"{len(best)} ad(s)" + (f", {len(errors)} limit problem(s) left for review" if errors else "")


# --- 5. visuals ------------------------------------------------------------------
def _upload(db: Session, run: AICampaignRun, actor: str, platform: str, filename: str, data: bytes) -> dict[str, Any]:
    from app.services import ads_builder_service, meta_builder_service

    tid = str(run.tenant_id)
    if platform == "meta":
        res = meta_builder_service.upload_media(db, tid, actor, filename, data)
        return {"media_id": res["image_hash"], "kind": "image", "name": filename}
    res = ads_builder_service.upload_media(db, tid, actor, platform, filename, data)
    return {"media_id": res["media_id"], "kind": res["kind"], "name": filename}


def _preview(data: bytes, mime: str | None) -> str | None:
    return f"data:{mime or 'image/png'};base64,{base64.b64encode(data).decode()}" if len(data) <= MAX_PREVIEW_BYTES else None


def _image_for(db: Session, run: AICampaignRun, ctx: dict[str, Any], brief: str, ratio: str) -> cp.CreativeResult:
    req = run.request
    visual = req.get("visuals")
    products = [p["title"] for p in ctx["products"]]
    if visual == "products":
        providers = [cp.BUILT_IN["catalog"]]
    else:
        providers = cp.ordered(db, str(run.tenant_id), "image") + ([cp.BUILT_IN["catalog"]] if req.get("skus") else [])
    palette = (ctx["brand"].get("palette") or {})
    prompt = (f"Advertising photo, aspect ratio {ratio}. {brief or run.prompt[:300]}. "
              f"Products: {', '.join(products) or 'the advertised offer'}. Brand colors: {palette or 'natural'}. "
              "Photorealistic, well lit, no text, no logos, no watermarks.")
    _guard(db, run, "image")
    try:
        result = creative_generate(db, str(run.tenant_id), cp.CreativeRequest(kind="image", prompt=prompt, aspect_ratio=ratio, skus=list(req.get("skus") or [])), providers)
    except cp.AllProvidersFailed as exc:
        raise StageFailed(f"No image source worked for {ratio}: {exc}") from None
    _bump(run, "images", 1 if result.provider != "catalog" else 0, result.cost_cents)
    return result


def _visuals(db: Session, run: AICampaignRun, actor: str) -> tuple[dict[str, Any], str | None, str | None]:
    ctx = _out(run, "context")
    copy = _out(run, "copy")["ads"]
    req = run.request
    out: dict[str, list[dict[str, Any]]] = {}
    issues: list[dict[str, Any]] = []
    providers_used: set[str] = set()
    logo_cache: dict[str, dict[str, Any]] = {}
    if req.get("visuals") == "builder":
        return {"ads": {}, "issues": []}, None, "Add images in the builder before publishing"
    for ad in _ad_list(run):
        ref, platform, fmt = ad["ref"], ad["platform"], ad["format"]
        media: list[dict[str, Any]] = []
        if platform == "pinterest":
            # Pinterest takes images as a public URL (no upload API): product photos only.
            urls = [u for p in ctx["products"] for u in p["image_urls"] if str(u).startswith("https://")]
            if urls:
                media.append({"ratio": "2:3", "image_url": urls[0], "preview": urls[0], "source": "catalog"})
            else:
                issues.append({"ref": ref, "severity": "error", "rule": "media", "source": "visuals",
                               "message": "Pinterest needs a public image link: feature a product with photos, or add an Image URL in the builder."})
        for ratio in ap.IMAGE_RATIOS.get(platform, {}).get(fmt, []) if platform != "pinterest" else []:
            result = _image_for(db, run, ctx, str((copy.get(ref) or {}).get("visual_brief") or ""), ratio)
            providers_used.add(result.provider)
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(result.mime or "", "png")
            uploaded = _upload(db, run, actor, platform, f"ai-{ref.replace(':', '-')}-{ratio.replace(':', 'x')}.{ext}", result.image or b"")
            media.append({**uploaded, "ratio": ratio, "preview": _preview(result.image or b"", result.mime), "source": result.provider})
        needs_logo = platform == "youtube" or (platform == "google" and fmt in ("responsive_display", "demand_gen", "asset_group"))
        if needs_logo:
            if ctx.get("logo_url"):
                if platform not in logo_cache:
                    try:
                        from app.integrations import verify
                        from app.integrations.base_adapter import http

                        verify._require_public_host(re.sub(r"^https://([^/:]+).*$", r"\1", ctx["logo_url"]))
                        data = http("GET", ctx["logo_url"], timeout=60.0).content
                        cp.image_size(data)
                        logo_cache[platform] = {**_upload(db, run, actor, platform, "brand-logo.png", data), "ratio": "1:1", "preview": _preview(data, None), "source": "brand logo"}
                    except Exception as exc:  # noqa: BLE001 - reported, never fatal
                        issues.append({"ref": ref, "severity": "warning" if platform == "google" else "error", "rule": "logo", "source": "visuals",
                                       "message": f"Couldn't use your brand logo ({type(exc).__name__}); upload a square logo in the builder."})
                if platform in logo_cache:
                    media.append(logo_cache[platform])
            elif platform == "youtube":
                issues.append({"ref": ref, "severity": "error", "rule": "logo", "source": "visuals",
                               "message": "YouTube ads need a square logo: add one in Settings › Brand or upload it in the builder."})
        out[ref] = media
    return {"ads": out, "issues": issues}, ", ".join(sorted(providers_used)) or None, f"{sum(len(v) for v in out.values())} image(s)"


# --- 6. safety -------------------------------------------------------------------
REF = re.compile(r"^[a-z]+:g\d+:a\d+")
DISCOUNT = re.compile(r"(\d{1,2})\s?%\s?(?:off|discount|ছাড়)", re.IGNORECASE)


def _landing_ok(url: str) -> str | None:
    """None when the landing page answers over https; otherwise the reason."""
    from app.integrations import verify
    from app.integrations.base_adapter import PlatformError, http

    try:
        verify._public_https_base(url)
        resp = http("GET", url, timeout=20.0, headers={"User-Agent": "PilotSonic-Autopilot/1.0"})
    except (verify.VerifyError, PlatformError) as exc:
        return str(exc)
    return None if resp.status_code < 400 else f"the page answered HTTP {resp.status_code}"


landing_check = _landing_ok


def _text_of(copy: dict[str, Any]) -> str:
    parts = []
    for k, v in copy.items():
        if k == "visual_brief":
            continue
        parts.extend(v if isinstance(v, list) else [v])
    return " | ".join(str(p) for p in parts if p)


MONEY_SYMBOLS = "$€£¥₹৳₦₱₩₫₺"
FREE_SHIPPING = re.compile(r"\bfree\s+(?:shipping|delivery)\b|ফ্রি\s*ডেলিভারি", re.IGNORECASE)


def _money_pattern(ctx: dict[str, Any]) -> re.Pattern[str]:
    # A number next to a currency symbol or code (SPEC-BE-085 FR11).
    codes = {ctx.get("currency") or "", *(p.get("currency") or "" for p in ctx["products"]), "tk", "taka", "bdt", "usd", "eur", "gbp", "inr", "rs"}
    words = "|".join(sorted({re.escape(c.strip().lower()) for c in codes if c.strip()}, key=len, reverse=True))
    sym = re.escape(MONEY_SYMBOLS)
    num = r"(\d[\d,]*(?:\.\d{1,2})?)"
    return re.compile(rf"(?:[{sym}]|\b(?:{words})\.?)\s?{num}|{num}\s?(?:[{sym}]|(?:{words})\b)", re.IGNORECASE)


def _price_issues(ctx: dict[str, Any], ref: str, body: str) -> list[dict[str, Any]]:
    """Amounts must be a featured product's price, compare-at price or saving,
    or a number in the brief; free shipping must be in the brief."""
    from app.ai.command_guard import numbers_in

    issues: list[dict[str, Any]] = []
    allowed = set(numbers_in(ctx.get("prompt") or ""))
    for p in ctx["products"]:
        price = Decimal(str(p["price"]))
        allowed.add(price)
        if p.get("was"):
            allowed.update({Decimal(str(p["was"])), Decimal(str(p["was"])) - price})
    for m in _money_pattern(ctx).finditer(body):
        raw = (m.group(1) or m.group(2) or "").rstrip(",").replace(",", "")
        try:
            amount = Decimal(raw)
        except ArithmeticError:
            continue
        if any(abs(amount - a) < Decimal("0.01") for a in allowed):
            continue
        if not ctx["products"]:
            issues.append({"ref": ref, "severity": "warning", "rule": "price_claim", "source": "price_check",
                           "message": f"Mentions the amount {m.group(0).strip()}, but no product is featured to check it against."})
        else:
            issues.append({"ref": ref, "severity": "error", "rule": "price_claim", "source": "price_check",
                           "message": f"Mentions the amount {m.group(0).strip()}, which isn't a featured product's price or a number in the brief."})
    if FREE_SHIPPING.search(body) and not FREE_SHIPPING.search(ctx.get("prompt") or ""):
        issues.append({"ref": ref, "severity": "warning", "rule": "free_shipping_claim", "source": "price_check",
                       "message": "Promises free shipping or delivery, which the brief doesn't mention. Check that it's true."})
    return issues


def _deterministic_checks(ctx: dict[str, Any], copy: dict[str, Any]) -> list[dict[str, Any]]:
    from app.ai.moderation import moderate_text

    issues = []
    best = max([p["discount_pct"] for p in ctx["products"]] or [0])
    for ref, fields in copy.items():
        body = _text_of(fields)
        issues += _price_issues(ctx, ref, body)
        passed, hits = moderate_text(body, ctx["forbidden"])
        if not passed:
            issues.append({"ref": ref, "severity": "error", "rule": "forbidden_terms", "source": "moderation", "message": f"Uses forbidden word(s): {', '.join(hits)}."})
        for m in DISCOUNT.finditer(body):
            claimed = int(m.group(1))
            if not ctx["products"]:
                issues.append({"ref": ref, "severity": "warning", "rule": "price_claim", "source": "price_check",
                               "message": f"Claims {claimed}% off, but no product is featured to check it against."})
            elif claimed > best + 1:
                issues.append({"ref": ref, "severity": "error", "rule": "price_claim", "source": "price_check",
                               "message": f"Claims {claimed}% off, but the featured products' real discount is at most {best}%."})
        for disclaimer in ctx["disclaimers"]:
            if disclaimer.lower() not in body.lower():
                issues.append({"ref": ref, "severity": "warning", "rule": "disclaimer", "source": "brand", "message": f"Missing the required disclaimer “{disclaimer}”."})
    return issues


def _review(db: Session, run: AICampaignRun, ctx: dict[str, Any], copy: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    ads = [{"ref": a["ref"], "platform": a["platform"], "copy": {k: v for k, v in (copy.get(a["ref"]) or {}).items() if k != "visual_brief"}} for a in _ad_list(run)]
    system, user = ap.review_prompts(ctx, ads)
    try:
        out, provider = _llm(db, run, "review", system, user, max_tokens=2000)
    except StageFailed as exc:
        return [{"ref": "", "severity": "warning", "rule": "policy_review", "source": "ai_review", "message": f"The AI policy review couldn't run ({exc}); check the copy yourself."}], None
    if "_parse_error" in out:
        return [{"ref": "", "severity": "warning", "rule": "policy_review", "source": "ai_review", "message": "The AI policy review gave an unreadable answer; check the copy yourself."}], provider
    return ap.check_review(out, {a["ref"] for a in ads}), provider


def _safety(db: Session, run: AICampaignRun, actor: str) -> tuple[dict[str, Any], str | None, str | None]:
    ctx = _out(run, "context")
    copy_out = _out(run, "copy")
    copy = dict(copy_out["ads"])
    issues = _deterministic_checks(ctx, copy)
    review, provider = _review(db, run, ctx, copy)
    issues += review
    # One repair round for the ads with copy errors (forbidden words, false
    # discounts, policy), then the checks run again on the new copy.
    bad = sorted({i["ref"] for i in issues if i["severity"] == "error" and i["ref"]})
    if bad:
        ads = [a for a in _ad_list(run) if a["ref"] in bad]
        feedback = [f"{i['ref']}: {i['message']}" for i in issues if i["ref"] in bad and i["severity"] == "error"]
        fixed, _errors, _p = _write_copy(db, run, ctx, ads, feedback)
        copy.update({ref: v for ref, v in fixed.items() if v})
        issues = _deterministic_checks(ctx, copy)
        review, provider = _review(db, run, ctx, copy)
        issues += review
        _set_stage(run, "copy", output={**copy_out, "ads": copy})
    limit_errors = [{"ref": m.group(0) if (m := REF.match(e)) else "", "severity": "error", "rule": "limits", "source": "copy", "message": e}
                    for e in copy_out.get("errors") or []]
    issues += limit_errors
    issues += list(_out(run, "visuals").get("issues") or [])
    issues += list(_out(run, "targeting").get("warnings") or [])
    reason = landing_check(ctx["landing_url"])
    if reason:
        issues.append({"ref": "", "severity": "error", "rule": "landing_page", "source": "landing_check", "message": f"The landing page didn't load: {reason}."})
    if (run.request or {}).get("visuals") == "builder":
        issues.append({"ref": "", "severity": "warning", "rule": "media", "source": "visuals", "message": "Add the images or videos in the builder before publishing."})
    return {"issues": issues}, provider, f"{sum(1 for i in issues if i['severity'] == 'error')} error(s), {sum(1 for i in issues if i['severity'] == 'warning')} warning(s)"


# --- 7. assemble -----------------------------------------------------------------
def _schedule(run: AICampaignRun) -> tuple[datetime, datetime]:
    sched = (run.request or {}).get("schedule") or {}
    start = datetime.fromisoformat(sched["starts_at"]) if sched.get("starts_at") else (_now() + timedelta(hours=1)).replace(second=0, microsecond=0)
    end = datetime.fromisoformat(sched["ends_at"]) if sched.get("ends_at") else start + timedelta(days=7)
    return start, end


def _creative_for(platform: str, ad: dict[str, Any], copy: dict[str, Any], media: list[dict[str, Any]], ctx: dict[str, Any], conn_fields: dict[str, Any], run: AICampaignRun, objective: str) -> dict[str, Any]:
    creative: dict[str, Any] = {"format": ad["format"], **{k: v for k, v in copy.items() if k != "visual_brief"}, "destination_url": ctx["landing_url"]}
    uploads = [{k: m[k] for k in ("media_id", "kind", "name")} for m in media if m.get("media_id")]
    if uploads:
        creative["media"] = uploads
    if platform == "pinterest":
        image = next((m.get("image_url") for m in media if m.get("image_url")), None)
        if image:
            creative["image_url"] = image
        if conn_fields.get("board_id"):
            creative["board_id"] = conn_fields["board_id"]
    if platform == "tiktok" and conn_fields.get("identity_id"):
        creative["identity_id"] = conn_fields["identity_id"]
    if platform == "youtube":
        creative["youtube_video"] = (run.request or {}).get("youtube_video")
    if platform in ("tiktok", "youtube", "linkedin", "snapchat") or (platform == "google" and ad["format"] == "demand_gen"):
        creative["cta"] = {"snapchat": "SHOP_NOW"}.get(platform) or CTA.get(objective, "LEARN_MORE")
    return creative


def _assemble(db: Session, run: AICampaignRun, actor: str) -> tuple[dict[str, Any], str | None, str | None]:
    from app.schemas import ads_builder as ab
    from app.schemas import meta as ms
    from app.services import ads_builder_service, integration_service, meta_builder_service

    tid = str(run.tenant_id)
    ctx = _out(run, "context")
    plan = _out(run, "plan")
    targeting = _out(run, "targeting")["groups"]
    copy = _out(run, "copy")["ads"]
    visuals = _out(run, "visuals").get("ads") or {}
    req = run.request
    mode = req["budget"]["mode"]
    start, end = _schedule(run)
    campaigns: dict[str, str] = {}
    ad_ids: dict[str, str] = {}
    issues: list[dict[str, Any]] = []
    # A retry rebuilds the drafts: earlier drafts of this run are discarded first.
    _discard_drafts(db, tid, [str(c) for c in run.campaign_ids or []])
    run.campaign_ids = []
    for p in plan["platforms"]:
        name = p["platform"]
        amount = Decimal(p["_budget"])
        groups = p["groups"]
        if name == "meta":
            # Use what the Meta connection has: the pixel for sales/leads
            # tracking, Instagram only when an Instagram account is connected.
            mconn = integration_service.meta_publish_credentials(db, tid) or {}
            pixel = mconn.get("pixel_id") or None
            use_ig = bool(mconn.get("instagram_id"))
            tree = meta_builder_service.create_campaign(db, tid, actor, ms.CampaignCreate(name=p["campaign_name"][:255], objective=p["objective"]))
            cid = tree["campaign"]["id"]
            set_ids = [s_["id"] for s_ in tree["ad_sets"]]
            for gi, g in enumerate(groups):
                if gi >= len(set_ids):
                    tree = meta_builder_service.add_ad_set(db, tid, actor, cid, ms.AdSetCreate(name=(g.get("name") or f"Ad set {gi + 1}")[:255]))
                    set_ids = [s_["id"] for s_ in tree["ad_sets"]]
                res = targeting[f"meta:g{gi}"]["resolved"]
                locs = res.get("locations") or []
                tg = ms.Targeting(
                    countries=[str((x.get("extra") or {}).get("country_code") or x["id"]) for x in locs if x.get("type") == "country"],
                    regions=[ms.TargetRef(key=x["id"], name=x["name"], type="region") for x in locs if x.get("type") == "region"],
                    cities=[ms.TargetRef(key=x["id"], name=x["name"], type="city") for x in locs if x.get("type") not in ("country", "region")],
                    age_min=res.get("age_min", 18), age_max=res.get("age_max", 65),
                    genders=(res.get("genders") or ["all"])[0] if len(res.get("genders") or []) == 1 else "all",
                    locales=[ms.TargetRef(key=x["id"], name=x["name"]) for x in res.get("languages") or []],
                    detailed=[ms.TargetRef(key=x["id"], name=x["name"], type="interests") for x in res.get("interests") or []],
                )
                per = (amount / len(groups)).quantize(Decimal("0.01"))
                meta_builder_service.update_ad_set(db, tid, actor, set_ids[gi], ms.AdSetFields(
                    name=(g.get("name") or f"Ad set {gi + 1}")[:255], budget_type="daily" if mode == "daily" else "lifetime", budget=per,
                    starts_at=start, ends_at=end, targeting=tg, pixel_id=pixel if p["objective"] in ("sales", "leads") else None))
                tree = meta_builder_service.get_tree(db, tid, cid)
                existing = [a["id"] for a in tree["ad_sets"][gi]["ads"]]
                for ai, _ad in enumerate(g["ads"]):
                    ref = f"meta:g{gi}:a{ai}"
                    if ai >= len(existing):
                        tree = meta_builder_service.add_ad(db, tid, actor, set_ids[gi], ms.AdCreate(name=f"{p['campaign_name']} {gi + 1}.{ai + 1}"[:255]))
                        existing = [a["id"] for a in tree["ad_sets"][gi]["ads"]]
                    c_ = copy.get(ref) or {}
                    img = next((m for m in visuals.get(ref) or [] if m.get("media_id")), None)
                    meta_builder_service.update_ad(db, tid, actor, existing[ai], ms.AdFields(
                        name=f"{p['campaign_name']} {gi + 1}.{ai + 1}"[:255], format="image",
                        media=[ms.Media(type="image", image_hash=img["media_id"], name=img.get("name", ""))] if img else None,
                        primary_text=c_.get("primary_text") or None, headline=c_.get("headline") or None, description=c_.get("description") or None,
                        call_to_action=CTA.get(p["objective"], "LEARN_MORE"), destination=ms.Destination(type="website", url=ctx["landing_url"]),
                        use_instagram=use_ig))
                    ad_ids[ref] = existing[ai]
            check = meta_builder_service.validate(db, tid, actor, cid)
            issues += [{"ref": "", "severity": "error", "rule": "platform", "source": "meta", "message": f"{e.get('level', '')}: {e.get('message', '')}"} for e in check.get("errors") or []]
        else:
            conn = integration_service.ad_platform_connection(db, tid, ads_builder_service.PLATFORMS[name]["provider"]) or {"fields": {}}
            tree = ads_builder_service.create_campaign(db, tid, actor, name, ab.CampaignCreate(name=p["campaign_name"][:255], objective=p["objective"], campaign_type=p.get("campaign_type")))
            cid = tree["campaign"]["id"]
            on_groups = name == "snapchat"  # Snapchat budgets live on the ad squads
            ads_builder_service.update_campaign(db, tid, actor, cid, ab.CampaignFields(
                budget_mode="none" if on_groups else mode, budget=None if on_groups else amount, starts_at=start, ends_at=end))
            group_ids = [g_["id"] for g_ in tree["groups"]]
            for gi, g in enumerate(groups):
                if gi >= len(group_ids):
                    tree = ads_builder_service.add_group(db, tid, actor, cid, ab.GroupFields(name=(g.get("name") or f"Group {gi + 1}")[:255]))
                    group_ids = [g_["id"] for g_ in tree["groups"]]
                res = dict(targeting[f"{name}:g{gi}"]["resolved"])
                res = {k: ([{"id": x.get("id"), "name": x.get("name"), **({"match": x["match"]} if x.get("match") else {})} for x in v] if isinstance(v, list) and v and isinstance(v[0], dict) else v)
                       for k, v in res.items()}
                fields = dict(DEFAULT_GROUP_FIELDS.get(name, {}))
                gfields: dict[str, Any] = {"name": (g.get("name") or f"Group {gi + 1}")[:255], "targeting": res, "fields": fields}
                if on_groups:
                    gfields.update(budget_mode=mode, budget=(amount / len(groups)).quantize(Decimal("0.01")))
                tree = ads_builder_service.update_group(db, tid, actor, group_ids[gi], ab.GroupFields(**gfields))
                existing = [a["id"] for a in tree["groups"][gi]["ads"]]
                for ai, ad in enumerate(g["ads"]):
                    ref = f"{name}:g{gi}:a{ai}"
                    if ai >= len(existing):
                        tree = ads_builder_service.add_ad(db, tid, actor, group_ids[gi], ab.AdFields(name=f"{p['campaign_name']} {gi + 1}.{ai + 1}"[:255]))
                        existing = [a["id"] for a in tree["groups"][gi]["ads"]]
                    creative = _creative_for(name, ad, copy.get(ref) or {}, visuals.get(ref) or [], ctx, conn["fields"], run, p["objective"])
                    ads_builder_service.update_ad(db, tid, actor, existing[ai], ab.AdFields(name=f"{p['campaign_name']} {gi + 1}.{ai + 1}"[:255], creative=creative))
                    ad_ids[ref] = existing[ai]
            check = ads_builder_service.validate(db, tid, cid)
            issues += [{"ref": "", "severity": i["severity"], "rule": "platform", "source": name, "message": f"{i['path']}: {i['message']}"} for i in check["issues"]]
        campaigns[name] = cid
        row = db.query(Campaign).filter(Campaign.tenant_id == tid, Campaign.id == cid).first()
        if row is not None:
            row.extra_metadata = {**(row.extra_metadata or {}), "ai_run_id": str(run.id)}
        run.campaign_ids = [*list(run.campaign_ids or []), cid]
        db.flush()
    return {"campaigns": campaigns, "ads": ad_ids, "issues": issues}, None, f"{len(campaigns)} draft(s)"


STAGE_FUNCS = {"context": _context, "plan": _plan, "targeting": _targeting, "copy": _copy, "visuals": _visuals, "safety": _safety, "assemble": _assemble}


# ---------------------------------------------------------------------------
# User actions: answer, retry, cancel/discard, regenerate, publish
# ---------------------------------------------------------------------------
def _discard_drafts(db: Session, tenant_id: str, campaign_ids: list[str]) -> int:
    """Delete this run's campaigns that are still drafts (never published ones)."""
    removed = 0
    for cid in campaign_ids:
        c = db.query(Campaign).filter(Campaign.tenant_id == tenant_id, Campaign.id == cid).first()
        if c is None or c.status != "draft":
            continue
        for g in list(c.ad_groups):
            for a in list(g.ads):
                db.delete(a)
            db.delete(g)
        db.delete(c)
        removed += 1
    db.flush()
    return removed


def answer(db: Session, tenant_id: str, actor: str, run_id: str, payload: s.AnswerRequest) -> dict[str, Any]:
    from app.services.scheduler_service import run_soon

    run = _run(db, tenant_id, run_id, lock=True)
    if run.status != "needs_input":
        raise ConflictError("This run isn't waiting for answers.")
    questions = _out(run, "plan").get("questions") or []
    run.request = {**dict(run.request or {}), "answers": [{"question": q, "answer": a} for q, a in zip(questions, payload.answers, strict=False)]}
    run.status = "queued"
    _audit(db, tenant_id, actor, "ai_campaign.answered", run_id)
    run_soon(run_pipeline, tenant_id, run_id, actor, "plan", db=db, name=f"ai_campaign:{run_id}")
    return read_run(db, tenant_id, run_id)


def retry(db: Session, tenant_id: str, actor: str, run_id: str, payload: s.RetryRequest) -> dict[str, Any]:
    from app.services.scheduler_service import run_soon

    run = _run(db, tenant_id, run_id, lock=True)
    if run.status not in ("failed", "ready_for_review"):
        raise ConflictError(f"Only a failed or reviewed run can be retried (this one is {run.status}).")
    if any(str(c) for c in run.campaign_ids or []) and _published_ids(db, tenant_id, run):
        raise ConflictError("Part of this run is already published; edit those campaigns in the builder instead.")
    failed = next((st["name"] for st in run.stages if st.get("status") == "failed"), None)
    stage = payload.from_stage or failed or "plan"
    run.status, run.error = "queued", None
    _audit(db, tenant_id, actor, "ai_campaign.retried", run_id, {"from_stage": stage})
    run_soon(run_pipeline, tenant_id, run_id, actor, stage, db=db, name=f"ai_campaign:{run_id}")
    return read_run(db, tenant_id, run_id)


def cancel(db: Session, tenant_id: str, actor: str, run_id: str) -> dict[str, Any]:
    """Stops a running run, or discards a reviewed one (its drafts are deleted;
    anything already published is left alone)."""
    run = _run(db, tenant_id, run_id, lock=True)
    if run.status in ("published", "publishing", "cancelled"):
        raise ConflictError(f"This run is {run.status}.")
    removed = _discard_drafts(db, tenant_id, [str(c) for c in run.campaign_ids or []])
    run.status = "cancelled"
    _audit(db, tenant_id, actor, "ai_campaign.cancelled", run_id, {"drafts_removed": removed})
    return read_run(db, tenant_id, run_id)


def _published_ids(db: Session, tenant_id: str, run: AICampaignRun) -> list[str]:
    ids = [str(c) for c in run.campaign_ids or []]
    if not ids:
        return []
    rows = db.query(Campaign.id, Campaign.status).filter(Campaign.tenant_id == tenant_id, Campaign.id.in_(ids)).all()
    return [str(i) for i, st in rows if st != "draft"]


def regenerate(db: Session, tenant_id: str, actor: str, run_id: str, payload: s.RegenerateRequest) -> dict[str, Any]:
    """New copy or a new image for one ad of a reviewed run; the draft and the
    safety report are updated."""
    from app.schemas import ads_builder as ab
    from app.schemas import meta as ms
    from app.services import ads_builder_service, meta_builder_service

    run = _run(db, tenant_id, run_id, lock=True)
    if run.status != "ready_for_review":
        raise ConflictError("Only a run in review can be regenerated.")
    ad = next((a for a in _ad_list(run) if a["ref"] == payload.ref), None)
    ad_id = (_out(run, "assemble").get("ads") or {}).get(payload.ref)
    if ad is None or not ad_id:
        raise NotFoundError("Ad not found in this run.")
    ctx = _out(run, "context")
    copy_out = _out(run, "copy")
    vis_out = _out(run, "visuals")
    try:
        if payload.what == "copy":
            fixed, errors, _p = _write_copy(db, run, ctx, [ad], ["Write a clearly different version from the previous one."])
            if not fixed.get(payload.ref):
                raise StageFailed("; ".join(errors[:3]) or "no usable copy")
            new = fixed[payload.ref]
            _set_stage(run, "copy", output={**copy_out, "ads": {**copy_out["ads"], payload.ref: new}})
            if ad["platform"] == "meta":
                meta_builder_service.update_ad(db, tenant_id, actor, ad_id, ms.AdFields(primary_text=new.get("primary_text") or None, headline=new.get("headline") or None, description=new.get("description") or None))
            else:
                ads_builder_service.update_ad(db, tenant_id, actor, ad_id, ab.AdFields(creative={k: v for k, v in new.items() if k != "visual_brief"}))
        else:
            ratios = ap.IMAGE_RATIOS.get(ad["platform"], {}).get(ad["format"], [])
            if not ratios or ad["platform"] == "pinterest":
                raise StageFailed("This ad format has no generated image to replace.")
            media = []
            for ratio in ratios:
                result = _image_for(db, run, ctx, str((copy_out["ads"].get(payload.ref) or {}).get("visual_brief") or ""), ratio)
                up = _upload(db, run, actor, ad["platform"], f"ai-{payload.ref.replace(':', '-')}-{ratio.replace(':', 'x')}-r.png", result.image or b"")
                media.append({**up, "ratio": ratio, "preview": _preview(result.image or b"", result.mime), "source": result.provider})
            _set_stage(run, "visuals", output={**vis_out, "ads": {**(vis_out.get("ads") or {}), payload.ref: media}})
            if ad["platform"] == "meta":
                meta_builder_service.update_ad(db, tenant_id, actor, ad_id, ms.AdFields(media=[ms.Media(type="image", image_hash=media[0]["media_id"], name=media[0]["name"])]))
            else:
                ads_builder_service.update_ad(db, tenant_id, actor, ad_id, ab.AdFields(creative={"media": [{k: m[k] for k in ("media_id", "kind", "name")} for m in media]}))
    except StageFailed as exc:
        raise AppError(f"Couldn't regenerate: {exc}", 422) from None
    # Re-run the copy checks for the whole run so the report stays current.
    issues = [i for i in _out(run, "safety").get("issues") or [] if i.get("ref") != payload.ref or i.get("source") not in ("moderation", "price_check", "ai_review", "brand")]
    new_copy = _out(run, "copy")["ads"]
    issues += [i for i in _deterministic_checks(ctx, {payload.ref: new_copy.get(payload.ref) or {}})]
    _set_stage(run, "safety", output={"issues": issues})
    _audit(db, tenant_id, actor, "ai_campaign.regenerated", run_id, {"ref": payload.ref, "what": payload.what})
    return read_run(db, tenant_id, run_id)


def publish(db: Session, tenant_id: str, actor: str, actor_is_owner: bool, run_id: str, payload: s.PublishRequest) -> dict[str, Any]:
    """A person publishes a reviewed run (the only way an AI campaign goes
    live). Safety errors block; warnings must be acknowledged. Each draft uses
    its builder's normal publish, so the spend-cap approval and rollback apply."""
    from app.services import ads_builder_service, meta_builder_service

    run = _run(db, tenant_id, run_id, lock=True)
    if run.status not in ("ready_for_review", "failed"):
        raise ConflictError(f"Only a reviewed run can be published (this one is {run.status}).")
    assembled = _out(run, "assemble")
    if not assembled.get("campaigns"):
        raise ConflictError("This run has no drafts yet; retry it first.")
    issues = _issues(run)
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        raise ConflictError("Fix the safety report's errors first: " + "; ".join(i["message"] for i in errors[:4]))
    if any(i["severity"] == "warning" for i in issues) and not payload.acknowledge_warnings:
        raise ConflictError("Review and acknowledge the safety report's warnings before publishing.")
    run.status = "publishing"
    db.commit()
    results: list[dict[str, Any]] = []
    for platform, cid in assembled["campaigns"].items():
        row = db.query(Campaign.status).filter(Campaign.tenant_id == tenant_id, Campaign.id == cid).first()
        if row is None:
            results.append({"platform": platform, "ok": False, "message": "The draft was deleted."})
            continue
        if row[0] != "draft":
            results.append({"platform": platform, "ok": True, "status": row[0]})
            continue
        try:
            if platform == "meta":
                tree = meta_builder_service.publish(db, tenant_id, actor, actor_is_owner, cid, payload.mode)
                pending = bool(tree["campaign"].get("pending_approval_id"))
                status = tree["campaign"]["status"]
            else:
                tree = ads_builder_service.publish(db, tenant_id, actor, actor_is_owner, cid, payload.mode)
                pending = bool(tree["campaign"].get("pending_approval_id"))
                status = tree["campaign"]["status"]
            results.append({"platform": platform, "ok": True, "status": status, "pending": pending})
        except AppError as exc:
            db.rollback()
            results.append({"platform": platform, "ok": False, "message": str(exc.detail)[:300]})
    run = _run(db, tenant_id, run_id, lock=True)
    failed = [r for r in results if not r["ok"]]
    if failed:
        run.status = "failed"
        run.error = "publish: " + "; ".join(f"{r['platform']}: {r['message']}" for r in failed)[:600]
    elif any(r.get("pending") for r in results):
        run.status = "awaiting_approval"
    else:
        run.status = "published"
    _audit(db, tenant_id, actor, "ai_campaign.publish", run_id, {"results": results})
    return read_run(db, tenant_id, run_id)


# Pending approvals resolve through the builders; a run waiting on them is
# shown as published once every campaign left draft.
def refresh_status(db: Session, tenant_id: str, run: AICampaignRun) -> None:
    if run.status == "awaiting_approval" and len(_published_ids(db, tenant_id, run)) == len(run.campaign_ids or []):
        run.status = "published"

