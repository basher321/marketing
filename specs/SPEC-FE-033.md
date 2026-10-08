# SPEC-FE-033: Knowledge Base — Products & Pricing, Policies, FAQs, Shipping tabs

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge on dev-shop (test policies, FAQ and audit rows removed afterwards). Depends on SPEC-BE-048. Amends SPEC-FE-015, whose "only Brand Voice has content" rule no longer applies. Brand Voice itself is unchanged.

## Purpose
Make every KB tab useful: one place to see and edit what the AI knows about the business.

## Functional rules
1. **Products & Pricing:**
   - A read view of what the AI quotes: product, SKU, price, stock status and channels (existing `GET /products`).
   - The pricing rules that are currently active (existing `GET /pricing/rules`).
   - Each section has a "Manage in E-Commerce →" link. Nothing is duplicated or edited here.
2. **Policies:**
   - Cards grouped by type (Returns, Refunds, Warranty, Shipping, Payment, Privacy, Terms, Other), each with its title, first lines, an Enabled badge and the effective dates.
   - "+ New policy" opens an inline form (type, title, body, effective from/until, enabled). Each card has Edit, Disable/Enable and Delete (Delete asks for confirmation).
   - A hint says "Enabled policies are used by the AI when drafting replies."
3. **FAQs:**
   - Searchable list (question and answer), showing channels ("All channels" when empty) and an Enabled toggle.
   - Add (existing form), Edit inline, and Delete with confirmation.
4. **Shipping:**
   - The delivery zones and rates the AI can quote (existing `GET /shipping/zones`, read view) with a "Manage in E-Commerce → Shipping" link.
   - The shipping/delivery policy text (the `shipping` policy type, editable here).
5. **Standard states:** every tab has loading, empty (with a call to action) and error states. A 403 shows "Only managers and above can edit the knowledge base."

## Acceptance criteria (verified E2E)
Each tab shows DB-true data. Creating, editing, disabling and deleting a policy and an FAQ persists in the DB. Test rows are removed afterwards.

## Target files
- app/(app)/kb/page.tsx
- components/kb/kb-tabs.tsx (new: Products & Pricing and Shipping read views), components/kb/policies.tsx (new), components/kb/faq-list.tsx (extended: edit, delete, toggle, search, full-width variant)
- lib/api/kb.ts, lib/types/kb.ts
