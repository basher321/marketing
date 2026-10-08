Purpose
Implement FAQ listing and creation, matching exactly what the Knowledge
Base page's FAQs card shows: the FAQ count in the "FAQs (N)" heading,
each FAQ's question and the channels it applies to, and the "+ Add FAQ"
action.

Scope
The existing stub files for the faqs domain: app/models/faq.py, the
matching file under app/schemas/, app/services/faq_service.py, and
app/api/v1/faqs.py. No new files or folders. No update endpoint, no
delete endpoint, no tag management, no enabled/disabled toggle - none of
that is rendered or actionable in the HTML.

Contract
After this step: a request returns the caller's tenant's FAQs, each with
its question and applied channels, plus a count matching the number of
rows returned; a create request adds one new FAQ for the caller's tenant
from a question, an answer, and a list of channels, and it appears in the
next list call with the count incremented by one.

Functional rules
- List endpoint returns the caller's tenant's FAQs only, each with:
  question and the channels it applies to.
- Create endpoint accepts question, answer, and channels for the caller's
  tenant. Any other column the existing faq model requires (e.g. tags,
  enabled) is set to its existing model default - not accepted as input,
  since neither is shown in the HTML.
- Every query and mutation filters by tenant_id explicitly, per this
  codebase's existing service convention.
- Every create writes one entry via the existing write_audit_log()
  function in core/audit.py - do not invent a new audit mechanism.

Edge cases
- An empty or missing channels list is interpreted as applying to all
  channels, matching the HTML's "Applied to: All channels" wording -
  document this mapping as a code comment.
- Creating an FAQ with an empty question or empty answer is rejected with
  a validation error, nothing is written.
- An FAQ belonging to another tenant never appears in the list or count.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The list endpoint returns only the caller's tenant's FAQs, each with
  question and channels, and the count matches the number of rows
  returned.
- A create call adds one FAQ for the caller's tenant from question,
  answer, and channels; it appears in the next list call and the count
  increases by one.
- An empty question or answer is rejected on create, nothing is written.
- A create produces one new audit_log row.
- An FAQ belonging to a different tenant never appears in the list or
  count, verified with two tenants.
- No update, delete, or tag/enabled-management endpoint exists as a
  result of this spec.

Assumptions
app/models/faq.py, the matching schema file, faq_service.py, and
api/v1/faqs.py already exist as stub files with correct signatures (per
CLAUDE.md's "structurally stubbed" list) - this spec fills their bodies
in, it does not create them. The faqs table already exists in the
database. core/audit.write_audit_log() already exists and works as
documented in CLAUDE.md.

Target files (all existing - none added, none removed):
backend/app/models/faq.py
backend/app/schemas/faq.py
backend/app/services/faq_service.py
backend/app/api/v1/faqs.py
