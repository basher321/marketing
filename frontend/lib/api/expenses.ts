import type { Expense, ExpenseList, ExpenseSave } from "../types/expenses";
import { apiFetch } from "./client";

export const expenseKeys = {
  all: ["expenses"] as const,
  list: (from: string, to: string) => ["expenses", "list", from, to] as const,
};

/** GET /expenses?from&to (SPEC-BE-110 FR1). */
export function fetchExpenses(from: string, to: string): Promise<ExpenseList> {
  return apiFetch<ExpenseList>(`/api/v1/expenses?from=${from}&to=${to}&limit=200`);
}

/** POST /expenses (manager+). */
export function createExpense(body: ExpenseSave): Promise<Expense> {
  return apiFetch<Expense>("/api/v1/expenses", { method: "POST", body: body as unknown as Record<string, unknown> });
}

/** DELETE /expenses/{id} (manager+, soft delete). */
export function deleteExpense(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/expenses/${encodeURIComponent(id)}`, { method: "DELETE" });
}
