import type {
  HospitalFamily,
  HospitalFamilyDetailPayload,
  HospitalFamilyListPayload,
} from "../types/hospitalFamily";
import { RegistrationRequestError } from "./registration";

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = (await response.json().catch(() => ({}))) as {
    message?: string;
    code?: string;
    families?: HospitalFamily[];
  };
  if (response.status === 401) {
    throw new RegistrationRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new RegistrationRequestError(
      body.message || "This action requires Reception access.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new RegistrationRequestError(
      body.message || "The family record could not be loaded.",
      response.status,
      body.code,
      [],
      body.families || [],
    );
  }
  return body as T;
}

export function searchHospitalFamilies(query = ""): Promise<HospitalFamilyListPayload> {
  const params = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
  return readJson(`/openmrs/abikan-api/registration/families${params}`);
}

export function fetchHospitalFamily(familyId: string): Promise<HospitalFamilyDetailPayload> {
  return readJson(`/openmrs/abikan-api/registration/families/${encodeURIComponent(familyId)}`);
}

export function fetchPatientFamily(patientUuid: string): Promise<HospitalFamilyDetailPayload> {
  return readJson(
    `/openmrs/abikan-api/registration/patient/${encodeURIComponent(patientUuid)}/family`,
  );
}

export function addFamilyMember(
  familyId: string,
  input: {
    patientUuid: string;
    relationship: string;
    confirmTransfer?: boolean;
    memberName?: string;
    memberIdentifier?: string;
  },
): Promise<HospitalFamilyDetailPayload> {
  return readJson(`/openmrs/abikan-api/registration/families/${encodeURIComponent(familyId)}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
}
