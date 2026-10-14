import type {
  InpatientBoard,
  InpatientStay,
  InpatientVitalsCreateResult,
  InpatientVitalsPayload,
  MarCreateResult,
  MarOutcome,
  MarPayload,
  MedicationScheduleResult,
  NursingTreatmentQueue,
  NursingTreatmentItem,
  NursingTreatmentNote,
  NursingNoteCreateResult,
  NursingNotesPayload,
} from "../types/inpatient";
import type { VitalDraftValues } from "./openmrs/clinicalEncounter";
import { nursingNoteRequestBody } from "../utils/nursingNotes";
import { vitalsRequestBody } from "../utils/inpatientVitals";
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
      body.message || "This action requires the ward workspace.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "We couldn't complete this ward request. Please try again.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchInpatientBoard(): Promise<InpatientBoard> {
  return readJson<InpatientBoard>("/openmrs/abikan-api/inpatient/board");
}

export function fetchNursingTreatmentQueue(): Promise<NursingTreatmentQueue> {
  return readJson<NursingTreatmentQueue>("/openmrs/abikan-api/nursing/treatments");
}

export function recordNursingTreatment(
  patientUuid: string,
  item: Pick<NursingTreatmentItem, "visitUuid" | "orderUuid">,
  outcome: "given" | "held" | "not-done",
  reason = "",
): Promise<{ status: string; duplicate?: boolean }> {
  return readJson<{ status: string; duplicate?: boolean }>(
    `/openmrs/abikan-api/nursing/patient/${encodeURIComponent(patientUuid)}/treatment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        visitUuid: item.visitUuid,
        orderUuid: item.orderUuid,
        outcome,
        reason,
      }),
    },
  );
}

export function callReceptionForNursingTreatment(
  patientUuid: string,
  visitUuid: string,
): Promise<{ status: string; duplicate?: boolean }> {
  return readJson<{ status: string; duplicate?: boolean }>(
    `/openmrs/abikan-api/nursing/patient/${encodeURIComponent(patientUuid)}/treatment-call`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ visitUuid }),
    },
  );
}

export function fetchNursingTreatmentNotes(
  patientUuid: string,
  visitUuid: string,
): Promise<{ status: string; notes: NursingTreatmentNote[] }> {
  return readJson<{ status: string; notes: NursingTreatmentNote[] }>(
    `/openmrs/abikan-api/nursing/patient/${encodeURIComponent(patientUuid)}/treatment/${encodeURIComponent(visitUuid)}/notes`,
  );
}

export function createNursingTreatmentNote(
  patientUuid: string,
  visitUuid: string,
  note: string,
  requestId: string,
): Promise<{ status: string; note: NursingTreatmentNote; duplicate: boolean }> {
  return readJson<{ status: string; note: NursingTreatmentNote; duplicate: boolean }>(
    `/openmrs/abikan-api/nursing/patient/${encodeURIComponent(patientUuid)}/treatment/${encodeURIComponent(visitUuid)}/notes`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ note, requestId }),
    },
  );
}

export function fetchInpatientStay(patientUuid: string): Promise<InpatientStay> {
  return readJson<InpatientStay>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}`,
  );
}

export function fetchNursingNotes(patientUuid: string): Promise<NursingNotesPayload> {
  return readJson<NursingNotesPayload>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}/nursing-notes`,
  );
}

export function createNursingNote(
  patientUuid: string,
  note: string,
  requestId: string,
): Promise<NursingNoteCreateResult> {
  return readJson<NursingNoteCreateResult>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}/nursing-notes`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(nursingNoteRequestBody(note, requestId)),
    },
  );
}

export function fetchMar(patientUuid: string, visitUuid?: string): Promise<MarPayload> {
  const query = visitUuid
    ? `?visitUuid=${encodeURIComponent(visitUuid)}`
    : "";
  return readJson<MarPayload>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}/medication-administration${query}`,
  );
}

export function fetchVitals(patientUuid: string, visitUuid?: string): Promise<InpatientVitalsPayload> {
  const query = visitUuid
    ? `?visitUuid=${encodeURIComponent(visitUuid)}`
    : "";
  return readJson<InpatientVitalsPayload>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}/vitals${query}`,
  );
}

export function recordVitals(
  patientUuid: string,
  values: VitalDraftValues,
  requestId: string,
): Promise<InpatientVitalsCreateResult> {
  return readJson<InpatientVitalsCreateResult>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}/vitals`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(vitalsRequestBody(values, requestId)),
    },
  );
}

export function ensureMedicationSchedule(
  patientUuid: string,
): Promise<MedicationScheduleResult> {
  return readJson<MedicationScheduleResult>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}/medication-schedule`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: "{}",
    },
  );
}

export function recordScheduledDose(
  patientUuid: string,
  slotUuid: string,
  outcome: MarOutcome,
  reason: string,
  outsideWindow = false,
): Promise<MarCreateResult> {
  return readJson<MarCreateResult>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}/medication-administration`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        slotUuid,
        outcome,
        reason,
        outsideWindow,
      }),
    },
  );
}

export function requestAdmission(
  patientUuid: string,
  visitUuid: string | null | undefined,
  locationUuid: string,
): Promise<InpatientStay> {
  const body: { locationUuid: string; visitUuid?: string } = { locationUuid };
  const selectedVisit = (visitUuid || "").trim();
  if (selectedVisit) {
    body.visitUuid = selectedVisit;
  }
  return readJson<InpatientStay>(
    `/openmrs/abikan-api/inpatient/patient/${encodeURIComponent(patientUuid)}/admit-decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function assignInpatientBed(
  patientUuid: string,
  bedUuid: string,
  requestId: string,
  bedId?: number | null,
): Promise<InpatientStay> {
  return readJson<InpatientStay>("/openmrs/abikan-api/inpatient/assign", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ patientUuid, bedUuid, bedId: bedId ?? undefined, requestId }),
  });
}

export function transferInpatientBed(
  patientUuid: string,
  bedUuid: string,
  bedId?: number | null,
): Promise<InpatientStay> {
  return readJson<InpatientStay>("/openmrs/abikan-api/inpatient/transfer", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ patientUuid, bedUuid, bedId: bedId ?? undefined }),
  });
}

export function cancelWaitingAdmission(patientUuid: string): Promise<InpatientStay> {
  return readJson<InpatientStay>("/openmrs/abikan-api/inpatient/cancel-admission", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ patientUuid }),
  });
}

export function dischargeInpatient(patientUuid: string): Promise<InpatientStay> {
  return readJson<InpatientStay>("/openmrs/abikan-api/inpatient/discharge", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ patientUuid }),
  });
}

export function newInpatientRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `ward-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function newNursingNoteRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `nursing-note-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function newVitalsRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `vitals-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

