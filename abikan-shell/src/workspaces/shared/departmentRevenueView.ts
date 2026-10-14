import type { AdminPeriodId } from "../../types/administration";

export const DEPARTMENT_REVENUE_PERIODS: { id: AdminPeriodId; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "this_week", label: "This week" },
  { id: "this_month", label: "This month" },
  { id: "custom", label: "Custom range" },
];

export function revenueShareLabel(share: number | undefined): string {
  if (typeof share !== "number" || Number.isNaN(share)) {
    return "0%";
  }
  return `${Math.round(share * 1000) / 10}%`;
}

export function revenueHint(periodLabel: string, department?: string): string {
  if (department) {
    return `${department} posted invoices for ${periodLabel}.`;
  }
  return `Posted invoices for ${periodLabel}.`;
}
