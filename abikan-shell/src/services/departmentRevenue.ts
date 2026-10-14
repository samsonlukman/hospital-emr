import type { DepartmentRevenuePayload } from "../types/departmentRevenue";
import { PatientAccountRequestError } from "./patientAccount";

export async function fetchDepartmentRevenue(query: string): Promise<DepartmentRevenuePayload> {
  const suffix = query ? `?${query}` : "";
  const response = await fetch(`/openmrs/abikan-api/department/revenue${suffix}`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const body = (await response.json().catch(() => ({}))) as DepartmentRevenuePayload & {
    message?: string;
    code?: string;
  };
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new PatientAccountRequestError(
      body.message || "This revenue view is not available for this account.",
      403,
      body.code || "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Revenue generated could not be loaded.",
      response.status,
      body.code,
    );
  }
  return body;
}
