# SPEC-BE-087: Meaning-based (embedding) search for AI customer-service replies

Status: IMPLEMENTED (2026-10-09). The DDL is applied to the live DB.
- **Checks:** 18 of 18 pass with dev fakes on the live Postgres, in a rolled-back transaction
  (AC1, AC2, AC3, FR6, both providers). No row persisted.
- **Regressions:** the SPEC-BE-085 suites still pass (31/31 golden cases, 18/18 checks).
- **Lint and types:** ruff and mypy at their baselines.
- **AC4 (real-model gain) is pending:** `EMBEDDINGS_PROVIDER=none` in `backend/.env` until the
  operator adds an OpenAI or Gemini key. The dev-fake vectors match shared words only, so the
  golden set stays at 8/13 with them (paraphrases and Bengali-vs-English share no words).

Decisions:
- **Storage:** the user first chose pgvector. It can't be installed here (no C++ build tools,
  and the Postgres folder needs admin rights), so the user said "go for chromadb or others
  suitable for my system". Chosen: a plain Postgres table with `real[]` vectors, compared in
  Python (D1 below).
- **Key:** one platform key (D2 = B).
- **Threshold:** 0.60, tuned on the golden set (D3 = A).

## Context

SPEC-BE-086 measured `ai/retrieval.retrieve_grounding()`: the right FAQ or policy is found for
8 of 13 answerable questions (target 0.80).
- **Paraphrases miss:** "parcel hasn't arrived" vs the tracking FAQ, "swap it" vs size exchange,
  "headphones stopped working" vs the warranty.
- **Bengali always misses:** `_keywords` keeps only `[a-z0-9]`.
- **Effect:** the customer gets the hand-over template although the answer exists.

Facts checked on 2026-10-09:
- **Database:** live server PostgreSQL 16.15, no pgvector; `pg_trgm` is installed.
- **Existing column:** `kb_documents.embedding` (jsonb) is unused and stays unused.
- **No numpy:** the app has no numpy; similarity is computed in plain Python.

## Decisions

- **D1 Storage: a new Postgres table (ChromaDB not used).** A separate vector database would be
  a second store to back up and keep in sync. It would hold every company's data outside the
  tenant-filtered Postgres, and add heavy dependencies (onnxruntime). Its default model is
  English-only. A company's knowledge is hundreds of rows, so plain Python cosine over unit
  vectors (768 dimensions) is fast enough. If it ever isn't, the table can move to pgvector
  without API changes.
- **D2 One platform key** in `backend/.env`: the platform owner pays.
- **D3 Threshold:** cosine ≥ 0.60 for a semantic hit, tuned on the golden set.

## Functional requirements

**FR1 Table** (additive DDL, applied by this spec):
```sql
CREATE TABLE knowledge_embeddings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  source_kind text NOT NULL CHECK (source_kind IN ('faq', 'policy', 'kb_document')),
  source_id uuid NOT NULL,
  chunk integer NOT NULL DEFAULT 0,
  content_hash text NOT NULL,
  model text NOT NULL,
  dims integer NOT NULL,
  embedding real[] NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_kind, source_id, chunk, model)
);
CREATE INDEX ix_knowledge_embeddings_tenant_model ON knowledge_embeddings (tenant_id, model);
```

**FR2 Settings** (`config.py`; SPEC-BE-002/003 amended):
- `EMBEDDINGS_PROVIDER`: `none` (default) | `openai` | `gemini`.
- `EMBEDDINGS_API_KEY` (secret).
- `EMBEDDINGS_MODEL`: empty = `text-embedding-3-small` / `gemini-embedding-001`.
- `EMBEDDINGS_DIMENSIONS`: 768.

