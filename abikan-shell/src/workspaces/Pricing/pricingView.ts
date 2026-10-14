import type { DepartmentPriceItem } from "../../types/departmentPricing";

export function matchesPriceSearch(row: DepartmentPriceItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return [row.name, row.mapping, row.specimen, row.type, row.strength, row.form]
    .join(" ")
    .toLowerCase()
    .includes(needle);
}

export function catalogueHint(row: DepartmentPriceItem): string {
  return [row.specimen, row.type, row.strength, row.form].filter(Boolean).join(" · ");
}

export function parsePriceDraft(raw: string): number | null {
  const cleaned = raw.replace(/[₦,\s]/g, "").replace(/NGN/gi, "").trim();
  if (!cleaned) {
    return null;
  }
  const amount = Number(cleaned);
  if (!Number.isFinite(amount) || amount < 0) {
    return null;
  }
  return Math.round(amount * 100) / 100;
}

export function priceDraftError(raw: string): string {
  return parsePriceDraft(raw) === null ? "Enter a price of zero or more." : "";
}
