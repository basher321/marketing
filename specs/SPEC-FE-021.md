# SPEC-FE-021: Integrations — Connection Status Grid

## Purpose
Wire the Integrations page's grid of provider cards to real, already-implemented backend connection-status data (SPEC-BE-017).

## Scope
In scope: the integrations-grid of provider cards — name, status badge, a generic real-data-driven subtitle, and a status-appropriate button (present but non-functional, per the gap noted below).

Explicitly NOT being built by this spec, and not backed by any real endpoint today:
- Real OAuth connect/reconnect/disconnect flows — no backend spec has ever built this (it was identified as needed backend work before the switch to frontend, and nothing has implemented it since). "Manage"/"Connect"/"Reconnect" render present but non-functional.
- Any per-provider richer stat ("2,431 products synced", "Tier 2 · 10k msgs/day") as if it were live tenant data — the real integrations schema (per the architecture doc: provider, credentials_ref, scopes[], connected_at, expires_at, last_sync_at) has no evident field for this. These become static provider-catalog copy instead (see Functional Rule 3).

## Contract
The real backend endpoint already implemented for integration connection status (SPEC-BE-017). Do not assume field names, route paths, or response shape — confirm from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's integrations routes/schemas (and CLAUDE.md) to determine: the exact list endpoint path and response shape (provider identifier, connection status/boolean, last_sync_at, and whether any error/reason field like "token expired" exists). If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render one .integration-card per real returned provider (do not hardcode the 9 providers the mockup happens to show — render however many the real endpoint returns, in whatever order it returns them).
3. Provider display name and a short static descriptive line (what connecting this provider offers, e.g. "Sync customer records") come from a small frontend-only provider-catalog lookup keyed by the real provider identifier — this is generic marketing/descriptive copy about the provider, not tenant data, so it is acceptable to hold statically in the frontend. If the real response includes a provider identifier this lookup doesn't recognize, render the raw identifier as the name and omit the descriptive line rather than guessing one.
4. Status badge: badge-success "Connected" if the real data marks it connected; badge-warn "Reconnect" if the real data marks it needing reconnect (e.g. an expired-token flag); badge-neutral "Not Connected" otherwise. Do not invent a status value beyond what the real enum/boolean(s) support — if the real data has more states than these three, stop and report.
5. Subtitle line: if connected and a real last_sync_at exists, render "Last synced: {relative time}" computed client-side from that real timestamp. If needing reconnect and the real data has an explicit reason (e.g. token expired), render that real reason text; otherwise render the static descriptive line from Functional Rule 3. If not connected, render the static descriptive line from Functional Rule 3.
6. Buttons ("Manage" for connected, "Reconnect" for needs-reconnect, "Connect" for not-connected) render with their exact mockup labels but are non-functional — add a code comment noting real OAuth connect/reconnect is deferred pending a backend spec that doesn't exist yet.

## Edge cases
- Zero integrations configured: render an empty grid with a plain "No integrations configured" message.
- The list fetch fails: show an inline error rather than a blank page.
- A provider recognized by the catalog but with no last_sync_at despite being marked connected: fall back to the static descriptive line rather than a blank/error subtitle.

## Non-functional rules
- No mock/hardcoded connection status anywhere — only the provider-catalog display name/description is static, and it is descriptive copy, not status data.
- Do not implement any real connect/reconnect/manage flow.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. The grid renders exactly the providers the real endpoint returns, not a hardcoded list.
2. Every status badge and last-synced time traces to real backend data.
3. Descriptive subtitle copy for non-connected/no-timestamp cases comes only from the static provider catalog, clearly separated in code from real status data.
4. All three action buttons are present but visibly non-functional, with the documenting comment.
5. Zero-integrations and fetch-error states render distinctly.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real integrations-status contract is authoritative per Functional Rule 1.
- Real OAuth connect/reconnect is confirmed-absent from the backend and deferred.

## Target files
- app/(app)/integrations/page.tsx (extends SPEC-FE-002's stub)
- components/integrations/integrations-grid.tsx (new)
- lib/api/integrations.ts (new)
- lib/types/integrations.ts (new)
- app/globals.css (extends, adding .integrations-grid, .integration-card, .integration-header, .integration-name, .integration-status verbatim from the reference mockup)
