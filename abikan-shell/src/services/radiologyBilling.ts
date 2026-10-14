import type {
  RadiologyChargePayload,
  RadiologyExternalStudyPayload,
  RadiologyHistoryPayload,
  RadiologyHistoryQuery,
  RadiologyOrderCreateResult,
  RadiologyWorklistPayload,
  RadiologyWorklistRow,
} from "../types/radiologyBilling";
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
      body.message || "This action requires the Radiology workspace.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Unable to complete the radiology request.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchRadiologyWorklist(): Promise<RadiologyWorklistPayload> {
  return readJson<RadiologyWorklistPayload>("/openmrs/abikan-api/radiology/worklist");
}

export function fetchRadiologyCharge(patientUuid: string): Promise<RadiologyChargePayload> {
  return readJson<RadiologyChargePayload>(
    `/openmrs/abikan-api/radiology/patient/${encodeURIComponent(patientUuid)}`,
  );
}

export function createRadiologyCharge(
  patientUuid: string,
  requestId: string,
  orderUuid: string | undefined,
  amount: number,
): Promise<RadiologyChargePayload> {
  return readJson<RadiologyChargePayload>(
    `/openmrs/abikan-api/radiology/patient/${encodeURIComponent(patientUuid)}/charge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ requestId, orderUuid, amount }),
    },
  );
}

export function createRadiologyOrders(
  patientUuid: string,
  input: {
    visitUuid: string;
    locationUuid: string;
    encounterUuid?: string;
    requestId: string;
    services: Array<{ serviceId: string; conceptUuid?: string }>;
  },
): Promise<RadiologyOrderCreateResult> {
  return readJson<RadiologyOrderCreateResult>(
    `/openmrs/abikan-api/radiology/patient/${encodeURIComponent(patientUuid)}/orders`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function createDirectRadiologyStudy(
  patientUuid: string,
  input: {
    visitUuid: string;
    locationUuid: string;
    requestId: string;
    indication?: string;
    amount: number;
    services: Array<{ serviceId: string; conceptUuid?: string; comment?: string }>;
  },
): Promise<RadiologyOrderCreateResult> {
  return readJson<RadiologyOrderCreateResult>(
    `/openmrs/abikan-api/radiology/patient/${encodeURIComponent(patientUuid)}/direct-study`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function createExternalRadiologyStudy(input: {
  requestId: string;
  buyerName: string;
  buyerPhone?: string;
  buyerSex?: string;
  buyerDob?: string;
  buyerAddress?: string;
  indication?: string;
  requestSource?: string;
  referrer?: string;
  amount: number;
  services: Array<{ serviceId: string; conceptUuid?: string }>;
}): Promise<RadiologyExternalStudyPayload> {
  return readJson<RadiologyExternalStudyPayload>("/openmrs/abikan-api/radiology/external-study", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
}

export function fetchExternalRadiologyStudy(studyId: string): Promise<RadiologyExternalStudyPayload> {
  return readJson<RadiologyExternalStudyPayload>(
    `/openmrs/abikan-api/radiology/external-study/${encodeURIComponent(studyId)}`,
  );
}

export function saveExternalRadiologyReport(
  studyId: string,
  text: string,
): Promise<RadiologyExternalStudyPayload> {
  return readJson<RadiologyExternalStudyPayload>(
    `/openmrs/abikan-api/radiology/external-study/${encodeURIComponent(studyId)}/report`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ text }),
    },
  );
}

export function linkExternalRadiologyStudy(
  studyId: string,
  patientUuid: string,
): Promise<RadiologyExternalStudyPayload> {
  return readJson<RadiologyExternalStudyPayload>(
    `/openmrs/abikan-api/radiology/external-study/${encodeURIComponent(studyId)}/link`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ patientUuid, confirm: true }),
    },
  );
}

export function fetchLinkedExternalRadiologyStudies(
  patientUuid: string,
): Promise<{ status: "ok"; items: RadiologyWorklistRow[] }> {
  return readJson(
    `/openmrs/abikan-api/radiology/patient/${encodeURIComponent(patientUuid)}/linked-external`,
  );
}

export function fetchRadiologyHistory(
  query: RadiologyHistoryQuery = {},
): Promise<RadiologyHistoryPayload> {
  const params = new URLSearchParams();
  const entries: Array<[keyof RadiologyHistoryQuery, string | number | undefined]> = [
    ["q", query.q],
    ["from", query.from],
    ["to", query.to],
    ["requestSource", query.requestSource],
    ["patientType", query.patientType],
    ["report", query.report],
    ["category", query.category],
    ["offset", query.offset],
    ["limit", query.limit],
  ];
  for (const [key, value] of entries) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<RadiologyHistoryPayload>(`/openmrs/abikan-api/radiology/history${suffix}`);
}

export function newRadiologyRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `radiology-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
