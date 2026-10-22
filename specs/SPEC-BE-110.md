# SPEC-BE-110: Expenses and profit & loss from real records

Status: IMPLEMENTED (2026-10-22). 44/44 rolled-back checks with BE-109. Live SQA (2026-10-22) found the company reset (SPEC-BE-051) didn't delete `expenses`, `sms_messages` or `order_status_events`; `tenant_service.RESET_TABLES` now does (4/4 rolled-back checks) (hand-calculated P&L matches). Deviation: FR4's `?range` on /analytics/sales was not added (the Sales tab keeps its fixed 7-day view; ranges are on the P&L tab); `by_status` and rule 1 revenue are in. UI in SPEC-FE-074.

## The problem

Analytics shows sales, ads, engagement and customer service (SPEC-BE-050), but there are no expenses and
nothing computes profit or loss. `products.cost_cents` / `product_variants.cost_cents` exist but are unused.

## Accounting rules (one place: `analytics_service.PL_RULES`, also returned by the API as text)

1. **Which orders are sales:** placed in the period (`placed_at`, the company's timezone) with status
   `confirmed`, `processing`, `shipped` or `delivered`. Pending / awaiting confirmation (not yet a sale),
   cancelled, returned and refunded orders are **not** sales; their count and value are shown separately.
2. **Sales revenue** = Σ (subtotal − discount). **Shipping charged** to customers is a separate revenue line.
   **Tax is excluded** (collected for the government). Net revenue = sales revenue + shipping charged.
3. **Product cost (COGS)** = Σ quantity × the cost snapshot on the order item (SPEC-BE-107), else the current
   variant cost, else the product cost, for the same orders as rule 1. A line with no cost anywhere is
   **missing**, never 0: the response lists how many lines and how much revenue have no cost, and marks the
   result `complete: false`.
4. **Ad spend** = `analytics_events` metric `spend_cents` for every source in `AD_RESULT_SOURCES`, by
   `event_time` in the period. Rows in another currency than the company's are left out (no FX conversion)
   and listed. Zernio campaigns are read live and not imported, so their spend is reported as
   **unavailable**, not 0.
5. **Other costs** = `expenses` by `incurred_on`, by category: `shipping` (courier costs you pay),
   `operating`, `other`. A cost recorded as an expense must not also be a product cost; the expense form
   offers no "product cost" category for that reason.
6. **Profit or loss** = net revenue − product cost − ad spend − shipping expenses − operating − other.
   Margin = profit ÷ net revenue (null when revenue is 0).
7. Money stays integer cents in the company currency; the API returns major units via `Decimal` and
   `format_money` for text.

## Additive DDL

```sql
CREATE TABLE expenses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  category text NOT NULL CHECK (category IN ('shipping','operating','other')),
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  currency char(3) NOT NULL,
  incurred_on date NOT NULL,
  description text NOT NULL,
  vendor text,
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);
CREATE INDEX expenses_tenant_day_idx ON expenses (tenant_id, incurred_on) WHERE deleted_at IS NULL;
```

## Requirements

- **FR1 Expenses.** `GET /expenses?from&to&category` (paged), `POST /expenses`, `PATCH /expenses/{id}`,
  `DELETE /expenses/{id}` (soft). Writes manager+, audited. Currency is the company's (a different one → 422).
  `incurred_on` can't be in the future.
- **FR2 `GET /analytics/profit-loss`** `?range=7d|30d|90d|mtd|ytd` or `?from=YYYY-MM-DD&to=YYYY-MM-DD`
  (≤ 366 days) → `{currency, period {from, to}, previous_period, revenue {sales, shipping_charged, net,
  order_count}, not_sales {pending, cancelled, returned, refunded: {count, value}}, costs {product,
  ad_spend {total, by_platform[], unavailable[], excluded_currency[]}, shipping, operating, other, total},
  profit, margin, complete, missing_cost {lines, revenue}, previous {net_revenue, costs_total, profit},
  delta_pct {revenue, profit}, by_day[] {date, net_revenue, costs, profit}, by_product[] {sku, title,
  units, revenue, cost|null}, rules[]}`. The previous period is the same length just before. Days are
  zero-filled; a day with no orders is 0 revenue (a real zero), while missing costs stay null.
- **FR3 `GET /analytics/profit-loss.csv`** → the same period as CSV (summary block, then by day, then by
  product), `Content-Disposition: attachment`.
- **FR4 Sales tab.** `GET /analytics/sales` gains `?range` and a `by_status` breakdown, using rule 1 for the
  revenue figure. Its existing fields keep their names.

## Acceptance criteria (live DB, rolled back)

1. Seed: 3 delivered orders, 1 cancelled, 1 pending, 1 returned; costs on 2 of 3 lines; 2 expenses; ad spend
   on 2 platforms. The numbers match a hand calculation, `complete` is false, missing_cost names 1 line.
2. Tax never appears in revenue; shipping charged is its own line.
3. A day with no orders is 0; ad spend in another currency is excluded and listed.
4. The CSV matches the JSON; another company's data never appears.

## Files

New: `models/expense.py`, `schemas/expense.py`, `services/expense_service.py`, `api/v1/expenses.py`
(registered in `api/router.py`). Changed: `services/analytics_service.py`, `schemas/analytics.py`,
`api/v1/analytics.py`.
