# SPEC-BE-089: AI customer-service replies answer in the customer's language

Status: IMPLEMENTED and verified (2026-10-09), live Postgres in rolled-back transactions, with
Claude (claude-sonnet-5-5) writing the replies and Gemini embeddings for retrieval.
- AC1 pass (prompt check). AC2 pass: the Bengali question got a Bengali answer (৬০ টাকা, ২০০০ টাকা
  free shipping), the English one English. AC3 pass: Bengali hand-over with no AI call, English
  otherwise. AC4 pass both ways. AC5 pass: `language_matches 1/1`. AC6 pass: stub suite 31/31,
  ruff 1 and mypy 7 (baselines).
- RAGAS (15 cases): factual correctness 0.59 -> 0.66 (target 0.60 met); the Bengali case 0.0 -> 0.5;
  faithfulness 0.41 -> 0.47 (greetings and sign-offs count as unsupported claims).
- Banglish: the first prompt gave mixed-script replies in 2 of 3 runs (a Chinese word, Bengali
  letters inside Latin words). Adding "use only that one script" gave 5 of 5 clean replies.
- Known limit: retrieval for Bengali questions needs embeddings (SPEC-BE-087); with
  `EMBEDDINGS_PROVIDER` off, keyword search finds nothing for Bengali script and the reply is the
  (now Bengali) hand-over.
Originally DRAFT (2026-10-09). Requested by the user: "yes reply in the customer language. ofcourse
follow spec driven development".

## Context

The SPEC-BE-086 RAGAS run on 2026-10-09 (Claude drafts, Claude judges, Gemini embeddings) asked
the Bengali question "ঢাকার ভেতরে ডেলিভারি চার্জ কত?". The reply was right ("Delivery inside Dhaka
costs 60 taka…") but in English, so factual correctness for that case was 0.0.

The cause is the SPEC-BE-027 brand rule in `ai/prompts/reply_drafter.py`: the system prompt says
"Write the reply in this language: {primary_language}", the company's main language
(`brand_settings.primary_language`, default `en`), whatever the customer wrote. The fixed
hand-over replies (no grounding, moderation rejected) are English only.

The SocialAPI inbox drafts (SPEC-BE-083) reuse `reply_drafter`, so they change too.

## Requirements

- **FR1 (AI reply):** the reply is written in the language of the customer's latest message,
  in the same script (Bengali written in Latin letters gets a reply in Latin letters).
  `primary_language` is used only when the message has no clear language (only numbers, an order
  number, emoji, a single word shared by several languages).
- **FR2 (hand-over replies):** when the latest customer message is mainly Bengali script, the
  fixed hand-over replies (no grounding, and the moderation-rejected safe reply) are Bengali,
  with the same three tone bands and the brand name (or "us"/"আমাদের" without one). Other
  languages keep the English templates: they are fixed text, and only Bengali is a launch
  market.
- **FR3:** everything else in SPEC-BE-027 is unchanged: grounding, cited sources, confidence,
  moderation (the Bengali templates also pass through it), the no-grounding rule (no AI call).
- **FR4 (eval):** `reply_cases.json` cases can name `"reply_script": "bengali"`;
  `run_reply_eval.py --ragas` reports `language_ok` per case and `language_matches` in the
  summary (a Bengali case passes when most letters of the reply are Bengali script).

## Decisions

- **D1:** Detection for the templates is a script check (letters in U+0980–U+09FF vs other
  letters), not a language-detection library: no new dependency, and Bengali is the only
  non-English template set. The AI reply needs no detection: the model is told to match the
  customer.
- **D2:** The Command Chat, ad copy and organic copy keep using `primary_language`: they write
  for the company's audience, not answer one customer.

## Target files

- `backend/app/ai/prompts/reply_drafter.py` (prompt rule, Bengali templates, script check,
  the SPEC-BE-027 comment)
- `backend/evals/reply_cases.json` (`reply_script` on the Bengali case)
- `backend/evals/run_reply_eval.py` (FR4)
- `CLAUDE.md` (one line)

## Acceptance criteria

1. The system prompt tells the model to answer in the customer's language and script, with
   `primary_language` only as the fallback (unit check of `build_reply_system_prompt`).
2. On the live DB in a rolled-back transaction, with a real AI model: a Bengali question
   answered by the knowledge base gets a Bengali reply; the same question in English gets an
   English reply.
3. A Bengali question with no grounding gets the Bengali hand-over template of the brand's tone
   band, with no AI call; an English one keeps the English template.
4. The moderation-rejected safe reply follows the same language rule.
5. `run_reply_eval.py --ragas` reports `language_matches` and the Bengali case passes it.
6. `ruff check app` / `mypy app` stay at their baselines; the SPEC-BE-085 stub suite still
   passes 31/31.
