# SPEC-BE-035: System Health Check (backend↔database connectivity + required configuration verification)

## Purpose
Provide one operator-run check that confirms, with no frontend involved: (a) the backend process can read every required configuration value/API key it needs to start and operate; (b) the backend can open a real connection to PostgreSQL; (c) for every domain already implemented by SPEC-BE-005 through SPEC-BE-034, at least one already-existing read function actually round-trips through the real database (call it → it queries Postgres → it returns real data or a real empty result) rather than returning anything mocked or in-memory. This is the final verification pass before frontend work begins.

## Scope
This is not a UI-facing feature — it has no corresponding element in the HTML mockup and is explicitly exempt from the "must match the HTML" rule that governs every other spec in this series, because it is an internal verification tool, not a rendered product feature.

In scope:
- Reporting presence/absence of every required config key declared in SPEC-BE-002's env template / SPEC-BE-003's config module.
- Reporting whether a live PostgreSQL connection can be opened.
- For each domain already implemented (products/inventory, orders, conversations, campaigns, scheduled_posts, ads, brand, faqs, workflows, analytics, integrations, approvals, orchestrator, content, and the shared ai/ modules where they expose a non-generation utility), calling exactly one already-existing read-only function and recording whether it executed without exception and returned a well-formed result for a supplied tenant_id.
- Producing one consolidated structured report.

Out of scope:
- Any frontend/browser/HTML check.
- Verifying that real third-party integration credentials (Facebook/TikTok/WhatsApp/etc.) actually work — SPEC-BE-017 only reports stored connection-status rows; live third-party credential verification is deferred to the not-yet-written OAuth integration spec(s).
- Any new business functionality or new domain.
- Testing write paths — see Functional Rule 5.

## Contract
Implement this as a manual operator command (script/CLI task) unless CLAUDE.md already stubs an internal/admin-only health-check route, in which case use that route instead of inventing a new one. Either way, this check is never called by the frontend, is never part of any public or tenant-facing API surface, and (if implemented as a route) must be gated to an owner/admin-only permission and never listed as a general API endpoint.

Input: a tenant_id supplied by the operator invoking the check (parameterized — never hardcoded).
Output: one structured report object:
{"config": {"<key>": "present"|"missing"}, "database": {"connected": bool, "error": string|null}, "domains": {"<domain_name>": {"status": "ok"|"failed"|"skipped", "detail": string}}}

## Functional rules
1. Read every required key from the app's settings/config module (SPEC-BE-003). For each, report "present" or "missing" — a present-but-empty-string value counts as "missing". Never log or return the actual secret value, only the key name and its presence.
2. Attempt one real database connection using the existing DB session/engine setup. Report "connected": true/false and, on failure, the real underlying error message (do not swallow the exception).
3. For every domain listed under Scope, call exactly one already-existing, already-implemented read-only function from that domain's real service module (the same function an existing endpoint already calls), passing the supplied tenant_id. Do not write a new query or a new function to perform this check — reuse what SPEC-BE-005 through SPEC-BE-034 already built.
4. Do not iterate over all tenants automatically. One invocation checks one supplied tenant_id, consistent with the tenant-scoping pattern used everywhere else in this codebase.
5. Do not write any new row to any table as part of this check. If verifying a domain would require a write (there is no read-only function to call), report that domain as "skipped: no read-only function available" rather than inventing a write-based check. Add a code comment explaining that write-path verification is intentionally out of scope because it would either pollute real tenant data or require throwaway-tenant infrastructure that does not exist yet.
6. Where an existing function needs a specific row id (e.g., a conversation_id) and no list function can safely supply one for this tenant, call the corresponding list function instead and mark the check "skipped: no seed row available for detail check" rather than fabricating an id.
7. Wrap every individual domain check so that one domain's failure (exception) is caught, recorded as "failed" with the real error message in "detail", and does not stop the remaining checks from running.
8. This check itself must never raise an unhandled exception to its caller.

## Edge cases
- A domain listed under Scope has no corresponding service module yet, or CLAUDE.md shows it still stubbed/empty: report "skipped: not yet implemented", do not fail the whole run.
- Database unreachable: the config section still completes (it doesn't need the DB); every domain check reports "failed: database unreachable".
- Tenant has zero rows in a given table: the domain's function returning an empty list/result is "ok" — only an exception counts as "failed".
- Config key present with an empty string: treated as "missing", not "present".

## Non-functional rules
- structlog only; log the full report at info level, or at error level if anything is "missing"/"failed".
- No new files or folders beyond what CLAUDE.md already stubs for this purpose. If no suitable existing file is found for the check itself, stop and report which file you'd need to add and why, and wait for confirmation, rather than creating one unapproved.
- Never log or return a raw secret/credential value anywhere in this feature's output.
- This code path must never be reachable from any tenant-facing or public route.

## Acceptance criteria
1. With a fully-configured environment and a live database, running the check against a real tenant_id reports "present" for every required config key, "connected": true, and "ok" for every already-implemented domain (or "skipped" with an honest reason where Functional Rules 3–6 apply).
2. Unsetting one required env var causes only that key to report "missing"; every other section completes normally.
3. Pointing the DB connection at an unreachable host causes "connected": false with a real error message, and every domain reports "failed: database unreachable" instead of crashing the process.
4. No new row exists in any table as a result of running this check (verify manually by comparing row counts/checksums before and after).
5. Nothing in the report or logs contains a raw secret value.
6. Running the check twice in a row against the same tenant produces identical domain statuses.

## Assumptions
- CLAUDE.md is canonical for the exact list of required config keys/API keys (from SPEC-BE-002/003) and for whether a stub already exists for this kind of system-wide check; if none exists, propose the single most appropriate existing infra file to extend and report back for approval rather than creating a new file outright, unless CLAUDE.md's own conventions already designate a location (e.g. an existing scripts/ folder) for operator tooling.
- "Necessary API keys" means credentials our own backend needs to start and operate (DB URL, JWT signing secret, LLM provider key(s), and any other secret declared in SPEC-BE-002's template) — not third-party OAuth tokens stored in the integrations table, which are data, not startup config.
- Real third-party platform connectivity (Meta/TikTok/WhatsApp/etc.) is intentionally not verified here; that is deferred to the OAuth integration spec(s) not yet written.

## Target files
To be identified from CLAUDE.md per the Assumptions above — expected to be the existing config module (SPEC-BE-003) plus the app entrypoint/startup file, and at most one additional existing infra/ops file if CLAUDE.md already stubs one for this purpose. If fewer than that exists, stop and report before writing any code rather than creating new files unapproved.
