import type { AccommodationTariffPayload } from "../types/accommodation";
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
  if (response.status === 403) {
    throw new PatientAccountRequestError(
      body.message || "You do not have access to accommodation prices.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "The accommodation prices could not be loaded.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchAccommodationTariffs(): Promise<AccommodationTariffPayload> {
  return readJson<AccommodationTariffPayload>("/openmrs/abikan-api/inpatient/accommodation/tariffs");
}

export function saveAccommodationTariff(
  areaUuid: string,
  listPrice: number,
  requestId: string,
): Promise<AccommodationTariffPayload> {
  return readJson<AccommodationTariffPayload>("/openmrs/abikan-api/inpatient/accommodation/tariffs", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ areaUuid, listPrice, requestId }),
  });
}

export function newTariffRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `tariff-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
