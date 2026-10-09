"""AI customer-service reply evaluation (SPEC-BE-086).

Seeds the knowledge of reply_cases.json into a temporary company on the live
Postgres, inside one transaction that is rolled back at the end, and checks:

- retrieval (always, free): does ai/retrieval.retrieve_grounding() return a
  source that answers the question, within its top 5?
- with --ragas: the real reply draft (ai/prompts/reply_drafter) is scored with
  RAGAS 0.4: faithfulness, context recall, context precision (with
  reference) and factual correctness against the reference answer.

Run it with the evaluation environment, never the app one (FR1), from backend/:
  .venv-eval/Scripts/python evals/run_reply_eval.py
  .venv-eval/Scripts/python evals/run_reply_eval.py --ragas --ai-from <company slug> [--out report.json]
--ragas spends that company's AI credits (drafts + judge calls).
Exit code 0 only when every measured target is met.
"""
from __future__ import annotations

import os

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # no RAGAS telemetry (FR6)

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

CASES = Path(__file__).with_name("reply_cases.json")
TARGETS = {"retrieval_hit_rate": 0.80, "faithfulness": 0.90, "context_recall": 0.80, "factual_correctness": 0.60}
TAG = re.compile(r"\s*\[S\d+\]")


def _seed(db: Session, tag: str, knowledge: dict[str, Any]) -> dict[str, str]:
    from app.models.user import User
    from app.schemas.auth import RegisterRequest
    from app.schemas.faq import FAQCreate
    from app.schemas.policy import PolicyCreate
    from app.services import auth_service, faq_service, policy_service

    email = f"reply-eval-{tag}@example.com"
    auth_service.register(db, RegisterRequest(
        tenant_name=f"Reply Eval {tag}", tenant_slug=f"reply-eval-{tag}", email=email, password="EvalRun2026x",
        first_name="Eval", last_name="Owner", timezone="Asia/Dhaka", country_code="BD"))
    user = db.query(User).filter(User.email == email).one()
    tid, uid = str(user.tenant_id), str(user.id)
    ids: dict[str, str] = {"tenant_id": tid}
    for faq in knowledge["faqs"]:
        row = faq_service.create_faq(db, tid, uid, FAQCreate(question=faq["question"], answer=faq["answer"]))
        ids[str(row["id"])] = faq["key"]
    for policy in knowledge["policies"]:
        row = policy_service.create_policy(db, tid, uid, PolicyCreate(
            policy_type=policy["policy_type"], title=policy["title"], body=policy["body"]))
        ids[str(row["id"])] = policy["key"]
    db.commit()  # releases the savepoint only; the outer transaction is rolled back
    return ids


def _judge(db: Session, tenant_id: str) -> Any:
    """RAGAS judge = the company's first AI model it can use: Claude through
    the Anthropic SDK, or an OpenAI-compatible one (OpenAI, Gemini, Groq,
    OpenRouter, Ollama) through its OpenAI-compatible endpoint."""
    from openai import AsyncOpenAI
    from ragas.llms.base import llm_factory

    from app.ai.providers import BY_PROVIDER
    from app.services.ai_model_service import resolve_chain

    for provider, key, model in resolve_chain(db, tenant_id):
        spec = BY_PROVIDER[provider]
        if spec.style == "anthropic":
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=key)
            create = client.messages.create

            # RAGAS sends temperature/top_p, which this SDK's Claude models
            # reject (TypeError); the judge works without them.
            async def create_without_sampling(*args: Any, **kwargs: Any) -> Any:
                kwargs.pop("temperature", None)
                kwargs.pop("top_p", None)
                return await create(*args, **kwargs)

            client.messages.create = create_without_sampling  # type: ignore[method-assign]
            return llm_factory(model, provider="anthropic", client=client, max_tokens=8192), f"{provider}:{model}"
        if spec.style == "openai":
            base_url = spec.url.removesuffix("/chat/completions")
            # Thinking models spend output tokens before answering: leave room.
            return llm_factory(model, provider="openai", client=AsyncOpenAI(api_key=key, base_url=base_url), max_tokens=8192), f"{provider}:{model}"
    raise SystemExit("The company has no usable AI model to judge with (Claude or an OpenAI-compatible one).")


