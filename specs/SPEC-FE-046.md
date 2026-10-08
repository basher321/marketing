# SPEC-FE-046: "Create with AI" — start, watch and approve AI-generated campaigns

Status: IMPLEMENTED (2026-10-02). It follows the user's decision to never auto-publish. Verified E2E in headless Edge on dev-shop against an isolated backend on :8010 (dev fakes, fixture LLM, scheduler off; the browser's API calls were rewritten from :8000 to :8010).
Passed:
- Ad Manager → Create with AI: the form shows "you review and publish" and has no auto-publish option; unconnected platforms are disabled.
- Start → Ready for review, with the 7-stage timeline + "Your review", Gemini-generated images rendered on 2 cards, the copy with character counts, and the safety report.
- New copy; Edit in builder opens the X draft; Publish → Published (campaign scheduled, ads created on X).
- An "AI" badge and the "AI runs" tab on Campaigns.
- AI Models › Creative: the order shows OpenAI as "not set up" and Gemini as ready; an MCP tool is saved, joins the order, Test reports the server failure, and Delete removes it.
Every test row (run, campaign, groups, ads, X connection, 18 audit rows, the empty creative settings key) was deleted afterwards. dev-shop is back to 14 campaigns, 7 integrations and 0 runs.
Not observed live: the 2-second polling, because with the scheduler off the run completes inside the Start request. With your scheduler on, Start returns at once and the page polls.
Deviations: the mode switch is two tabs on the Ad Manager; the run page adds "Publish paused" and "Start over"; the Creative order uses ↑ buttons. Backend: SPEC-BE-069/070.

## Amendment (2026-10-02): the form's options must be truthful and checked before Start

Status: IMPLEMENTED (2026-10-02), approved by the user. Scope: only `/campaigns/ai/new` and the checks behind it. Nothing else changes.

**Change log (every edit, for inspection):**

| File | What changed |
|---|---|
| `backend/app/services/ai_campaign_service.py` | **New:** `YOUTUBE_LINK` regex, `_text_ai()`, `_image_ai()`, `_products()` and `readiness()`, placed just above `create_run`. **Changed:** `create_run()` gained checks after the YouTube check: YouTube link format; text AI ready; featured products exist and are active; `products` visuals need photos; `generate` needs an image source; the end date in the future. No other function changed. |
| `backend/app/api/v1/ai_campaigns.py` | **New:** route `GET /ai-campaigns/readiness`, declared before `GET /{run_id}`. |
| `backend/app/schemas/ai_campaign.py` | **New:** models `ReadyPlatform`, `TextAI`, `ImageAI`, `ReadyProduct` and `Readiness`. **Changed:** `AICampaignCreate` gained a `prompt` validator (trimmed, at least 10 characters). |
| `frontend/lib/types/ai-campaigns.ts` | **New:** interface `Readiness`, appended at the end. |
| `frontend/lib/api/ai-campaigns.ts` | **New:** `fetchReadiness()` and the key `aiCampaignKeys.readiness`. |
| `frontend/app/(app)/campaigns/ai/new/page.tsx` | Rewritten around readiness: the "Before you start" checklist with links; examples from the company's active products and real prices; platforms disabled with their reason; products show price, real discount, "no photo" and the reason when not selectable; image options disabled with reasons; inline field checks (prompt, budget with currency, start/end, landing https, YouTube link, platforms), shown once a field is edited or after Start; Start disabled only while checklist items remain, with the reason. The default image option is now "I'll add images in the builder", the one that always works. |

No other file changed.

**How the rules decide (from real data):**
- **Text AI is ready** when one of the company's enabled AI models has no failed last call. Only when no company model is enabled does the server default count (or the dev fixture). This is exactly what the pipeline will use.
- **Image AI is ready** when an OpenAI or Gemini key is saved (that is all that can be checked without a paid image call; the source is labeled "uses your saved key"), or an MCP image tool is enabled.
- **A product is selectable** only when it is active. Its discount comes only from compare-at vs price.

**Verified (2026-10-02):**
- **Server:** 15/15 in a rolled-back transaction with real tokens. Readiness reports the missing platform and AI, the real products (20 % discount from compare-at, photos, draft not selectable) and the currency and country. The API refuses, with the stated message: no AI model; an enabled model whose last call failed (named); a draft or unknown product; product photos without photos; generate without an image source; an end date in the past; end before start; a whitespace-padded short prompt; an http landing page. A valid request reaches review, and a real 20 % claim passes the price check.
- **Real app on dev-shop (read-only; nothing submitted):** 14 checks passed:
  - the checklist names "No ad platform is connected" and both retired models (gemini-2.0-flash, llama-3.3-70b-versatile), with links to Integrations; Start is disabled with the reason;
  - the examples come from dev-shop's products in BDT, with no invented discount, and none mention kurtas;
  - Canvas Tote Bag (draft) and Baseball Cap (out of stock) are disabled with the reason, and every product shows its price and "no photo";
  - "product photos" is disabled for the photo-less Hoodie; "Generate with AI" shows Gemini images; "builder" is the default;
  - inline errors for end before start, an http landing page and a zero budget, which clear once fixed; the budget label shows BDT;
  - platforms show "Connect Meta in Integrations".
- **Note:** an example prompt names a country only when the company profile has one; dev-shop has none set, so its examples say "to shoppers" without a place.
- `tsc` passes; ruff is clean; mypy is at its baseline of 7.

