/** Business expenses (SPEC-FE-074), mirroring app/schemas/expense.py (SPEC-BE-110 FR1). */
export type ExpenseCategory = "shipping" | "operating" | "other";

export interface Expense {
  id: string;
  category: ExpenseCategory;
  amount: number;
  currency: string;
  /** YYYY-MM-DD, company day. */
  incurred_on: string;
  description: string;
  vendor: string | null;
  created_by_name: string | null;
  created_at: string;
}

export interface ExpenseList {
  total: number;
  sum: number;
  currency: string;
  items: Expense[];
}

export interface ExpenseSave {
  category: ExpenseCategory;
  amount: string;
  incurred_on: string;
  description: string;
  vendor?: string;
}