**FR3 Client (`ai/embeddings.py`).** Plain `httpx` with a swappable `client_factory`, a 10 s
timeout, and keys never logged.
- **OpenAI:** `POST /v1/embeddings` with `dimensions`.
- **Gemini:** `models/{model}:batchEmbedContents` with `outputDimensionality` and `taskType`
  (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`); the key goes in the `x-goog-api-key` header.
- Batches of up to 100 texts. Vectors are normalized to unit length.
- Any failure raises `EmbeddingError`.

**FR4 Index (`services/knowledge_index_service.py`).** Index units:
- enabled FAQs (question + answer);
- enabled, in-effect policies (title + body);
- KB documents (title + body, split into ~1,000-character chunks at paragraph or sentence
  boundaries).

`refresh(db, tenant_id)`:
- embeds units that are missing or whose SHA-256 content hash changed, at most 50 per call;
- deletes rows whose source unit no longer exists;
- writes inside a savepoint of the caller's session, so the caller's commit keeps them.

No change to the FAQ, policy or KB write paths: the index catches up on the next retrieval.

**FR5 Hybrid retrieval.** `retrieve_grounding` keeps its signature and return type.
1. Run today's full-text search.
2. When embeddings are on: `refresh`, embed the customer message, and rank the tenant's rows
   for the current model by cosine. Keep those ≥ the threshold (top 10); only sources that are
   still valid count.
3. Merge both lists by reciprocal rank fusion (k = 60; a source found by both scores both) and
   return the top `limit`.

A source found only semantically gets its title and text from its row, with the same
validity filters as today (FAQ enabled, policy enabled and in effect).

**FR6 Never worse than today.** With `EMBEDDINGS_PROVIDER=none`, an empty key, or any
`EmbeddingError` / timeout, retrieval returns exactly today's full-text result, and the
failure is logged once per call. Reply drafting never fails because of embeddings.

**FR7 Bengali.** Text is embedded as written (both models are multilingual).

**FR8 Dev fakes.** `dev_fakes` answers both embedding APIs with deterministic hashed
bag-of-words vectors: texts sharing words are similar. `FAIL["openai" | "gemini"]` injects a
failure.

**FR9 Measured.** `evals/run_reply_eval.py --compare` prints the keyword-only and hybrid hit
rates side by side on the SPEC-BE-086 golden set.

## Target files

- `ai/embeddings.py` (new)
- `services/knowledge_index_service.py` (new)
- `ai/retrieval.py`
- `config.py`
- `integrations/dev_fakes.py`
- `evals/run_reply_eval.py`
- `backend/.env` (`EMBEDDINGS_*` lines, provider `none`)
- `specs/SPEC-BE-002.md` / `003.md` (amendment)
- `CLAUDE.md`

## Acceptance criteria

1. With dev fakes, retrieval indexes the tenant's FAQs, policies and KB chunks. It re-embeds
   only changed rows, and deletes rows of removed sources.
2. With embeddings off, or failing, the result equals today's full-text result exactly.
3. With dev fakes, a paraphrase sharing no keyword with the FAQ but sharing words with its
   answer is found semantically. Tenant isolation holds: another company's rows are never
   ranked.
4. With a real key: on the golden set the hit rate is ≥ 0.80, the Bengali question is found,
   and the not-in-knowledge questions still hand over or invent nothing. **Pending a working
   OpenAI / Gemini key.**
5. `ruff` / `mypy` at their baselines; live-DB checks in rolled-back transactions; the DDL is
   applied.

## Amendment (2026-10-09): any embedding-capable key

Requested by the user: "make it for any api key like claude openai genai and others".
- **Providers:** `EMBEDDINGS_PROVIDER` = `auto` (new default) | `none` | `openai` | `gemini` | `voyage` | `mistral` | `cohere` |
  `openai_compatible`. `openai_compatible` needs `EMBEDDINGS_BASE_URL` + `EMBEDDINGS_MODEL`, and covers Together,
  Jina, Ollama, LM Studio and similar.
- **`auto`:** recognises the key by its documented prefix: `AIza` Gemini, `pa-` Voyage, `sk-` OpenAI, `sk-ant-` Anthropic,
  `gsk_` Groq. With no `EMBEDDINGS_API_KEY`, it tries `LLM_API_KEY`.
- **Keys with no embeddings API:** Anthropic (Claude) and Groq have none, so their keys switch embeddings off and log
  why, once per process (Anthropic recommends Voyage AI). Mistral and Cohere keys have no recognisable prefix, so
  they need the explicit provider.
- **Vector size:** sent only where the API accepts it. OpenAI and Gemini take any size; Voyage takes 256/512/1024/2048;
  Cohere v4 takes 256/512/1024/1536; Mistral and OpenAI-compatible servers use their own size. The stored model tag
  is `<provider>:<model>@<size|native>`, so vectors of different models are never compared.
- **Checks:** dev fakes answer Voyage, Mistral and Cohere too. 20 of 20 provider checks pass (detection, off reasons,
  each provider end to end on the live DB, failure → full-text), and the 18 earlier checks still pass. ruff and mypy
  are at their baselines.
- **Live check:** waiting for the user's GenAI key in `backend/.env` (`EMBEDDINGS_API_KEY=AIza…`). The current `.env`
  holds only a Claude key, so `auto` is off and logs the Claude reason.

## Live result (2026-10-09, Gemini key saved for pilotsonic, used in memory only)

- **AC4 met:** on the golden set the hit rate is **11/13 (0.85) with meaning search vs 8/13 keyword-only**. Newly found:
  the parcel/tracking and shirt/size-exchange paraphrases, and the Bengali shipping question. The two
  not-in-knowledge questions retrieve exactly what they retrieved before, so they behave as today.
- **Threshold (D3):** measured for `gemini-embedding-001@768` with `run_reply_eval.py --similarities`:
  - right answers scored 0.642–0.786;
  - the best wrong match of an unanswerable question scored 0.683 (Sylhet) and 0.634 (India).
  - At 0.60 all 13 were found, but the unanswerable questions also pulled in 5 loosely related sources each.
  - The new setting **`EMBEDDINGS_MIN_SIMILARITY` defaults to 0.70**. Headphones (0.694) and PayPal (0.642) fall
    below it.
  - The value is model-specific: re-measure it for any other provider or model.
- **RAGAS reply scores:** still not measured. Gemini text generation for pilotsonic still answers HTTP 429 (quota),
  while embeddings work.
- **Checks:** 18/18 + 20/20 checks, the SPEC-BE-085 suites, ruff and mypy are all at baseline. No rows persisted.
