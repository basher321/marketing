# SPEC-FE-016: Campaign Wizard — Creative Variants Step

## Purpose
Wire the Campaign Wizard's "Creative" step — the only step the reference mockup actually renders — to the real, already-implemented content-generation and variant-selection endpoints (SPEC-BE-029/030), while being explicit that the rest of the wizard has no backend to build against yet.

## Scope
In scope: the step progress bar (rendered statically at step 3 of 6, matching the mockup, since no real multi-step wizard state exists to drive it dynamically) and the "AI-Generated Creative Variants" card — generating variants, displaying them, and selecting one.

Explicitly NOT being built by this spec, and not backed by any real endpoint today:
- Steps 1, 2, 4, 5, and 6 of the wizard (Objective, Audience, Budget & Duration, Channels, Review/Launch) — the mockup itself has no markup for them
- Real campaign creation, launch, pause, or an "Active Campaigns" list to attach this creative to — SPEC-BE-009 explicitly excluded a create/launch campaign endpoint, and nothing since has added one
- "← Back" and "Continue to Budget →" — rendered present but non-functional, since there is no real prior/next step to navigate to

## Contract
The real backend endpoints already implemented for content generation and variant selection (SPEC-BE-029/030, content_assets domain). Do not assume the generate endpoint's required input, the response shape, or the select endpoint — confirm all of these from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's content routes/schemas (app/api/v1/content.py) and CLAUDE.md to determine: the exact generate-creative endpoint's path and required request input (e.g. a brief/prompt string, channel, template reference — whatever it actually requires), the exact response shape (how many variants, each variant's headline/body/image-treatment fields, moderation_status per variant), and the exact select-variant endpoint (path, request shape). If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render the progress bar as 6 equal segments, the first 3 filled (accent color) and the last 3 unfilled (border color), matching the mockup exactly — this is static per Scope, not driven by real wizard state.
3. Provide a way to trigger generation (the mockup shows variants already present, but a real flow needs an explicit trigger since no campaign draft/brief already exists server-side) — add a minimal "Generate Variants" control that collects only the input the real endpoint actually requires per Functional Rule 1, and calls it.
4. Render each returned variant using the mockup's card treatment (a colored placeholder block standing in for real generated imagery if the real response doesn't include an image, a headline, a body line, and a Select/Selected button) — do not fabricate an image if the real response doesn't provide one; render the colored placeholder block in that case and note this in a code comment.
5. If the real response includes a moderation_status per variant and a variant is not in an approved state, do not render it as selectable — show its moderation state instead (do not silently hide it, and do not let the user select a rejected/pending variant).
6. Selecting a variant calls the real confirmed select endpoint. On success, the selected variant's button shows "✓ Selected" (matching the mockup) and the others show "Select" (unselected), reflecting the real persisted selection — not just local UI state that could desync from the backend.
7. "← Back" and "Continue to Budget →" render present, matching the mockup's exact labels, but are non-functional — add a code comment stating the rest of the wizard has no backend to advance to or from yet.

## Edge cases
- Generation returns zero variants or fails: show an inline error/empty state rather than a blank card.
- Re-triggering generation after a selection already exists: show the new set of variants with no pre-existing selection, per whatever the real endpoint's actual behavior is on a repeat call (confirm this doesn't error unexpectedly).

## Non-functional rules
- No mock/hardcoded variant content anywhere.
- Do not build any other wizard step or a working Back/Continue flow.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. Generating variants calls the real confirmed endpoint with only the input it actually requires, and every rendered variant field traces to the real response.
2. A moderation-rejected/pending variant (if the real data ever returns one) is never selectable and its state is visibly different from an approved one.
3. Selecting a variant persists via the real confirmed endpoint, and the "✓ Selected"/"Select" states reflect real persisted state, not just local UI toggling.
4. The progress bar renders as a static 3-of-6, and Back/Continue are visibly present but do nothing, with the documenting comment.
5. No campaign-creation, campaign-list, or other-wizard-step functionality was fabricated.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real content-generation/selection contract is authoritative per Functional Rule 1.
- The rest of the Campaign Wizard (steps 1/2/4/5/6, and real campaign create/launch) is confirmed-absent in the current backend per SPEC-BE-009's documented exclusions, and is deferred pending new backend work.

## Target files
- app/(app)/campaigns/page.tsx (extends SPEC-FE-002's stub)
- components/campaigns/creative-variants.tsx (new)
- lib/api/content.ts (new)
- lib/types/content.ts (new)

## Amendment (2026-09-30)
Replaced by SPEC-FE-030 (all 6 wizard steps, working Back/Continue, drafts) and
SPEC-FE-031 (the creative step: write your own, edit, AI generation linked to the
draft). This spec's "only step 3, static 3-of-6 bar, Back/Continue inert" rules no
longer apply. The creative card markup, gradients and "✓ Selected"/"Select"
behavior are kept.
