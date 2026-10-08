Purpose
Implement the Dashboard's "Recent Activity" timeline, matching exactly
what the HTML shows: a chronological feed of significant cross-engine
events (e.g. an AI-drafted reply awaiting approval, an ad auto-paused, a
low-stock alert, a post published) for the caller's tenant, each with a
human-readable message and a relative timestamp.

Scope
The existing stub files that already house this kind of cross-engine
event/audit feed, identified from CLAUDE.md's "structurally stubbed"
list. No new files or folders are created under any circumstance - if
CLAUDE.md shows no existing stub set for this feed, stop before writing
any code and report back exactly what CLAUDE.md does show, rather than
guessing or creating anything.

Contract
After this step: a request returns, for the caller's tenant, the most
recent significant events across engines within the last 24 hours, each
with a human-readable message and its occurred-at timestamp, most recent
first.

Functional rules
- Events are read, not synthesized speculatively - every entry returned
  must trace to an actual row already written by an existing mechanism
  in this codebase (e.g. the audit log written by
  core/audit.write_audit_log(), or another existing event-recording
  mechanism). Document exactly which existing table/mechanism is the
  source, as a code comment.
- Only "significant" events are included. Document the exact filter rule
  (e.g. specific action types) as a code comment - do not return every
  low-level mutation.
- Each returned event includes a human-readable message and its
  occurred-at timestamp. If human-readable text does not already exist
  on the source rows, generate it from a small, documented set of
  message templates keyed by action type - never fabricate specific
  details (numbers, names) that aren't in the underlying event's own
  data.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with no significant events in the last 24 hours returns an
  empty list, not an error.
- An action type with no matching message template is either excluded or
  shown with a generic fallback message - document which, as a code
  comment.
- An event belonging to another tenant never appears in another
  tenant's feed.

Non-functional rules
No new files or folders under any circumstance - if the right stub files
cannot be identified from CLAUDE.md, stop and report back instead of
creating anything. Follow the existing service pattern: plain functions,
explicit db and tenant_id parameters, no classes. Type hints on every
function. No print statements - structlog only. No test framework exists
yet, so verification is manual.

Acceptance criteria
- The endpoint returns the caller's tenant's significant events from the
  last 24 hours, most recent first, each with a human-readable message
  and timestamp.
- Every returned message is traceable to a real underlying event row -
  none is invented.
- A tenant with no events in the last 24 hours gets an empty list, no
  error.
- An event belonging to a different tenant never appears in another
  tenant's feed, verified with two tenants.
- No endpoint beyond this read-only feed exists as a result of this
  spec.

Assumptions
Which existing stub files house this feed is not assumed here - it is
identified from CLAUDE.md's "structurally stubbed" list during planning,
per Scope above.

Target files
To be identified from CLAUDE.md's "structurally stubbed" list during
planning - the existing stub files for whatever domain already houses
cross-engine event/audit logging. No new files or folders under any
circumstance.
