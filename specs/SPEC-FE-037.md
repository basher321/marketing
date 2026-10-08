# SPEC-FE-037: Integrations — one page for every key (platforms + AI models)

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge on dev-shop (restored to its snapshot afterwards). The E2E never contacted a real platform: the platform save used the server-side request forgery guard path, and the AI-model "Test" call was covered by the mocked backend tests. Depends on SPEC-BE-052/053. Amends SPEC-FE-021, whose Manage/Connect buttons were inert.

Implementation note: seeded demo rows that are "connected" but have no saved credentials show "No credentials saved — click Manage to add them." instead of a sync time.

## Amendment (2026-10-02): Test checks what's on screen

Status: IMPLEMENTED (2026-10-02). Goes with SPEC-BE-053's 2026-10-02 amendment. "Save & test" appears while the key or model is unsaved, saves first, then tests. Type check passes.

**Problem.** In an AI model card, "Test" checks the **saved** model and key. A user who types a new model and clicks Test without Save gets the old model's error again, so the fix looks broken.

**Rules.**
1. When the card's model or key field differs from what's saved, Test saves first and then tests. A failed save shows its error and skips the test.
2. The button reads "Save & test" while there are unsaved changes, and "Test" otherwise.
3. Test is enabled once a key is saved or typed (today it needs a saved key).
4. The model field's placeholder and the "default" hint come from `default_model` (already in the API), so the new defaults show without a frontend change.

**Acceptance criteria (E2E, dev-shop, restored afterwards).**
1. Type `gemini-2.5-flash` over the retired model and click "Save & test". The model is saved and the result shows "Test OK — gemini-2.5-flash …".
2. With no changes, the button reads "Test" and checks the saved model.
3. A 404 shows the backend's retired-model hint.

**Target files.** components/integrations/ai-models.tsx only.

## Purpose
All keys and connections are managed in one place, `/integrations`. Nothing needs to go in `.env`.

## Functional rules
1. **Sections:** AI Models, Ads, Social, Messaging, Email, Commerce, CRM. The existing card grid look stays. Each card shows its status badge, account name, "Last verified …" or the last error.
2. **AI Models:**
   - One card per provider (Claude, GPT, Gemini, Groq): API key (password field with show/hide; empty keeps the saved key), model, and an Enabled switch.
   - "Test" shows OK and the latency, or the error.
   - Drag or ↑/↓ controls set the **fallback order**, with the note: "If the first model fails, the next one answers automatically."
   - It shows whether a `.env` fallback exists.
3. **Connect / Manage / Reconnect** opens a side panel with the catalog fields for that provider:
   - Secrets are password fields showing the masked saved value.
   - There's help text and a docs link.
   - "Save & test" shows the verification result. "Disconnect" asks for confirmation.
4. A persistent note: "Connecting verifies your credentials. Publishing ads and posts to these platforms is not active yet."
5. A 403 shows "Only managers and above can change integrations."

## Acceptance criteria (verified E2E)
Saving a (stub or invalid) token shows the backend's verification result. The DB holds only ciphertext. The AI-model order and enable state persist. A test call with an invalid key shows the provider's error. Test data is removed afterwards.

## Target files
- app/(app)/integrations/page.tsx
- components/integrations/integrations-grid.tsx, components/integrations/connect-panel.tsx (new), components/integrations/ai-models.tsx (new)
- lib/api/integrations.ts, lib/types/integrations.ts

## Amendment (2026-10-02): model pickers from the provider's live list

Status: APPROVED (2026-10-02), frontend part of the SPEC-BE-053 amendment of the same date.
- Once a key is saved, the Model field becomes a picker filled from `GET /ai-models/{provider}/models`, with a **Refresh** button. Typing any other name is still possible ("Other…" free text), for models the list doesn't show yet.
- No placeholder default. With no model chosen, the card shows "Choose a model" and pre-fills the backend's suggestion; nothing is saved until the user clicks Save or Save & test.
- OpenAI and Gemini cards get an **Image model** picker from the same list (used by Create with AI).
- A failed test with suggestions shows **Switch to X** (save + test) and the other suggestions.
- A list error (bad key, network) is shown under the picker; free text still works.
Target files: `components/integrations/ai-models.tsx`, `lib/api/integrations.ts`, `lib/types/integrations.ts`.
