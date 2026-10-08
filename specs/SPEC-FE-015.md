# SPEC-FE-015: Knowledge Base — Brand Settings & FAQs (Brand Voice tab)

## Purpose
Wire the Knowledge Base page's Brand Voice tab — Brand Settings form and FAQs list — to real, already-implemented backend data (SPEC-BE-012 brand settings, SPEC-BE-013 FAQs).

## Scope
In scope: the tabs row (Brand Voice/Products & Pricing/Policies/FAQs/Shipping) and the grid-2 content beneath it — the Brand Settings form (left) and FAQs list with add-FAQ (right) — matching the mockup, for the Brand Voice tab only.

Explicitly NOT being built by this spec:
- Any content for the Products & Pricing, Policies, FAQs (as a separate full-page tab), or Shipping tabs — the mockup has no markup for them beyond the FAQs list already shown on the Brand Voice tab; clicking them may toggle the active tab visual state but shows no different content yet
- FAQ editing/deletion — only list + create, per SPEC-BE-013's scope

## Contract
The real backend endpoints already implemented for brand settings (GET/PUT, SPEC-BE-012) and FAQs (GET list/POST create, SPEC-BE-013). Do not assume field names, route paths, response shapes, or which form fields the real brand_settings schema actually supports — confirm all of these from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's brand and faqs routes/schemas (and CLAUDE.md) to determine, field by field: which of the mockup's Brand Settings fields (brand name, tone slider, style slider, primary language, forbidden terms) actually exist in the real brand_settings schema and their exact field names/types/ranges — the architecture doc's own schema list (voice JSONB, palette JSONB, logo_url, forbidden_terms[], disclaimers) does not obviously include a "primary language" field, so confirm specifically whether it exists; and the exact FAQ list/create endpoint paths and request/response fields (question, answer, channel/tag applicability, and whether "All channels" is a real stored value or derived). If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render the tabs row with the 5 literal labels, "Brand Voice" active by default. Do not fabricate content for the other 4 tabs — leave the content area unchanged when a different tab is selected, with a code comment noting their real content is deferred.
3. Brand Settings form: render only the fields confirmed to exist in the real schema in Functional Rule 1, pre-filled with real current values. Any mockup field NOT actually present in the real schema (e.g. if "primary language" turns out not to exist) renders visually per the mockup but as a disabled/read-only control with a code comment stating it has no real backing field yet — do not invent a fake persistence path for it.
4. "Save Brand Settings" calls the real confirmed update endpoint with only the fields that are real, in the real expected shape (e.g. if tone/style are stored as a single voice JSONB object, construct that object correctly rather than sending flat fields the backend doesn't expect).
5. FAQs card: render the header "FAQs ({n})" with the real total count from the confirmed list endpoint, and one .kb-item per real FAQ (question bolded, "Applied to: {channels}" using the real channel/tag data — collapsing to "All channels" only if the real data actually represents full applicability, confirmed in Functional Rule 1, not assumed).
6. "+ Add FAQ" reveals a minimal inline form using exactly the fields the real create endpoint's request schema requires (question, answer, and channel/tag selection if the real schema has one) — do not add fields the real schema doesn't accept. Submitting calls the real create endpoint and adds the new FAQ to the list on success.
7. Disable Save/Add-FAQ controls while their respective calls are in flight; on failure, show the real ApiError message inline without discarding the user's unsaved input.

## Edge cases
- Zero FAQs: render "FAQs (0)" with a plain "No FAQs yet" message instead of an empty list.
- Brand settings not yet configured for this tenant (a real "not found"/empty response): render the form with empty/default values rather than erroring.
- The FAQ list or brand settings fetch fails: show an inline error in that card without blocking the other card.

## Non-functional rules
- No mock/hardcoded brand values or FAQ rows anywhere.
- Must not fabricate a working save path for a form field that isn't real — see Functional Rule 3.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. Every rendered brand-settings field that is interactive/saveable traces to a real backend field confirmed in the plan step; any field without real backing is visibly disabled with the documenting comment.
2. Saving brand settings persists correctly to the real endpoint and reloads to show the saved values.
3. The FAQs count and every FAQ's question/channel text trace to real backend data.
4. Adding an FAQ uses only real schema fields and correctly appends the new item on success.
5. Loading/empty/error states for both cards are handled distinctly and independently of each other.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real brand_settings and FAQ contracts are authoritative per Functional Rule 1, including which mockup fields actually have real backing.
- The 4 non-Brand-Voice tabs have no real content yet.

## Target files
- app/(app)/kb/page.tsx (extends SPEC-FE-002's stub)
- components/kb/brand-settings-form.tsx (new)
- components/kb/faq-list.tsx (new)
- lib/api/kb.ts (new — covers both the brand and FAQ domains for this page, mirroring the SPEC-FE-005-style aggregation approach)
- lib/types/kb.ts (new)
- app/globals.css (extends, adding .form-row, .form-grid-2, .kb-list, .kb-item, .kb-item-icon verbatim from the reference mockup; .tabs/.tab were already ported by SPEC-FE-011 — reuse, do not duplicate)
