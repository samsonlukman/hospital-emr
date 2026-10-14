import type { AllergyRecord, AllergyState } from "../types";
import { PatientAccountRequestError } from "./patientAccount";
import { allergyStateFromPayload, type AllergyDraft } from "../utils/allergies";

interface AllergyPayload {
  status?: string;
  canWrite?: boolean;
  allergies?: AllergyRecord[];
  message?: string;
  code?: string;
}

async function readJson(path: string, init?: RequestInit): Promise<AllergyPayload> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = (await response.json().catch(() => ({}))) as AllergyPayload;
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "The allergy could not be saved on the patient chart. Try again.",
      response.status,
      body.code,
    );
  }
  return body;
}

function allergyPath(patientUuid: string, allergyUuid?: string, suffix = ""): string {
  const base = `/openmrs/abikan-api/patient/${encodeURIComponent(patientUuid)}/allergies`;
  if (!allergyUuid) {
    return base;
  }
  return `${base}/${encodeURIComponent(allergyUuid)}${suffix}`;
}

function bodyFromDraft(draft: AllergyDraft): Record<string, string> {
  return {
    allergenType: draft.allergenType,
    allergenName: draft.allergenName.trim(),
    codedAllergenUuid: draft.codedAllergenUuid,
    severity: draft.severity,
    reaction: draft.reaction.trim(),
    comment: draft.comment.trim(),
  };
}

export async function fetchAllergyRecord(patientUuid: string): Promise<AllergyState> {
  const payload = await readJson(allergyPath(patientUuid));
  return allergyStateFromPayload(payload);
}

export async function createAllergy(
  patientUuid: string,
  draft: AllergyDraft,
): Promise<AllergyState> {
  const payload = await readJson(allergyPath(patientUuid), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bodyFromDraft(draft)),
  });
  return allergyStateFromPayload(payload);
}

export async function updateAllergy(
  patientUuid: string,
  allergyUuid: string,
  draft: AllergyDraft,
): Promise<AllergyState> {
  const payload = await readJson(allergyPath(patientUuid, allergyUuid), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bodyFromDraft(draft)),
  });
  return allergyStateFromPayload(payload);
}

export async function removeAllergy(
  patientUuid: string,
  allergyUuid: string,
): Promise<AllergyState> {
  const payload = await readJson(allergyPath(patientUuid, allergyUuid, "/void"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return allergyStateFromPayload(payload);
}
