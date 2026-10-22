# SPEC-BE-114: Command Chat actions for orders, profit and unanswered customers

Status: IMPLEMENTED (2026-10-22). Command Chat golden set 38/38 in stub mode (6 new cases); 13/13 live-DB executor checks, rolled back. Approved change steps run with the requester's role (an agent's approved cancel of a confirmed order still fails with SPEC-BE-107's manager rule). Depends on SPEC-BE-107/108/110/112.

## Requirements

New actions in `ai/command_actions.py`, with the existing strict params, approval policy (SPEC-BE-059) and guard
(SPEC-BE-085):

| Action | Risk | Params | Does |
|---|---|---|---|
| `inspect_orders` (changed) | read | status += awaiting_confirmation, returned; `confirmation` filter | as before |
| `orders_awaiting_confirmation` | read | `older_than_hours?` | lists waiting orders with SMS status and age |
| `update_order_status` | change | `order` (number), `to`, `reason?`, `tracking_number?` | SPEC-BE-107 FR5 (manager+ approval) |
| `send_order_confirmation` | change | `order` | SPEC-BE-108 FR4 (sends an SMS, so a change step) |
| `profit_and_loss` | read | `range` (7d/30d/90d/mtd/ytd) or `from`/`to` | SPEC-BE-110 summary with the `complete` flag and missing items named |
| `inspect_conversations` | read | `unreplied: bool`, `channel?`, `since?` | SPEC-BE-112 list; "unreplied" = last message inbound |

- Dates and numbers go through the guard's provenance check (order numbers must appear in the message or
  context).
- The planner context gets `order_statuses` and whether SMS is `ready`.
- Golden cases added to `evals/command_chat_cases.json`: "find orders awaiting confirmation", "show sales and
  profit for this month", "which customers haven't had a reply", "mark order 1003 as shipped" (change →
  approval), "cancel order 1004" (no reason → question).
- Credentials are never in context or results (unchanged rule).

## Acceptance criteria

1. The stub eval passes all old and new cases.
2. A live DB check (rolled back): each read action returns the right rows; `update_order_status` by an agent
   waits for approval and applies on approval; an invalid change fails the step with SPEC-BE-107's message
   and a fix hint.

## Files

`ai/command_actions.py`, `ai/prompts/intent_parser.py` (context lines), `evals/command_chat_cases.json`.
