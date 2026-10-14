import {
  CONSULTATION_ENCOUNTER_TYPE,
  OPD_VISIT_TYPE_NAME,
  OPD_VISIT_TYPE_UUID,
  VITAL_CONCEPTS,
  type VitalConceptKey,
} from "../../config/clinicalConcepts";
import type { DiagnosisDraftItem, DiagnosisRecord } from "../../types";
import { OpenmrsRequestError, openmrsGet, openmrsPost } from "./client";
import type { BahmniDrugOrderPayload } from "./drugOrders";
import { parseOpenmrsDateTime } from "../../utils/datetime";
import { VISIT_NOT_STARTED_MESSAGE, visitHasStarted } from "./visitWindow";

export const DIAGNOSIS_SEARCH_URL = "/openmrs/ws/rest/v1/bahmni/terminologies/concepts";
export const DIAGNOSIS_READ_URL = "/openmrs/ws/rest/v1/bahmnicore/diagnosis/search";
export const DIAGNOSIS_SEARCH_LIMIT = 20;

export const BAHMNI_ENCOUNTER_URL = "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter";
export const EMRAPI_CONDITION_URL = "/openmrs/ws/rest/emrapi/condition";

export interface EncounterObservation {
  uuid?: string;
  concept: {
    uuid: string;
    name: string;
    dataType: string;
  };
  value?: number | string;
  voided?: boolean;
  orderUuid?: string;
  groupMembers?: EncounterObservation[];
}

export interface BahmniDiagnosisPayload {
  codedAnswer?: { uuid?: string };
  freeTextAnswer?: string;
  order: "PRIMARY" | "SECONDARY";
  certainty?: string;
  existingObs?: string | null;
  diagnosisDateTime?: string | null;
  diagnosisStatusConcept?: unknown;
  voided?: boolean;
  comments?: string;
}

export interface BahmniOrderPayload {
  concept: { name: string; uuid: string };
  commentToFulfiller?: string;
  urgency?: "STAT";
  uuid?: string;
}

export interface ConsultationSaveInput {
  patientUuid: string;
  visitUuid: string;
  visitType?: string;
  visitStartDatetime?: string;
  locationUuid: string;
  providerUuid: string;
  encounterUuid?: string;
  encounterDateTime?: string;
  observations?: EncounterObservation[];
  bahmniDiagnoses?: BahmniDiagnosisPayload[];
  orders?: BahmniOrderPayload[];
  drugOrders?: BahmniDrugOrderPayload[];
  disposition?: Record<string, unknown> | null;
}

export interface ConsultationSaveResult {
  encounterUuid?: string;
  encounterType?: string;
  savedDrugCount?: number;
  alreadyPrescribed?: string[];
}

export interface VitalDraftValues {
  temperature?: number;
  pulse?: number;
  respiratoryRate?: number;
  systolic?: number;
  diastolic?: number;
  spo2?: number;
  weight?: number;
  height?: number;
}

export function formatOpenmrsDateTime(date = new Date()): string {
  return date.toISOString().replace("Z", "+0000");
}

/** The hospital clock rejects a consultation time that is even a second ahead. */
export function consultationEncounterTime(
  visitStartDatetime?: string | null,
  now = new Date(),
): string {
  const latestSafe = now.getTime() - 15_000;
  const start = parseOpenmrsDateTime(visitStartDatetime)?.getTime();
  const chosen =
    start != null && start > latestSafe && start <= now.getTime() ? start : latestSafe;
  return formatOpenmrsDateTime(new Date(chosen));
}

function safeConsultationEncounterTime(
  value: string | undefined,
  visitStartDatetime?: string | null,
  now = new Date(),
): string {
  const parsed = parseOpenmrsDateTime(value);
  if (value && parsed && parsed.getTime() < now.getTime() - 1000) {
    return value;
  }
  return consultationEncounterTime(visitStartDatetime, now);
}

export async function fetchProviderUuidForUser(userUuid: string): Promise<string> {
  const data = await openmrsGet<{
    results?: Array<{ uuid?: string; retired?: boolean }>;
  }>(
    `/openmrs/ws/rest/v1/provider?user=${encodeURIComponent(userUuid)}&v=custom:(uuid,retired)`,
  );
  const provider = (data.results ?? []).find((row) => row.uuid && !row.retired);
  if (!provider?.uuid) {
    throw new OpenmrsRequestError("This account is not set up as a clinician.");
  }
  return provider.uuid;
}

