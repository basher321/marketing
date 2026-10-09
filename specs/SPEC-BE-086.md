# SPEC-BE-086: RAGAS evaluation of AI customer-service replies

Status: IMPLEMENTED (2026-10-09). The RAGAS scores are not measured yet: the judge and drafting
model ran out of quota.
- **Environment (AC1):** `backend/.venv` `pip freeze` is identical to its pre-work snapshot. An
  accidental `pip install ragas` into it was fully reverted; it had changed `pydantic-settings`,
  `rich` and `websockets`. `backend/.venv-eval` imports `app.main` and `ragas` 0.4.3 with the
  app's pins.
- **Retrieval (AC2):** the right source is found for 8 of 13 answerable questions (0.61, below the
  0.80 target). The misses: 3 of 4 paraphrases, the PayPal inference question, and the Bengali
  question (`_keywords` keeps only `[a-z0-9]`, so Bengali text gives no keywords and gets the
  hand-over template).
- **RAGAS (AC3, not met):** run against company `pilotsonic`'s Gemini (`gemini-3.8-flash`). The
  first call got HTTP 503 (high demand), and then every drafting and judge call got HTTP 429
  "You exceeded your current quota". One reply was drafted (cash on delivery: grounded and
  correct by reading, but unscored). A retry a few minutes later was still 429. Re-run when the
  quota resets, or with a paid key, using `--delay`.
- **Isolation (AC4):** no temporary company remained, and pilotsonic's settings are unchanged
  (`last_error` null, `last_ok_at` 2026-10-08).

Requested by the user ("yes do it and execute"), after the advice that RAGAS fits the AI reply
drafts (knowledge-grounded answers), not Command Chat / Create with AI (SPEC-BE-085 already
measures those).

## Context

AI reply drafts (SPEC-BE-027, used by the Inbox and SocialAPI) work as follows:
1. `ai/retrieval.retrieve_grounding()` finds up to 5 sources for the customer's latest message:
   Postgres full-text search over `kb_documents`, enabled `faqs` and in-effect `policies`.
   Keywords are `[a-z0-9]` only, and there are no embeddings.
2. `ai/prompts/reply_drafter.generate_reply_draft()` asks the company's AI model to answer from
   those sources, citing `[S1]…`.
3. When nothing is retrieved, the reply is a fixed hand-over template (`fallback="no_grounding"`).

Nothing measures whether the right sources are found or whether the reply sticks to them.

## Functional requirements

**FR1 Separate environment.** RAGAS and its dependencies (langchain, openai, datasets, …) never
enter the app environment.
- They live in `backend/.venv-eval`, built from `backend/evals/requirements-eval.txt`
  (`-r ../requirements.txt` plus `ragas==0.4.3` and `truststore`). The app's pins win.
- `.venv-eval/` is git-ignored.
- `requirements.txt` is unchanged, so SPEC-BE-001 is unchanged.

**FR2 Golden set.** `backend/evals/reply_cases.json` holds:
- a small knowledge base (FAQs and policies, each with a key);
- customer questions, each with a reference answer written from that knowledge and the keys of
  the sources that answer it (`[]` = the knowledge doesn't answer it).

The set mixes:
- questions sharing words with their source;
- paraphrases sharing none;
- questions the knowledge can't answer;
- a Bengali question.

**FR3 Retrieval check (free, always runs).** For each case it records what `retrieve_grounding`
returns. It reports the hit rate (an expected source in the top 5) and the rank of the first
hit. No AI call is made.

**FR4 RAGAS scoring (`--ragas --ai-from <company slug>`).**
- The reply is drafted by the real `generate_reply_draft`, using the AI models saved for that
  company (copied into the temporary company inside the rolled-back transaction).
- It is then scored with RAGAS 0.4 metrics, judged by the same company's first OpenAI-compatible
  model (OpenAI, Gemini or Groq, through its OpenAI-compatible endpoint):
  - **Faithfulness:** the reply's claims are supported by the retrieved sources. This is the
    "made-up answer" score.
  - **ContextRecall:** the retrieved sources contain the reference answer.
  - **ContextPrecisionWithReference:** useful sources are ranked first.
  - **FactualCorrectness (F1):** the reply against the reference answer.
- Citation tags are removed before scoring.
- A `no_grounding` fallback reply is not scored for faithfulness (it states no facts). It counts
  as correct for cases the knowledge can't answer, and as a miss otherwise.
- Without `--ragas`, nothing calls an AI model.

**FR5 Report.**
- Per case: retrieved keys, hit / rank, the fallback, and the four scores.
- Averages, compared with targets: retrieval hit rate ≥ 0.80, faithfulness ≥ 0.90, context
  recall ≥ 0.80, factual correctness ≥ 0.60.
- `--out <file.json>` saves everything.
- The exit code is 0 only when every measured target is met.

**FR6 Isolation.**
- Everything runs on the live Postgres inside one transaction that is rolled back, with a
  temporary company and no rows left behind.
- RAGAS telemetry is off (`RAGAS_DO_NOT_TRACK=true`), and no prompt or answer is sent anywhere
  except the company's own AI provider.
- `truststore` makes Python use the operating system's certificate store (as pip does).

## Non-functional

- No app code, DDL or setting changes. The retrieval and drafter code stay as they are: this
  spec measures them. Improving retrieval (e.g. embeddings) is a follow-up, decided on these
  results.
- Cost: with `--ragas`, about 1 drafting call plus about 5–10 judge calls per case, on that
  company's AI credits.

## Target files

- `backend/evals/requirements-eval.txt`, `backend/evals/reply_cases.json`,
  `backend/evals/run_reply_eval.py` (new)
- `.gitignore` (`backend/.venv-eval/`)
- `CLAUDE.md` (commands)

## Acceptance criteria

1. `backend/.venv` is unchanged (`pip freeze` identical before and after), and
   `backend/.venv-eval` imports both `app.main` and `ragas`.
2. The retrieval check runs with no AI call and prints the hit rate per case and in total.
3. With `--ragas --ai-from <slug>`, every case gets a real draft and the four scores, or a
   stated reason why a score is missing.
4. Nothing persists: no temporary company remains after the run, and the source company's
   settings are unchanged.
5. `ruff check evals` passes, and `ruff check app` / `mypy app` stay at their baselines.
