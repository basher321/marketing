# SPEC-FE-075: E-Commerce adapts to the business type

Status: IMPLEMENTED (2026-10-22). Browser E2E: business type picker → confirm → tabs, category, product form with a server 422 shown and a successful save. Bug found and fixed in E2E: a config refresh no longer jumps back to the first tab. Backend SPEC-BE-111.

## Requirements

- `/ecommerce` reads `GET /ecommerce/config`; its tabs are the returned `tabs[]` (keys keep `?tab=` deep links
  working; an unknown or hidden tab falls back to the first).
- **Business type banner** while `confirmed: false`: shows the suggestion and its reasons ("We saw a connected
  Shopify store"), or "Tell us what you sell" when there is none, with the type picker (cards with
  descriptions). Manager+ confirms; others see "Ask a manager to choose". Settings → Store lets a manager change
  it later (with "Tabs change; no data is deleted").
- **Products tab:** "Add product" and row "Edit" open a form built from `product_fields[]` (labels, required,
  types); server 422 messages shown per field. Images from the media library picker. Archive with confirm.
- **Categories tab:** list, add, rename.
- **Customers tab:** the SPEC-FE-073 list, embedded.
- **Payments tab:** filters by payment status, "Mark paid" / "Refunded" (with reference).
- Inventory, Pricing Rules, Shipping and Orders tabs are unchanged apart from showing only when the type has them.

## Files

`app/(app)/ecommerce/page.tsx`, new `components/ecommerce/{business-type,product-form,categories,payments}.tsx`,
new `lib/api/ecommerce.ts`, `lib/api/products.ts`, `lib/types/ecommerce.ts`, `app/(app)/settings/page.tsx`.