export async function startOpdVisit(input: {
  patientUuid: string;
  locationUuid: string;
}): Promise<{ uuid: string }> {
  const visit = await openmrsPost<{ uuid: string }>("/openmrs/ws/rest/v1/visit", {
    patient: input.patientUuid,
    visitType: OPD_VISIT_TYPE_UUID,
    location: input.locationUuid,
    startDatetime: formatOpenmrsDateTime(),
  });
  if (!visit.uuid) {
    throw new OpenmrsRequestError("The visit could not be started. Try again.");
  }
  return visit;
}

export interface DiagnosisSearchHit {
  conceptUuid: string;
  conceptName: string;
  matchedName?: string;
}

export async function searchDiagnosisConcepts(term: string): Promise<DiagnosisSearchHit[]> {
  const query = term.trim();
  if (query.length < 2) {
    return [];
  }
  const params = new URLSearchParams({
    term: query,
    limit: String(DIAGNOSIS_SEARCH_LIMIT),
  });
  const data = await openmrsGet<
    Array<{ conceptUuid?: string; conceptName?: string; matchedName?: string }>
  >(`${DIAGNOSIS_SEARCH_URL}?${params.toString()}`);
  return (Array.isArray(data) ? data : [])
    .filter((row) => row.conceptUuid && row.conceptName)
    .map((row) => ({
      conceptUuid: row.conceptUuid as string,
      conceptName: row.conceptName as string,
      matchedName: row.matchedName,
    }));
}

interface DiagnosisSearchRow {
  existingObs?: string;
  encounterUuid?: string;
  order?: string;
  certainty?: string;
  freeTextAnswer?: string;
  codedAnswer?: { uuid?: string; name?: string; shortName?: string };
}

export async function fetchPatientDiagnoses(patientUuid: string): Promise<DiagnosisRecord[]> {
  const data = await openmrsGet<DiagnosisSearchRow[] | { results?: DiagnosisSearchRow[] }>(
    `${DIAGNOSIS_READ_URL}?patientUuid=${encodeURIComponent(patientUuid)}`,
  );
  const rows = Array.isArray(data) ? data : data.results ?? [];
  return rows.map((row, index) => {
    const display =
      row.codedAnswer?.shortName ||
      row.codedAnswer?.name ||
      row.freeTextAnswer ||
      "Diagnosis";
    const order = row.order === "SECONDARY" ? "SECONDARY" : row.order === "PRIMARY" ? "PRIMARY" : undefined;
    return {
      uuid: row.existingObs || row.codedAnswer?.uuid || `diagnosis-${index}`,
      display,
      order,
      certainty: row.certainty,
      conceptUuid: row.codedAnswer?.uuid,
    };
  });
}

export function diagnosesFromDraft(draft: DiagnosisDraftItem[]): BahmniDiagnosisPayload[] {
  return draft.map((item) => ({
    codedAnswer: { uuid: item.conceptUuid },
    order: item.order,
    certainty: "CONFIRMED",
    existingObs: null,
    diagnosisDateTime: null,
    diagnosisStatusConcept: null,
    voided: false,
    comments: "",
  }));
}

export function vitalObservationsFromDraft(
  values: VitalDraftValues,
): EncounterObservation[] {
  const observations: EncounterObservation[] = [];
  (Object.keys(VITAL_CONCEPTS) as VitalConceptKey[]).forEach((key) => {
    const value = values[key];
    if (value === undefined || Number.isNaN(value)) {
      return;
    }
    const concept = VITAL_CONCEPTS[key];
    observations.push({
      concept: {
        uuid: concept.uuid,
        name: concept.name,
        dataType: concept.dataType,
      },
      value,
      voided: false,
    });
  });
  return observations;
}

export function buildConsultationPayload(
  input: ConsultationSaveInput,
): Record<string, unknown> {
  const encounterDateTime = safeConsultationEncounterTime(
    input.encounterDateTime,
    input.visitStartDatetime,
  );
  return {
    patientUuid: input.patientUuid,
    visitUuid: input.visitUuid,
    visitType: input.visitType || OPD_VISIT_TYPE_NAME,
    encounterTypeUuid: CONSULTATION_ENCOUNTER_TYPE,
    encounterDateTime,
    locationUuid: input.locationUuid,
    providers: [{ uuid: input.providerUuid }],
    observations: input.observations ?? [],
    bahmniDiagnoses: input.bahmniDiagnoses ?? [],
    orders: input.orders ?? [],
    drugOrders: (input.drugOrders ?? []).map((order) => {
      const { staffName: _staffName, ...payload } = order;
      const scheduled = payload as { scheduledDate?: string };
      if (!scheduled.scheduledDate) {
        scheduled.scheduledDate = encounterDateTime;
      }
      return payload;
    }),
    disposition: input.disposition ?? undefined,
    ...(input.encounterUuid ? { encounterUuid: input.encounterUuid } : {}),
  };
}

export interface OpenConsultationEncounter {
  uuid: string;
  encounterDatetime?: string;
}

