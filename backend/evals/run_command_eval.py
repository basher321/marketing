"""Command Chat evaluation runner (SPEC-BE-085 FR13).

Runs every case of command_chat_cases.json through the real planner
(orchestrator_service.send_message_and_plan) on the live Postgres, inside one
transaction that is rolled back at the end. A temporary company is seeded
(products, a shipping zone, a campaign); no plan step is executed.

Usage, from backend/ with the venv active:
  python evals/run_command_eval.py
      Stub mode: the "model" returns each case's recorded model_output, so the
      code guards are tested. No AI call, no cost.
  python evals/run_command_eval.py --live --ai-from <company slug>
      Live mode: the AI models saved for that company (Integrations > AI
      Models) answer each command. This measures the real accuracy and spends
      that company's AI credits.

Exit code 0 when every case passes.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.ai.llm_client import LLMCompletion  # noqa: E402
from app.config import get_settings  # noqa: E402

CASES = Path(__file__).with_name("command_chat_cases.json")
TIMEZONE = "Asia/Dhaka"
PRODUCTS = [
    ("SKU-TSHIRT-RED", "Red Cotton T-Shirt", 79000),
    ("SKU-MUG", "Ceramic Coffee Mug", 45000),
    ("SKU-CAP", "Baseball Cap", 35000),
]


class StubModel:
    """Returns the queued answers in order (stub mode)."""

    def __init__(self) -> None:
        self.answers: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    def complete_with_usage(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024, timeout_s: float = 30.0,
                            *, db: Any = None, tenant_id: Any = None, temperature: float | None = None) -> LLMCompletion:
        self.calls.append({"temperature": temperature})
        answer = self.answers.pop(0) if self.answers else {"new_request": True, "summary": "", "ask": [], "actions": []}
        body = answer if isinstance(answer, str) else json.dumps(answer)
        return LLMCompletion(text=body, provider="stub", model="stub", input_tokens=0, output_tokens=0, is_mock=False)


def _substitute(value: Any, names: dict[str, str]) -> Any:
    if isinstance(value, str):
        for key, real in names.items():
            if value == key:
                return real
        return value
    if isinstance(value, list):
        return [_substitute(v, names) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, names) for k, v in value.items()}
    return value


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(_same(v, actual.get(k)) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(_same(e, a) for e, a in zip(expected, actual))
    if isinstance(expected, (int, float, str)) and not isinstance(expected, bool):
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except (InvalidOperation, ValueError):
            return expected == actual
    return expected == actual


def _seed(db: Session, tag: str) -> dict[str, str]:
    from app.models.user import User
    from app.schemas.auth import RegisterRequest
    from app.schemas.shipping import ShippingZoneCreate
    from app.services import auth_service, shipping_service

    email = f"eval-{tag}@example.com"
    auth_service.register(db, RegisterRequest(
        tenant_name=f"Eval {tag}", tenant_slug=f"eval-{tag}", email=email, password="EvalRun2026x",
        first_name="Eval", last_name="Owner", timezone=TIMEZONE, country_code="BD"))
    user = db.query(User).filter(User.email == email).one()
    tid, uid = str(user.tenant_id), str(user.id)
    db.execute(text("UPDATE tenants SET timezone = :z WHERE id = :t"), {"z": TIMEZONE, "t": tid})
    for sku, title, cents in PRODUCTS:
        db.execute(text("INSERT INTO products (tenant_id, sku, title, slug, default_price_cents, status, currency) "
                        "VALUES (:t, :s, :ti, :sl, :c, 'active', 'BDT')"),
                   {"t": tid, "s": sku, "ti": title, "sl": sku.lower(), "c": cents})
    zone = shipping_service.create_zone(db, tid, uid, ShippingZoneCreate(name="Bangladesh", country_codes=["BD"]))
    campaign_id = db.execute(text("INSERT INTO campaigns (tenant_id, name, objective, budget_cents, daily_cap_cents, status) "
                                  "VALUES (:t, 'Summer Sale', 'traffic', 100000, 10000, 'running') RETURNING id"), {"t": tid}).scalar_one()
    db.commit()  # releases the savepoint only; the outer transaction is still rolled back
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    names = {"@zone:Bangladesh": str(zone["id"]), "@campaign:Summer Sale": str(campaign_id)}
    names.update({f"@date:+{n}": (today + timedelta(days=n)).isoformat() for n in range(0, 61)})
    return {"tenant_id": tid, "user_id": uid, **names}


def _stamp(db: Session, tid: str) -> None:
    # orchestrator_messages.created_at defaults to now(), which is the same
    # instant for every row of one transaction; give the rows just written
    # the wall-clock time so "the latest message" means what it does in
    # production, where every request is its own transaction.
    db.execute(text("UPDATE orchestrator_messages SET created_at = clock_timestamp() WHERE tenant_id = :t AND created_at = now()"), {"t": tid})
    db.commit()


def _run_case(db: Session, case: dict[str, Any], seed: dict[str, str], stub: StubModel | None) -> list[str]:
    """A case may say which ad platforms its company connected directly
    ("direct_ad_platforms", SPEC-BE-102); the seeded company has none."""
    from app.services import orchestrator_service as orch

    direct = case.get("direct_ad_platforms")
    if direct is None:
        return _run_case_inner(db, case, seed, stub)
    real = orch._direct_ad_platforms
    orch._direct_ad_platforms = lambda _db, _tid: list(direct)  # type: ignore[assignment]
    try:
        return _run_case_inner(db, case, seed, stub)
    finally:
        orch._direct_ad_platforms = real  # type: ignore[assignment]


def _run_case_inner(db: Session, case: dict[str, Any], seed: dict[str, str], stub: StubModel | None) -> list[str]:
    from app.models.orchestrator import OrchestratorMessage
    from app.services import orchestrator_service as orch

    tid, uid = seed["tenant_id"], seed["user_id"]
    names = {k: v for k, v in seed.items() if k.startswith("@")}
    orch.discard_draft(db, tid, uid)  # each case starts with no pending question
    _stamp(db, tid)
    calls_before = len(stub.calls) if stub else 0
    result: dict[str, Any] = {}
    for turn in case["turns"]:
        if stub is not None:
            answers = turn.get("model_output")
            stub.answers = [_substitute(a, names) for a in (answers if isinstance(answers, list) else [answers])]
        result = orch.send_message_and_plan(db, tid, uid, turn["message"], role="owner")
        _stamp(db, tid)
    expect = _substitute(case["expect"], names)
    reply = db.query(OrchestratorMessage).filter(OrchestratorMessage.id == result["reply"]["id"]).one()
    info = reply.parsed_intent if isinstance(reply.parsed_intent, dict) else {}
    kind = info.get("kind") or "message"
    problems: list[str] = []
    if expect.get("kind") and kind != expect["kind"]:
        problems.append(f"kind {kind!r}, expected {expect['kind']!r} (reply: {reply.content[:160]!r})")
    if "asks" in expect and sorted(info.get("missing_labels") or []) != sorted(expect["asks"]):
        problems.append(f"asked {info.get('missing_labels')}, expected {expect['asks']}")
    if "dropped" in expect and sorted(info.get("dropped") or []) != sorted(expect["dropped"]):
        problems.append(f"dropped {info.get('dropped')}, expected {expect['dropped']}")
    if "left_out" in expect and sorted(x["field"] for x in info.get("left_out") or []) != sorted(expect["left_out"]):
        problems.append(f"left out {info.get('left_out')}, expected {expect['left_out']}")
    actions = (result.get("plan") or {}).get("actions") or []
    if "actions" in expect:
        got_types = [a["type"] for a in actions]
        want_types = [a["type"] for a in expect["actions"]]
        if got_types != want_types:
            problems.append(f"steps {got_types}, expected {want_types}")
        else:
            for want, got in zip(expect["actions"], actions):
                if not _same(want.get("params") or {}, got.get("params") or {}):
                    problems.append(f"{got['type']} params {got.get('params')}, expected to include {want.get('params')}")
    for index, field in expect.get("absent") or []:
        params = actions[index - 1].get("params") if len(actions) >= index else {}
        if field in (params or {}):
            problems.append(f"step {index} still has {field}={params[field]!r}")
    if stub is not None and "llm_calls" in expect and len(stub.calls) - calls_before != expect["llm_calls"]:
        problems.append(f"{len(stub.calls) - calls_before} model calls, expected {expect['llm_calls']}")
    if stub is not None and any(c["temperature"] != 0.0 for c in stub.calls[calls_before:]):
        problems.append("the planner didn't ask for temperature 0")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="use real AI models (costs AI credits)")
    parser.add_argument("--ai-from", help="company slug whose saved AI models answer in --live mode")
    parser.add_argument("--case", action="append", help="run only these case ids")
    args = parser.parse_args()
    if args.live and not args.ai_from:
        parser.error("--live needs --ai-from <company slug>")
    import logging

    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))  # results only

    from app.services import orchestrator_service as orch

    cases = [c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"] if not args.case or c["id"] in args.case]
    mode = "live" if args.live else "stub"
    engine = create_engine(get_settings().DATABASE_URL_SYNC.get_secret_value())
    conn = engine.connect()
    outer = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    tag = uuid.uuid4().hex[:10]
    original_llm, original_schedule = orch.command_llm, orch.schedule_execution
    stub = None if args.live else StubModel()
    passed = 0
    run = [c for c in cases if mode in c.get("modes", ["stub", "live"])]
    try:
        seed = _seed(db, tag)
        if args.live:
            copied = db.execute(text(
                "UPDATE tenants SET settings = jsonb_set(COALESCE(settings, '{}'::jsonb), '{llm_providers}', "
                "(SELECT settings->'llm_providers' FROM tenants WHERE slug = :s AND settings ? 'llm_providers')) "
                "WHERE id = :t AND EXISTS (SELECT 1 FROM tenants WHERE slug = :s AND settings ? 'llm_providers') RETURNING id"),
                {"s": args.ai_from, "t": seed["tenant_id"]}).scalar_one_or_none()
            if not copied:
                print(f"No saved AI models found for company slug {args.ai_from!r}.")
                return 2
        else:
            orch.command_llm = stub  # type: ignore[assignment]
        orch.schedule_execution = lambda *a, **k: None  # plans are scored, never executed
        for case in run:
            try:
                problems = _run_case(db, case, seed, stub)
            except Exception as exc:  # a crash is a failed case, not a stopped run
                db.rollback()
                problems = [f"crashed: {type(exc).__name__}: {exc}"]
            status = "PASS" if not problems else "FAIL"
            passed += not problems
            print(f"{status}  {case['id']}: {case['what']}")
            for p in problems:
                print(f"      - {p}")
    finally:
        orch.command_llm, orch.schedule_execution = original_llm, original_schedule
        db.close()
        outer.rollback()
        left = conn.execute(text("SELECT count(*) FROM tenants WHERE slug = :s"), {"s": f"eval-{tag}"}).scalar_one()
        conn.close()
    print(f"\n{mode} mode: {passed}/{len(run)} cases passed. Rolled back; temporary company rows left: {left}.")
    return 0 if passed == len(run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
