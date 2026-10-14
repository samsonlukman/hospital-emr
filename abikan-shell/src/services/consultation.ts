import type { ConsultationChargePayload } from "../types/consultation";
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
      body.message || "This action requires the Doctor workspace.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Unable to complete the consultation request.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchConsultationCharge(
  patientUuid: string,
  visitUuid: string,
): Promise<ConsultationChargePayload> {
  const query = `?visitUuid=${encodeURIComponent(visitUuid)}`;
  return readJson<ConsultationChargePayload>(
    `/openmrs/abikan-api/consultation/patient/${encodeURIComponent(patientUuid)}${query}`,
  );
}

export function createConsultationCharge(
  patientUuid: string,
  visitUuid: string,
  requestId: string,
  amount: number,
): Promise<ConsultationChargePayload> {
  return readJson<ConsultationChargePayload>(
    `/openmrs/abikan-api/consultation/patient/${encodeURIComponent(patientUuid)}/charge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ visitUuid, requestId, amount }),
    },
  );
}


export function newConsultationRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `consult-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
