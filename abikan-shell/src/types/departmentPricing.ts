import type { PatientAccountMoney as Money } from "./patientAccount";

export type PricingDepartment = "reception" | "laboratory" | "pharmacy";

export interface PriceChange {
  occurredAt: string;
  department: PricingDepartment;
  itemId: string;
  itemLabel: string;
  oldPrice: Money;
  newPrice: Money;
  changedBy: string;
  username: string;
  reason: string;
}

export interface DepartmentPriceItem {
  id: string;
  name: string;
  kind: string;
  mapping?: string;
  specimen?: string;
  type?: string;
  strength?: string;
  form?: string;
  editable: boolean;
  note?: string;
  price: Money | null;
  lastChange?: PriceChange | null;
}

export interface DepartmentPricingPayload {
  status: "ok" | "error";
  department: PricingDepartment;
  currency: { code: string; symbol: string; decimalPlaces: number };
  canWrite: boolean;
  message?: string;
  items: DepartmentPriceItem[];
}

export interface DepartmentPriceHistoryPayload {
  status: "ok" | "error";
  department: PricingDepartment;
  itemId: string;
  history: PriceChange[];
}