**Problems found on dev-shop (2026-10-02, real app):**
1. Every platform is disabled (none has real credentials), so Start is always disabled, and the page never says why.
2. The example prompts describe kurtas at "20% off", products and a discount dev-shop doesn't have. Using one invites the AI to make claims about things that don't exist.
3. An end date before the start date is accepted by the form and only fails on the server.
4. The budget shows no currency.
5. Draft and out-of-stock products can be featured.
6. "Use the featured products' photos" can be chosen even though none of dev-shop's products has a photo, so the run would fail at the visuals step.
7. "Generate with AI" is offered without checking that an image source is set up.
8. Both saved AI models (Groq, Gemini) still use retired model names, so every run would fail at the plan step, and the form doesn't warn about it.

**Rules:**
1. **Readiness endpoint.** `GET /ai-campaigns/readiness` (any role) returns, from real data only:
   - per-platform readiness;
   - text-AI readiness (an enabled model whose last test or call didn't fail, or a working server default);
   - image-generation readiness;
   - the products, with status, price, compare-at price, real discount % and whether they have photos;
   - the brand (name, logo yes/no, forbidden words);
   - the currency.
2. **The form uses it:**
   - A **"Before you start" checklist** lists each missing item with a link to fix it (connect a platform, fix the AI model, add a product photo). Start is disabled only while an item is missing, and the reason is always shown.
   - **Example prompts** are built from the company's own active products and real prices. A discount appears only if the product's compare-at price shows one.
   - **Products:** only active products can be picked. Draft and out-of-stock products are shown greyed out with the reason. Each shows its price and real discount.
   - **Images:** "Generate with AI" is disabled with a reason when no image source is ready. "Use product photos" is disabled unless every picked product has a photo.
   - **Field checks shown inline:** prompt length (10–2000), budget > 0 (with the currency shown), end after start and in the future, landing page https, YouTube link format, 1–3 platforms.
3. **The server enforces the same rules** (`create_run`, 422 with the reason), so a manual API call can't bypass the form:
   - featured products must be active;
   - `products` visuals need photos;
   - `generate` needs a ready image source;
   - text AI must be ready;
   - the schedule end must be in the future.
4. **Prompts stay grounded:** the plan and copy prompts already receive only real product data. The new examples and checks keep the input truthful, and the existing safety review still blocks false discounts.

**Acceptance (dev-shop, real app):**
1. The checklist names the missing platform connection and the retired AI models, each with a working link.
2. The examples use dev-shop's own products, with no invented discount.
3. Draft and out-of-stock products are disabled with the reason, and product photos can't be chosen while the picked products have none.
4. End-before-start and an http landing page show inline errors.
5. With a platform connected and AI ready (verified in a rolled-back transaction with the dev fakes), Start works.
6. The API refuses each invalid case with the same message.
7. `tsc` passes, and ruff/mypy add no new errors.

**Target files:** `frontend/app/(app)/campaigns/ai/new/page.tsx`, `frontend/lib/api/ai-campaigns.ts`, `frontend/lib/types/ai-campaigns.ts`, `backend/app/services/ai_campaign_service.py`, `backend/app/api/v1/ai_campaigns.py`, `backend/app/schemas/ai_campaign.py`.

## Flow
"+ New campaign" → Ad Manager. The page gains a mode switch at the top: **Build manually** (today's cards → builder) | **Create with AI**.

**Create with AI** (`/campaigns/ai/new`):
- A large prompt box with example prompts.
- Platform chips: connected ones are preselected; unconnected ones are disabled, with a link to connect.
- Goal (optional), budget (required, tenant currency, daily/total), dates (default 7 days).
- Products to feature (catalog picker), landing page, visuals (Generate / Use product images / Upload), ads per group (1–3).
- A note: "AI prepares everything; you review and publish." There is no auto-publish option.
- **Start** → `/campaigns/ai/<run_id>`.

## Run page (`/campaigns/ai/<run_id>`)
- A live **stage timeline** (Context → Plan → Targeting → Copy → Visuals → Safety review → Draft → Publish): each stage has a status, duration and the provider used. Polled every 2 s while running.
- **needs_input:** the questions as a small form, and "Continue".
- **Ready for review:** per platform, a card for each ad with an image preview, texts with character counts, the audience summary and the budget. The safety report shows checks passed and issues.
  - Actions:
    - **Publish**: normal approval rules, and it says when owner approval will be needed. It's disabled while the safety report has errors; warnings need a tick first.
    - **Edit in builder**: opens `/campaigns/<id>/edit`.
    - **Regenerate** per ad (copy or image).
    - **Discard**.
- **failed:** the reason in plain words, plus **Retry** (from the failed stage) or **Retry publish**.
- **published / awaiting approval:** links to the campaigns and the results.

## Monitoring
- **Campaigns list:** an "AI" badge on AI-created campaigns, plus an "AI runs" tab listing recent runs (status, platforms, created by and when, cost).
- **Command Chat:** "create an AI campaign …" starts a run, and the chat links to the run page.
- **Settings › AI Models:**
  - a **Creative** section: order per kind and image providers;
  - **Creative tools (MCP)** forms.

## Acceptance criteria (E2E, headless Edge, dev-shop; fixture LLM and dev fakes; test rows removed afterwards)
1. Start a Meta and TikTok run in review mode. The timeline advances to Ready for review, with previews and safety checks.
2. Edit in builder opens the draft. Publish → published (owner), with links.
3. A needs_input question is answered and the run continues.
4. A failed run shows Retry, and Retry continues.
5. `tsc --noEmit` passes.

## Target files
- `app/(app)/campaigns/ad-manager/page.tsx` (mode switch)
- New: `app/(app)/campaigns/ai/new/page.tsx`, `app/(app)/campaigns/ai/[runId]/page.tsx`, `components/campaigns/ai/{run-timeline.tsx, ad-preview-card.tsx}`, `lib/api/ai-campaigns.ts`, `lib/types/ai-campaigns.ts`
- `app/(app)/campaigns/page.tsx` ("AI" badge + "AI runs" tab)
- `components/integrations/ai-models.tsx` (the Creative + MCP sections)
