# SPEC-FE-011: E-Commerce — Products Table

## Purpose
Wire the E-Commerce Automation page's Products tab and table to real, already-implemented backend data (SPEC-BE-005 stock/low-stock tracking + SPEC-BE-008 product catalog).

## Scope
In scope: the tabs row (Products/Orders/Inventory/Pricing Rules/Shipping) and the Products table beneath it (SKU, Product, Price, Stock, Channel, Status columns, plus the row-actions "⋮" element), matching the mockup's markup — Products is the only tab with content, since the mockup itself defines no content for the other four.

Explicitly NOT being built by this spec:
- Any content for the Orders, Inventory, Pricing Rules, or Shipping tabs — the mockup has no markup for them; clicking them may toggle the active tab visual state but shows no different content yet
- The "⋮" row-action menu's actual menu content — no menu is defined in the mockup, so it stays non-functional
- Product creation/editing

## Contract
The real backend endpoints already implemented for product catalog listing (SPEC-BE-008) and stock/low-stock data (SPEC-BE-005). Do not assume field names, route paths, response shapes, the product status enum's exact values, the low-stock threshold/flag, or the channel list — confirm all of these from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's products/inventory routes and schemas (and CLAUDE.md) to determine: the exact endpoint(s) for the product list (one combined endpoint, or two to merge client-side — confirm which), each product's exact fields (sku, title/name, price, channels, status), the exact stock/low-stock field(s) and whatever flag or threshold marks a stock value as "low" (do not assume a hardcoded threshold like "< 10"), and the exact set of possible status enum values/labels (do not assume only Active/Out of Stock/Draft exist). If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render the tabs row with the 5 literal labels "Products", "Orders", "Inventory", "Pricing Rules", "Shipping", "Products" active by default. Clicking a different tab may toggle which one shows as active, but do not fabricate content for the other 4 — leave the content area unchanged /empty when a non-Products tab is selected, and add a code comment noting their real content is deferred to future specs.
3. Render the products table with the mockup's exact column headers (SKU, Product, Price, Stock, Channel, Status, and an empty header for the actions column), one row per real product from the confirmed endpoint(s).
4. Price formatting: literal "৳" symbol with comma-grouped thousands, matching the mockup.
5. Stock cell: render the real stock number. Apply the badge-danger treatment to the Stock cell only when the confirmed real low-stock flag/threshold (per Functional Rule 1) indicates this SKU is low-stock — do not invent your own numeric cutoff. A stock value that is not flagged low-stock (including 0, if the real data doesn't flag it as low-stock specifically) renders as a plain number with no badge, matching the mockup's own inconsistency between the "4" row (badged) and the "0" row (unbadged, since its Status column already conveys "Out of Stock" separately).
6. Channel cell: join the product's real channel list with ", ". If the confirmed real channel list for a product equals the confirmed full/complete set of channels the backend supports, render "All channels" instead of listing them individually — confirm the exact full channel set from the real backend/CLAUDE.md rather than assuming it's exactly {FB, IG, Shopify}.
7. Status cell: render a badge whose color/label maps to the real status value — badge-success for an "active"-equivalent value, badge-warn for an "out of stock"-equivalent value, badge-neutral for a "draft"-equivalent value, per the exact real enum confirmed in Functional Rule 1. If the real enum has values beyond these three, stop and report rather than inventing a badge color for an unrecognized one.
8. The "⋮" actions cell renders the literal character with no functional menu — matching the mockup's undefined interaction, same treatment as other undefined interactive elements in this series.
9. Table loading/empty/error states: a skeleton or lightweight loading indicator while fetching; a plain "No products yet" row if the real list is empty; an inline error message if the fetch fails.

## Edge cases
- A product with zero channels: render an empty Channel cell rather than erroring.
- A very long product title: no truncation logic invented; let normal table-cell wrapping/overflow behavior apply.

## Non-functional rules
- No mock/hardcoded product rows anywhere.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. Every rendered product row's fields trace to real backend data confirmed in the plan step.
2. The low-stock badge only appears where the real backend's own low-stock flag/threshold says so, not a frontend-invented cutoff.
3. "All channels" only appears when the real channel list actually equals the confirmed full channel set.
4. Status badges use only the real enum values confirmed in the plan step, with no invented badge color for an unrecognized value.
5. Loading/empty/error states render distinctly and correctly.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real product/stock contract and channel set are authoritative per Functional Rule 1.
- The Orders/Inventory/Pricing Rules/Shipping tabs have no real content yet, since the mockup itself defines none.

## Target files
- app/(app)/ecommerce/page.tsx (extends SPEC-FE-002's stub)
- components/ecommerce/products-table.tsx (new)
- lib/api/products.ts (new)
- lib/types/products.ts (new)
- app/globals.css (extends, adding .tabs, .tab, .tab.active verbatim from the reference mockup; table/th/td/badge rules were already ported by earlier specs — confirm and reuse, do not re-add duplicates)

## Amendment (2026-09-30, IMPLEMENTED)
The deferred Orders, Inventory, Pricing Rules and Shipping tab content is now covered
by SPEC-FE-026, 027, 028 and 029 respectively. The mockup still defines none of it,
so their layouts follow common e-commerce admin practice, as the user chose. Functional
rule 2's "leave the content area empty" no longer applies once those specs land.