def _similarities(db: Session, tid: str, keys: dict[str, str], cases: list[dict[str, Any]]) -> None:
    """SPEC-BE-087 D3: the data to set EMBEDDINGS_MIN_SIMILARITY for the
    configured model. A good value sits above every unanswerable question's
    best match and below as many right answers as possible."""
    from app.ai import embeddings
    from app.services import knowledge_index_service as index

    model = embeddings.model_id()
    if model is None:
        raise SystemExit("Embeddings are off: set EMBEDDINGS_* in backend/.env or pass --embeddings-from <slug>.")
    current = index.units(db, tid)
    index.refresh(db, tid, current, model)
    right: list[float] = []
    wrong_unanswerable: list[float] = []
    print(f"Model {model}")
    for case, vector in zip(cases, embeddings.embed([c["question"] for c in cases], "query"), strict=True):
        scored = [(keys.get(u.source_id, u.source_id), s) for u, s in index.search(db, tid, vector, current, model, -1.0, 1000)]
        best_right = max((s for k, s in scored if k in case["sources"]), default=None)
        best_wrong = max((s for k, s in scored if k not in case["sources"]), default=None)
        if best_right is not None:
            right.append(best_right)
        elif best_wrong is not None:
            wrong_unanswerable.append(best_wrong)
        print(f"  {case['id']:<24} right {'-' if best_right is None else f'{best_right:.3f}'}   best wrong "
              f"{'-' if best_wrong is None else f'{best_wrong:.3f}'}")
    if right and wrong_unanswerable:
        floor = max(wrong_unanswerable)
        kept = sum(1 for s in right if s > floor)
        print(f"Unanswerable questions' best wrong match: {floor:.3f}. A threshold just above it keeps {kept}/{len(right)} "
              f"right answers semantically (full-text search may still find the others).")


def _use_saved_key(slug: str) -> None:
    """Embeddings for this run from a company's saved AI Models key (OpenAI or
    Gemini), set on the in-memory settings only: nothing is written."""
    from pydantic import SecretStr

    from app.config import get_settings
    from app.services.ai_model_service import resolve_chain

    engine = create_engine(get_settings().DATABASE_URL_SYNC.get_secret_value())
    with Session(engine) as db:
        tid = db.execute(text("SELECT id FROM tenants WHERE slug = :s"), {"s": slug}).scalar_one_or_none()
        chain = resolve_chain(db, str(tid)) if tid else []
        db.rollback()
    engine.dispose()
    for provider, key, _model in chain:
        if provider in ("openai", "gemini"):
            s = get_settings()
            s.EMBEDDINGS_PROVIDER, s.EMBEDDINGS_API_KEY, s.EMBEDDINGS_MODEL = provider, SecretStr(key), ""  # type: ignore[assignment]
            print(f"Embeddings for this run: {provider} key saved for {slug!r} (in memory only).")
            return
    raise SystemExit(f"No enabled OpenAI or Gemini key is saved in AI Models for company {slug!r}.")