export async function fetchOpenConsultationEncounter(
  visitUuid: string,
): Promise<OpenConsultationEncounter | null> {
  const visit = await openmrsGet<{
    encounters?: Array<{
      uuid?: string;
      encounterDatetime?: string;
      encounterType?: { uuid?: string; name?: string };
    }>;
  }>(
    `/openmrs/ws/rest/v1/visit/${encodeURIComponent(visitUuid)}?v=custom:(uuid,encounters:(uuid,encounterDatetime,encounterType:(uuid,name)))`,
  );
  const rows = (visit.encounters ?? [])
    .filter(
      (row) =>
        Boolean(row.uuid) &&
        (row.encounterType?.uuid === CONSULTATION_ENCOUNTER_TYPE ||
          row.encounterType?.name === "Consultation"),
    )
    .sort((left, right) =>
      (right.encounterDatetime || "").localeCompare(left.encounterDatetime || ""),
    );
  const latest = rows[0];
  return latest?.uuid
    ? { uuid: latest.uuid, encounterDatetime: latest.encounterDatetime }
    : null;
}

export function isAlreadyPrescribedError(message: string): boolean {
  const text = message.toLowerCase();
  return text.includes("more than one") || text.includes("order.cannot.have.more.than.one");
}

export function consultationWrites(input: ConsultationSaveInput): ConsultationSaveInput[] {
  const drugs = input.drugOrders ?? [];
  const notes: ConsultationSaveInput = { ...input, drugOrders: [] };
  const hasNotes = Boolean(
    notes.observations?.length || notes.bahmniDiagnoses?.length || notes.orders?.length,
  );
  const writes: ConsultationSaveInput[] = [];
  if (hasNotes || drugs.length === 0) {
    writes.push(notes);
  }
  drugs.forEach((drug) => {
    writes.push({
      ...input,
      encounterUuid: undefined,
      observations: [],
      bahmniDiagnoses: [],
      orders: [],
      drugOrders: [drug],
    });
  });
  return writes;
}

async function postConsultation(input: ConsultationSaveInput): Promise<ConsultationSaveResult> {
  const saved = await openmrsPost<
    ConsultationSaveResult & {
      observations?: Array<{ encounterUuid?: string }>;
    }
  >(BAHMNI_ENCOUNTER_URL, buildConsultationPayload(input));
  return {
    encounterUuid: saved.encounterUuid || saved.observations?.[0]?.encounterUuid,
    encounterType: saved.encounterType,
  };
}

export async function saveConsultation(
  input: ConsultationSaveInput,
): Promise<ConsultationSaveResult> {
  if (!input.visitUuid) {
    throw new OpenmrsRequestError("A visit is required before saving a consultation");
  }
  if (!input.providerUuid) {
    throw new OpenmrsRequestError("A provider is required before saving a consultation");
  }
  if (!visitHasStarted(input.visitStartDatetime)) {
    throw new OpenmrsRequestError(VISIT_NOT_STARTED_MESSAGE);
  }
  let encounterUuid = input.encounterUuid;
  let savedDrugCount = 0;
  const alreadyPrescribed: string[] = [];
  for (const write of consultationWrites(input)) {
    const drug = write.drugOrders?.[0];
    if (drug && encounterUuid) {
      write.encounterUuid = encounterUuid;
    }
    try {
      const saved = await postConsultation(write);
      if (saved.encounterUuid) {
        encounterUuid = saved.encounterUuid;
      }
      if (drug) {
        savedDrugCount += 1;
      } else if (saved.encounterUuid) {
        encounterUuid = saved.encounterUuid;
      }
    } catch (error) {
      const message = error instanceof OpenmrsRequestError ? error.message : "";
      if (drug && isAlreadyPrescribedError(message)) {
        alreadyPrescribed.push(drug.staffName || drug.drugNonCoded || "This medicine");
        continue;
      }
      if (savedDrugCount > 0) {
        throw new OpenmrsRequestError(
          `${savedDrugCount} medicine${savedDrugCount === 1 ? "" : "s"} saved. ${message || "The remaining medicines could not be saved."}`,
        );
      }
      if (isAlreadyPrescribedError(message)) {
        throw new OpenmrsRequestError("This medicine is already prescribed for this patient.");
      }
      throw error;
    }
  }
  return { encounterUuid, savedDrugCount, alreadyPrescribed };
}

export async function saveConditions(
  patientUuid: string,
  conditions: Array<Record<string, unknown>>,
): Promise<unknown> {
  const body = conditions.map((row) => ({
    ...row,
    patientUuid: row.patientUuid ?? patientUuid,
  }));
  return openmrsPost(EMRAPI_CONDITION_URL, body);
}
