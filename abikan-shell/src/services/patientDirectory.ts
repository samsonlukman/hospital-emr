import type {
  PatientDirectoryPageSize,
  PatientDirectoryPayload,
  PatientLifeStatusFilter,
  PatientRecord,
} from "../types/patientDirectory";
import { PatientAccountRequestError } from "./patientAccount";

async function readJson<T>(path: string, fallback: string): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const body = (await response.json().catch(() => ({}))) as T & {
    message?: string;
    code?: string;
  };
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(body.message || fallback, response.status, body.code);
  }
  return body;
}

export function fetchPatientDirectory(input: {
  q?: string;
  limit: PatientDirectoryPageSize;
  startIndex: number;
  lifeStatus?: PatientLifeStatusFilter;
}): Promise<PatientDirectoryPayload> {
  const params = new URLSearchParams({
    limit: String(input.limit),
    startIndex: String(input.startIndex),
  });
  const query = (input.q || "").trim();
  if (query) {
    params.set("q", query);
  }
  if (input.lifeStatus && input.lifeStatus !== "all") {
    params.set("lifeStatus", input.lifeStatus);
  }
  return readJson<PatientDirectoryPayload>(
    `/openmrs/abikan-api/patients?${params.toString()}`,
    "The patient list could not be loaded.",
  );
}

export function setPatientNhis(
  patientUuid: string,
  nhis: boolean,
): Promise<{ status: string; uuid: string; nhis: boolean }> {
  return fetch(`/openmrs/abikan-api/consultation/patient/${encodeURIComponent(patientUuid)}/nhis`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ nhis }),
  }).then(async (response) => {
    const payload = (await response.json().catch(() => ({}))) as {
      status?: string;
      uuid?: string;
      nhis?: boolean;
      message?: string;
      code?: string;
    };
    if (response.status === 401) {
      throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
    }
    if (!response.ok) {
      throw new PatientAccountRequestError(
        payload.message || "NHIS could not be saved. Try again.",
        response.status,
        payload.code,
      );
    }
    return { status: payload.status || "ok", uuid: payload.uuid || patientUuid, nhis: Boolean(payload.nhis) };
  });
}

export function fetchPatientRecord(patientUuid: string): Promise<PatientRecord> {
  return readJson<PatientRecord>(
    `/openmrs/abikan-api/patients/${encodeURIComponent(patientUuid)}`,
    "This patient could not be loaded.",
  );
}

export function updatePatientLifeStatus(
  patientUuid: string,
  body: { alive: boolean; deathDate?: string; requestId: string },
): Promise<PatientRecord> {
  return fetch(`/openmrs/abikan-api/admin/patients/${encodeURIComponent(patientUuid)}/life-status`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(async (response) => {
    const payload = (await response.json().catch(() => ({}))) as PatientRecord & {
      message?: string;
      code?: string;
    };
    if (response.status === 401) {
      throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
    }
    if (response.status === 403) {
      throw new PatientAccountRequestError(
        payload.message || "This action requires Hospital Administration.",
        403,
        payload.code || "forbidden",
      );
    }
    if (!response.ok) {
      throw new PatientAccountRequestError(
        payload.message || "The patient status could not be updated.",
        response.status,
        payload.code,
      );
    }
    return payload;
  });
}