async def _score(metrics: dict[str, Any], case: dict[str, Any], reply: str, contexts: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    async def run(name: str, coro: Any) -> None:
        try:
            out[name] = round(float((await coro).value), 3)
        except Exception as exc:  # a failed judge call is reported, not hidden
            out[name] = None
            out[f"{name}_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    q, ref = case["question"], case["reference"]
    if contexts:
        await run("faithfulness", metrics["faithfulness"].ascore(user_input=q, response=reply, retrieved_contexts=contexts))
        await run("context_recall", metrics["context_recall"].ascore(user_input=q, retrieved_contexts=contexts, reference=ref))
        await run("context_precision", metrics["context_precision"].ascore(user_input=q, reference=ref, retrieved_contexts=contexts))
    await run("factual_correctness", metrics["factual_correctness"].ascore(response=reply, reference=ref))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ragas", action="store_true", help="draft real replies and score them with RAGAS (costs AI credits)")
    parser.add_argument("--ai-from", help="company slug whose saved AI models draft and judge")
    parser.add_argument("--case", action="append", help="run only these case ids")
    parser.add_argument("--out", help="save the full report as JSON")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds to wait between cases (rate-limited keys)")
    parser.add_argument("--compare", action="store_true", help="also show full-text-only retrieval (before SPEC-BE-087)")
    parser.add_argument("--fake-embeddings", action="store_true",
                        help="answer embedding calls with dev_fakes word-hash vectors (plumbing check, not semantic)")
    parser.add_argument("--similarities", action="store_true",
                        help="print each question's cosine to its right source and to the best wrong one, to set EMBEDDINGS_MIN_SIMILARITY")
    parser.add_argument("--embeddings-from",
                        help="use the OpenAI/Gemini key saved in AI Models for this company slug, in memory only (no .env change)")
    args = parser.parse_args()
    if args.ragas and not args.ai_from:
        parser.error("--ragas needs --ai-from <company slug>")

    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    for name in ("ragas", "httpx", "openai", "instructor"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        import truststore  # the OS certificate store, as pip uses (FR6)

        truststore.inject_into_ssl()
    except ImportError:
        pass

    import app.main  # noqa: F401  (registers every model)
    from app.db.session import engine as app_engine

    app_engine.echo = False  # APP_DEBUG echoes SQL; results only here
    if args.fake_embeddings:
        from pydantic import SecretStr

        from app.config import get_settings as _settings
        from app.integrations import dev_fakes

        dev_fakes.install()
        _settings().EMBEDDINGS_PROVIDER, _settings().EMBEDDINGS_API_KEY = "openai", SecretStr("fake")
    if args.embeddings_from:
        _use_saved_key(args.embeddings_from)
    from app.ai.llm_client import LLMProviderError
    from app.ai.prompts.reply_drafter import HistoryMessage, generate_reply_draft, is_bengali
    from app.ai.retrieval import retrieve_grounding
    from app.config import get_settings

    data = json.loads(CASES.read_text(encoding="utf-8"))
    cases = [c for c in data["cases"] if not args.case or c["id"] in args.case]
    engine = create_engine(get_settings().DATABASE_URL_SYNC.get_secret_value())
    conn = engine.connect()
    outer = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    tag = uuid.uuid4().hex[:10]
    results: list[dict[str, Any]] = []
    judge_name = None
    try:
        keys = _seed(db, tag, data["knowledge"])
        tid = keys["tenant_id"]
        metrics: dict[str, Any] = {}
        if args.ragas:
            copied = db.execute(text(
                "UPDATE tenants SET settings = jsonb_set(COALESCE(settings, '{}'::jsonb), '{llm_providers}', "
                "(SELECT settings->'llm_providers' FROM tenants WHERE slug = :s AND settings ? 'llm_providers')) "
                "WHERE id = :t AND EXISTS (SELECT 1 FROM tenants WHERE slug = :s AND settings ? 'llm_providers') RETURNING id"),
                {"s": args.ai_from, "t": tid}).scalar_one_or_none()
            if not copied:
                print(f"No saved AI models found for company slug {args.ai_from!r}.")
                return 2
            db.commit()
            from ragas.metrics.collections import ContextPrecisionWithReference, ContextRecall, FactualCorrectness, Faithfulness

            llm, judge_name = _judge(db, tid)
            metrics = {"faithfulness": Faithfulness(llm=llm), "context_recall": ContextRecall(llm=llm),
                       "context_precision": ContextPrecisionWithReference(llm=llm), "factual_correctness": FactualCorrectness(llm=llm)}

        if args.similarities:
            _similarities(db, tid, keys, cases)
            cases = []

        for case in cases:
            sources = retrieve_grounding(db, tid, case["question"])
            got = [keys.get(s.id, s.id) for s in sources]
            rank = next((i for i, k in enumerate(got, start=1) if k in case["sources"]), None)
            row: dict[str, Any] = {"id": case["id"], "kind": case["kind"], "expected": case["sources"], "retrieved": got, "hit_rank": rank}
            if args.compare:
                # SPEC-BE-087 FR9: today's full-text search alone, side by side.
                from app.ai.retrieval import _fulltext

                kw = [keys.get(s.id, s.id) for s in _fulltext(db, tid, case["question"])]
                row["keyword_hit_rank"] = next((i for i, k in enumerate(kw, start=1) if k in case["sources"]), None)
            if args.ragas:
                if args.delay and results:
                    import time

                    time.sleep(args.delay)
                try:
                    draft = generate_reply_draft(db, tid, [HistoryMessage(sender_type="customer", body=case["question"])])
                    reply = TAG.sub("", draft.body).strip()
                    row.update(reply=reply, fallback=draft.fallback, cited=[keys.get(s.id, s.id) for s in draft.sources])
                    if case.get("reply_script") == "bengali":
                        row["language_ok"] = is_bengali(reply)  # SPEC-BE-089 FR4
                    if draft.fallback == "no_grounding":
                        # A hand-over states no facts: right when the knowledge
                        # can't answer, a miss when it can (FR4).
                        row["fallback_ok"] = not case["sources"]
                    else:
                        row.update(asyncio.run(_score(metrics, case, reply, [s.snippet for s in sources])))
                except LLMProviderError as exc:
                    row["draft_error"] = str(exc.detail)[:200]
            results.append(row)
            _print_row(row, args.ragas)
    finally:
        db.close()
        outer.rollback()
        left = conn.execute(text("SELECT count(*) FROM tenants WHERE slug = :s"), {"s": f"reply-eval-{tag}"}).scalar_one()
        conn.close()

    summary = _summary(results, args.ragas)
    print("\nSummary" + (f" (judge {judge_name})" if judge_name else ""))
    ok = True
    for name, value in summary.items():
        target = TARGETS.get(name)
        verdict = "" if target is None or value is None else ("  meets target" if value >= target else f"  BELOW target {target:.2f}")
        ok &= not verdict.startswith("  BELOW")
        print(f"  {name}: {'n/a' if value is None else f'{value:.2f}' if isinstance(value, float) else value}{verdict}")
    print(f"Rolled back; temporary company rows left: {left}.")
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "judge": judge_name, "cases": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1


def _avg(values: list[Any]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    return round(sum(nums) / len(nums), 3) if nums else None


def _summary(results: list[dict[str, Any]], ragas: bool) -> dict[str, Any]:
    answerable = [r for r in results if r["expected"]]
    summary: dict[str, Any] = {
        "retrieval_hit_rate": round(sum(1 for r in answerable if r["hit_rank"]) / len(answerable), 3) if answerable else None,
        "retrieval_hits": f"{sum(1 for r in answerable if r['hit_rank'])}/{len(answerable)}",
    }
    if answerable and "keyword_hit_rank" in answerable[0]:
        summary["keyword_only_hits"] = f"{sum(1 for r in answerable if r['keyword_hit_rank'])}/{len(answerable)}"
    if ragas:
        summary.update({
            "faithfulness": _avg([r.get("faithfulness") for r in results]),
            "context_recall": _avg([r.get("context_recall") for r in answerable]),
            "context_precision": _avg([r.get("context_precision") for r in answerable]),
            "factual_correctness": _avg([r.get("factual_correctness") for r in answerable]),
            "hand_overs": f"{sum(1 for r in results if r.get('fallback') == 'no_grounding')} "
                          f"({sum(1 for r in results if r.get('fallback_ok') is False)} on answerable questions)",
            "language_matches": f"{sum(1 for r in results if r.get('language_ok'))}/"
                                f"{sum(1 for r in results if 'language_ok' in r)}",
            "errors": sum(1 for r in results if r.get("draft_error") or any(k.endswith("_error") for k in r)),
        })
    return summary


def _print_row(row: dict[str, Any], ragas: bool) -> None:
    hit = "n/a (no source answers it)" if not row["expected"] else (f"hit at rank {row['hit_rank']}" if row["hit_rank"] else "MISS")
    if "keyword_hit_rank" in row and row["expected"]:
        hit += f" (keyword only: {'rank ' + str(row['keyword_hit_rank']) if row['keyword_hit_rank'] else 'MISS'})"
    print(f"{row['id']} [{row['kind']}]: retrieval {hit}; retrieved {row['retrieved'] or 'nothing'}")
    if not ragas:
        return
    if row.get("draft_error"):
        print(f"    draft error: {row['draft_error']}")
        return
    print(f"    reply: {row.get('reply', '')[:220]!r}")
    if "language_ok" in row:
        print(f"    reply language: {'matches the customer' if row['language_ok'] else 'WRONG language'}")
    if row.get("fallback"):
        print(f"    hand-over (no grounding): {'correct' if row.get('fallback_ok') else 'MISSED an answerable question'}")
        return
    scores = {k: row.get(k) for k in ("faithfulness", "context_recall", "context_precision", "factual_correctness") if k in row}
    print(f"    scores: {scores}")
    for k, v in row.items():
        if k.endswith("_error"):
            print(f"    {k}: {v}")


if __name__ == "__main__":
    raise SystemExit(main())
