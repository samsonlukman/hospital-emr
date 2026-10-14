import type {
  HmoAssignmentsPayload,
  HmoAssignment,
  HmoBillsPayload,
  HmoMetadata,
} from "../types/hmo";
import { PatientAccountRequestError } from "./patientAccount";

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const payload = (await response.json().catch(() => ({}))) as T & {
    message?: string;
    code?: string;
  };
  if (!response.ok) {
    throw new PatientAccountRequestError(
      payload.message || "The HMO list could not be loaded.",
      response.status,
      payload.code || "hmo_error",
    );
  }
  return payload;
}

export function fetchHmoMetadata(): Promise<HmoMetadata> {
  return readJson<HmoMetadata>("/openmrs/abikan-api/hmo/metadata");
}

export function fetchHmoAssignments(query = ""): Promise<HmoAssignmentsPayload> {
  const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
  return readJson<HmoAssignmentsPayload>(`/openmrs/abikan-api/hmo/patients${suffix}`);
}

export function fetchHmoBills(input: {
  body?: string;
  scheme?: string;
  from?: string;
  to?: string;
}): Promise<HmoBillsPayload> {
  const query = new URLSearchParams();
  if (input.body) query.set("body", input.body);
  if (input.scheme) query.set("scheme", input.scheme);
  if (input.from) query.set("from", input.from);
  if (input.to) query.set("to", input.to);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return readJson<HmoBillsPayload>(`/openmrs/abikan-api/hmo/bills${suffix}`);
}

export function sendHmoStatement(input: {
  body: string;
  scheme: string;
  from: string;
  to: string;
  recipient: string;
}): Promise<HmoBillsPayload> {
  return readJson("/openmrs/abikan-api/hmo/bills/send", {
    method: "POST",
    body: JSON.stringify({
      body: input.body,
      scheme: input.scheme,
      start: input.from,
      end: input.to,
      recipient: input.recipient,
    }),
  });
}

export function assignHmoPatient(input: {
  patientUuid: string;
  scheme: string;
  body: string;
}): Promise<{ status: string; assignment: HmoAssignment }> {
  return readJson("/openmrs/abikan-api/hmo/patients", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
