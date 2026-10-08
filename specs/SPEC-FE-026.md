# SPEC-FE-026: E-Commerce — Orders Tab

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge against the running backend + live Postgres. Depends on SPEC-BE-041.

Implementation note: "Date" uses the viewer's browser timezone (the dev-shop tenant and browser are both Asia/Dhaka); the "Showing x–y" label is derived from the offset the displayed rows were fetched with, so it never describes a page that is still loading.

## Purpose
Fill the E-Commerce page's **Orders** tab, which is empty today (SPEC-FE-011 deferred it). The mockup defines only the tab label, so the layout follows common admin practice (Shopify/WooCommerce): a filter bar above an orders table, styled like the existing Products table (`.card`, `table`, `.badge-*`).

## Scope
In scope: a filter bar (status select + search box), an orders table, and pagination.

Not in scope: order detail view, status actions, and bulk actions. The "⋮" cell stays a static glyph, the same as in the Products table.

## Functional rules
1. **Filter bar:** a status `<select>` with "All statuses" plus the 7 live `order_status` values, and a search input for order number or customer. Search is debounced by 300 ms and trimmed. Changing a filter resets to page 1.
2. **Columns:** Order (`order_number`, bold), Date (`placed_at` in the tenant-local style used elsewhere, e.g. "Sep 30, 14:05"), Customer (`customer_name`, or muted "Guest" when null), Channel (the channel labels already used by the Products table and Customer inbox), Items (`item_count`), Total (৳ formatting identical to the Products table), Payment (`payment_method` upper-cased, e.g. "COD", plus `payment_status` when not null), Status (badge), and "⋮".
3. **Status badges:** pending → neutral, confirmed/processing → warn, shipped/delivered → success, cancelled/refunded → danger. The 7 values are the full live enum. An unknown value is shown as plain text, never with an invented badge.
4. **Pagination:** 25 per page, a "Showing 1–25 of 231" label, and Prev/Next buttons (`.btn-secondary .btn-sm`) disabled at the ends. It uses the backend's `total`, `limit` and `offset`.
5. Loading, empty ("No orders yet", or "No orders match these filters" when a filter is set) and error states follow the Products-table pattern.
6. The data comes only from `GET /api/v1/orders`, with no hardcoded rows. The TanStack Query key includes the filters and page.

## Acceptance criteria (verified E2E: backend + `next dev` + live Postgres)
1. The rows match dev-shop's orders in the DB (numbers, customers, totals, statuses), newest first.
2. The status filter and search change the rows and the "of N" total to match the DB.
3. Pagination walks through all orders with no duplicates or gaps.
4. Loading, empty and error states render. The other tabs and routes are unchanged.

## Target files
- app/(app)/ecommerce/page.tsx (render the Orders tab)
- components/ecommerce/orders-table.tsx (new)
- lib/api/orders.ts (new)
- lib/types/orders.ts (new)
