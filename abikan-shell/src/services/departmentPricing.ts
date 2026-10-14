import type {
  DepartmentPriceHistoryPayload,
  DepartmentPricingPayload,
  PricingDepartment,
} from "../types/departmentPricing";
import { PatientAccountRequestError } from "./patientAccount";

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = (await response.json().catch(() => ({}))) as {
    message?: string;
    code?: string;
  };
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Those prices could not be loaded.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchDepartmentPrices(
  department: PricingDepartment,
  query = "",
): Promise<DepartmentPricingPayload> {
  const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
  return readJson<DepartmentPricingPayload>(`/openmrs/abikan-api/pricing/${department}${suffix}`);
}

export function fetchPriceHistory(
  department: PricingDepartment,
  itemId: string,
): Promise<DepartmentPriceHistoryPayload> {
  return readJson<DepartmentPriceHistoryPayload>(
    `/openmrs/abikan-api/pricing/${department}/${encodeURIComponent(itemId)}/history`,
  );
}

export function saveDepartmentPrice(
  department: PricingDepartment,
  itemId: string,
  price: number,
  expectedPrice?: number,
): Promise<DepartmentPricingPayload> {
  return readJson<DepartmentPricingPayload>(`/openmrs/abikan-api/pricing/${department}/${encodeURIComponent(itemId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      price,
      expectedPrice,
    }),
  });
}

export function formatPriceChangedAt(iso: string | undefined): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat("en-NG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Africa/Lagos",
  }).format(date);
}
