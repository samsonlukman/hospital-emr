import type {
  AncCardListPayload,
  AncChargePayload,
  AncEnrollResponse,
  AncPatientSummary,
  AncPregnancyResponse,
  AncPregnancyWriteBody,
  AncVisitResponse,
  AncVisitWriteBody,
} from "../types/antenatal";
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
      body.message || "You do not have access to antenatal records.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Unable to complete the antenatal request.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

function patientPath(patientUuid: string, suffix = ""): string {
  return `/openmrs/abikan-api/antenatal/patient/${encodeURIComponent(patientUuid)}${suffix}`;
}

export function fetchAncSummary(patientUuid: string): Promise<AncPatientSummary> {
  return readJson<AncPatientSummary>(patientPath(patientUuid));
}

export function fetchAncCardList(options: {
  q?: string;
  limit?: number;
  startIndex?: number;
} = {}): Promise<AncCardListPayload> {
  const params = new URLSearchParams();
  if (options.q?.trim()) {
    params.set("q", options.q.trim());
  }
  params.set("limit", String(options.limit ?? 50));
  params.set("startIndex", String(options.startIndex ?? 0));
  const query = params.toString();
  return readJson<AncCardListPayload>(`/openmrs/abikan-api/antenatal/cards?${query}`);
}

/** Register the patient for Antenatal Care (creates pregnancy card). One-time fee is separate. */
export function enrollAncPatient(
  patientUuid: string,
  body: AncPregnancyWriteBody = {},
): Promise<AncEnrollResponse> {
  return readJson<AncEnrollResponse>(patientPath(patientUuid, "/enroll"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function createAncPregnancy(
  patientUuid: string,
  body: AncPregnancyWriteBody = {},
): Promise<AncPregnancyResponse> {
  return readJson<AncPregnancyResponse>(patientPath(patientUuid, "/pregnancy"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function updateAncPregnancy(
  patientUuid: string,
  pregnancyId: string,
  body: AncPregnancyWriteBody,
): Promise<AncPregnancyResponse> {
  return readJson<AncPregnancyResponse>(
    patientPath(patientUuid, `/pregnancy/${encodeURIComponent(pregnancyId)}`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function recordAncVisit(
  patientUuid: string,
  body: AncVisitWriteBody,
): Promise<AncVisitResponse> {
  return readJson<AncVisitResponse>(patientPath(patientUuid, "/visits"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchAncCharge(
  patientUuid: string,
  pregnancyId: string,
): Promise<AncChargePayload> {
  const query = `?pregnancyId=${encodeURIComponent(pregnancyId)}`;
  return readJson<AncChargePayload>(patientPath(patientUuid, `/charge${query}`));
}

export function createAncCharge(
  patientUuid: string,
  pregnancyId: string,
  requestId: string,
  amount: number,
): Promise<AncChargePayload> {
  return readJson<AncChargePayload>(patientPath(patientUuid, "/charge"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ pregnancyId, requestId, amount }),
  });
}

export function newAncRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `anc-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
