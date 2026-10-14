import {
  CHIEF_COMPLAINT_CODED_CONCEPT,
  CHIEF_COMPLAINT_DURATION_UNITS,
  CHIEF_COMPLAINT_DURATION_UNIT_CONCEPT,
  CHIEF_COMPLAINT_DURATION_VALUE_CONCEPT,
  CHIEF_COMPLAINT_RECORD_CONCEPT,
  CHIEF_COMPLAINT_TEXT_CONCEPT,
  CONSULTATION_NOTE_CONCEPT,
  HPI_CONCEPT,
  OTHER_GENERIC_COMPLAINT_UUID,
  VITAL_CONCEPTS,
} from "../../config/clinicalConcepts.ts";
import { openmrsGet } from "./client.ts";
import { displayedDoseUnit } from "./drugOrderMap.ts";
import type { EncounterObservation } from "./clinicalEncounter.ts";

export const NO_CHIEF_COMPLAINT_FOR_VISIT =
  "No chief complaint recorded for this visit.";
export const NO_HISTORY_FOR_VISIT = "No history recorded for this visit.";
export const NO_CLINICAL_NOTES_FOR_VISIT =
  "No clinical notes recorded for this visit.";

export interface CodedAnswer {
  uuid: string;
  name: string;
}

export interface ChiefComplaintObsRefs {
  complaintGroupUuid?: string;
  codedUuid?: string;
  textUuid?: string;
  durationUuid?: string;
  durationUnitUuid?: string;
}

export interface ChiefComplaintDraft {
  key: string;
  codedComplaintUuid: string;
  codedComplaintName: string;
  complaintText: string;
  durationValue: string;
  durationUnitUuid: string;
  obs: ChiefComplaintObsRefs;
}

export interface DocumentationObsRefs {
  hpiUuid?: string;
  noteUuid?: string;
}

export interface DocumentationDraft {
  complaints: ChiefComplaintDraft[];
  hpi: string;
  consultationNote: string;
  obs: DocumentationObsRefs;
}

export const EMPTY_DOCUMENTATION_DRAFT: DocumentationDraft = {
  complaints: [],
  hpi: "",
  consultationNote: "",
  obs: {},
};

export function emptyChiefComplaint(key = "complaint-new"): ChiefComplaintDraft {
  return {
    key,
    codedComplaintUuid: "",
    codedComplaintName: "",
    complaintText: "",
    durationValue: "",
    durationUnitUuid: "",
    obs: {},
  };
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const OPENMRS_CONCEPT_ID_PATTERN = /^[0-9a-f]{36}$/i;

function isUuid(value: string): boolean {
  return UUID_PATTERN.test(value) || OPENMRS_CONCEPT_ID_PATTERN.test(value);
}

interface RawObs {
  uuid?: string;
  obsDatetime?: string;
  voided?: boolean;
  value?: unknown;
  valueCoded?: { uuid?: string; display?: string };
  concept?: { uuid?: string; display?: string };
  groupMembers?: RawObs[];
}

export interface VisitDocumentationPayload {
  uuid?: string;
  patient?: { uuid?: string };
  encounters?: Array<{
    uuid?: string;
    encounterDatetime?: string;
    obs?: RawObs[];
  }>;
}

function durationUnitName(uuid: string): string {
  return CHIEF_COMPLAINT_DURATION_UNITS.find((unit) => unit.uuid === uuid)?.name ?? "";
}

export function emptyDocumentationDraft(): DocumentationDraft {
  return {
    ...EMPTY_DOCUMENTATION_DRAFT,
    obs: {},
  };
}

export function cloneDocumentationDraft(draft: DocumentationDraft): DocumentationDraft {
  return {
    ...draft,
    complaints: draft.complaints.map((row) => ({ ...row, obs: { ...row.obs } })),
    obs: { ...draft.obs },
  };
}

export function parseObsText(value: unknown): string {
  if (value == null || value === "") {
    return "";
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "string") {
    return isUuid(value) ? "" : value;
  }
  if (typeof value === "object") {
    const row = value as { display?: string; name?: string; uuid?: string };
    if (row.display) {
      return row.display;
    }
    if (typeof row.name === "string" && !isUuid(row.name)) {
      return row.name;
    }
  }
  return "";
}

export function parseObsNumber(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "string" && value.trim() && !isUuid(value)) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? String(parsed) : "";
  }
  return "";
}

export function parseObsCodedUuid(obs: RawObs): string {
  if (obs.valueCoded?.uuid) {
    return obs.valueCoded.uuid;
  }
  const value = obs.value;
  if (typeof value === "string" && isUuid(value)) {
    return value;
  }
  if (value && typeof value === "object") {
    const row = value as { uuid?: string };
    if (row.uuid) {
      return row.uuid;
    }
  }
  return "";
}

function latestObs(rows: RawObs[]): RawObs | undefined {
  return [...rows].sort((left, right) =>
    (right.obsDatetime || "").localeCompare(left.obsDatetime || ""),
  )[0];
}

function memberByConcept(group: RawObs | undefined, conceptUuid: string): RawObs | undefined {
  return group?.groupMembers?.find((row) => row.concept?.uuid === conceptUuid);
}

export function documentationObsFromVisit(
  visit: VisitDocumentationPayload | null | undefined,
  visitUuid: string,
): { complaintGroups: RawObs[]; hpi: RawObs[]; notes: RawObs[] } {
  const complaintGroups: RawObs[] = [];
  const hpi: RawObs[] = [];
  const notes: RawObs[] = [];
  if (!visitUuid || visit?.uuid !== visitUuid) {
    return { complaintGroups, hpi, notes };
  }
  for (const encounter of visit.encounters ?? []) {
    for (const obs of encounter.obs ?? []) {
      const conceptUuid = obs.concept?.uuid;
      if (conceptUuid === CHIEF_COMPLAINT_RECORD_CONCEPT.uuid) {
        complaintGroups.push(obs);
      } else if (conceptUuid === HPI_CONCEPT.uuid) {
        hpi.push(obs);
      } else if (conceptUuid === CONSULTATION_NOTE_CONCEPT.uuid) {
        notes.push(obs);
      }
    }
  }
  return { complaintGroups, hpi, notes };
}

/** Visit-scoped documentation only. Never fall back to another visit's latest obs. */
export function documentationForSelectedVisit(
  visit: VisitDocumentationPayload | null | undefined,
  visitUuid: string | null | undefined,
  patientUuid?: string,
): DocumentationDraft {
  if (!visitUuid) {
    return emptyDocumentationDraft();
  }
  if (patientUuid && visit?.patient?.uuid && visit.patient.uuid !== patientUuid) {
    return emptyDocumentationDraft();
  }
  return documentationFromObservations(documentationObsFromVisit(visit, visitUuid));
}

function complaintFromGroup(group: RawObs, index: number): ChiefComplaintDraft {
  const coded = memberByConcept(group, CHIEF_COMPLAINT_CODED_CONCEPT.uuid);
  const text = memberByConcept(group, CHIEF_COMPLAINT_TEXT_CONCEPT.uuid);
  const duration = memberByConcept(group, CHIEF_COMPLAINT_DURATION_VALUE_CONCEPT.uuid);
  const unit = memberByConcept(group, CHIEF_COMPLAINT_DURATION_UNIT_CONCEPT.uuid);
  return {
    key: group.uuid || `complaint-${index + 1}`,
    codedComplaintUuid: coded ? parseObsCodedUuid(coded) : "",
    codedComplaintName: parseObsText(coded?.value) || parseObsText(coded?.valueCoded),
    complaintText: parseObsText(text?.value),
    durationValue: parseObsNumber(duration?.value),
    durationUnitUuid: unit ? parseObsCodedUuid(unit) : "",
    obs: {
      ...(group.uuid ? { complaintGroupUuid: group.uuid } : {}),
      ...(coded?.uuid ? { codedUuid: coded.uuid } : {}),
      ...(text?.uuid ? { textUuid: text.uuid } : {}),
      ...(duration?.uuid ? { durationUuid: duration.uuid } : {}),
      ...(unit?.uuid ? { durationUnitUuid: unit.uuid } : {}),
    },
  };
}

export function documentationFromObservations(input: {
  complaintGroups?: RawObs[];
  hpi?: RawObs[];
  notes?: RawObs[];
}): DocumentationDraft {
  const groups = [...(input.complaintGroups ?? [])]
    .filter((row) => !row.voided)
    .sort((left, right) => (left.obsDatetime || "").localeCompare(right.obsDatetime || ""));
  const hpi = latestObs(input.hpi ?? []);
  const note = latestObs(input.notes ?? []);
  return {
    complaints: groups.map(complaintFromGroup),
    hpi: parseObsText(hpi?.value),
    consultationNote: parseObsText(note?.value),
    obs: {
      ...(hpi?.uuid ? { hpiUuid: hpi.uuid } : {}),
      ...(note?.uuid ? { noteUuid: note.uuid } : {}),
    },
  };
}

function trimComplaint(row: ChiefComplaintDraft): ChiefComplaintDraft {
  return {
    ...row,
    codedComplaintUuid: row.codedComplaintUuid.trim(),
    codedComplaintName: row.codedComplaintName.trim(),
    complaintText: row.complaintText.trim(),
    durationValue: row.durationValue.trim(),
    durationUnitUuid: row.durationUnitUuid.trim(),
  };
}

export function chiefComplaintIsEmpty(row: ChiefComplaintDraft): boolean {
  const value = trimComplaint(row);
  return !value.codedComplaintUuid && !value.complaintText && !value.durationValue && !value.durationUnitUuid;
}

function trimDraft(draft: DocumentationDraft): DocumentationDraft {
  return {
    ...draft,
    complaints: draft.complaints.map(trimComplaint),
    hpi: draft.hpi.trim(),
    consultationNote: draft.consultationNote.trim(),
  };
}

function complaintsMatch(left: ChiefComplaintDraft[], right: ChiefComplaintDraft[]): boolean {
  const filledLeft = left.filter((row) => !chiefComplaintIsEmpty(row));
  const filledRight = right.filter((row) => !chiefComplaintIsEmpty(row));
  if (filledLeft.length !== filledRight.length) {
    return false;
  }
  return filledLeft.every((row, index) => {
    const other = filledRight[index];
    return (
      row.codedComplaintUuid === other.codedComplaintUuid &&
      row.complaintText === other.complaintText &&
      row.durationValue === other.durationValue &&
      row.durationUnitUuid === other.durationUnitUuid
    );
  });
}

export function documentationDraftsEqual(
  left: DocumentationDraft,
  right: DocumentationDraft,
): boolean {
  const a = trimDraft(left);
  const b = trimDraft(right);
  return complaintsMatch(a.complaints, b.complaints) && a.hpi === b.hpi && a.consultationNote === b.consultationNote;
}

export function documentationHasContent(draft: DocumentationDraft): boolean {
  const value = trimDraft(draft);
  return Boolean(
    value.complaints.some((row) => !chiefComplaintIsEmpty(row)) || value.hpi || value.consultationNote,
  );
}

export function documentationIsDirty(
  draft: DocumentationDraft,
  baseline: DocumentationDraft,
): boolean {
  return !documentationDraftsEqual(draft, baseline);
}

/** Keep typed notes when another part of the consultation is saved. */
export function keepUnsavedDocumentation(
  preserveUnsaved: boolean,
  latest: DocumentationDraft,
  recordedAtStart: DocumentationDraft,
): boolean {
  return preserveUnsaved && documentationIsDirty(latest, recordedAtStart);
}

export function validateDocumentationDraft(draft: DocumentationDraft): string | null {
  for (const row of trimDraft(draft).complaints) {
    if (chiefComplaintIsEmpty(row)) {
      continue;
    }
    if (row.codedComplaintUuid === OTHER_GENERIC_COMPLAINT_UUID && !row.complaintText) {
      return "Enter the chief complaint.";
    }
    if (!row.codedComplaintUuid && !row.complaintText) {
      return "Enter the chief complaint.";
    }
    if (row.durationValue && !row.durationUnitUuid) {
      return "Choose the duration unit for each chief complaint.";
    }
    if (row.durationUnitUuid && !row.durationValue) {
      return "Enter the duration for each chief complaint.";
    }
    if (row.durationValue) {
      const amount = Number(row.durationValue);
      if (!Number.isFinite(amount) || amount < 0) {
        return "Duration must be a number.";
      }
    }
  }
  return null;
}

function conceptPayload(concept: { uuid: string; name: string; dataType: string }) {
  return {
    uuid: concept.uuid,
    name: concept.name,
    dataType: concept.dataType,
  };
}

function leafObs(
  concept: { uuid: string; name: string; dataType: string },
  value: number | string,
  uuid?: string,
): EncounterObservation {
  return {
    ...(uuid ? { uuid } : {}),
    concept: conceptPayload(concept),
    value,
    voided: false,
  };
}

function complaintSignature(row: ChiefComplaintDraft): string {
  return [row.codedComplaintUuid, row.complaintText, row.durationValue, row.durationUnitUuid].join("\u0000");
}

function complaintObservation(row: ChiefComplaintDraft): EncounterObservation | null {
  const members: EncounterObservation[] = [];
  if (row.codedComplaintUuid) {
    members.push(leafObs(CHIEF_COMPLAINT_CODED_CONCEPT, row.codedComplaintUuid, row.obs.codedUuid));
  }
  if (row.complaintText) {
    members.push(leafObs(CHIEF_COMPLAINT_TEXT_CONCEPT, row.complaintText, row.obs.textUuid));
  }
  if (row.durationValue && row.durationUnitUuid) {
    members.push(
      leafObs(CHIEF_COMPLAINT_DURATION_VALUE_CONCEPT, Number(row.durationValue), row.obs.durationUuid),
    );
    members.push(
      leafObs(CHIEF_COMPLAINT_DURATION_UNIT_CONCEPT, row.durationUnitUuid, row.obs.durationUnitUuid),
    );
  }
  if (members.length === 0) {
    return null;
  }
  return {
    ...(row.obs.complaintGroupUuid ? { uuid: row.obs.complaintGroupUuid } : {}),
    concept: conceptPayload(CHIEF_COMPLAINT_RECORD_CONCEPT),
    groupMembers: members,
    voided: false,
  };
}

export function documentationObservationsFromDraft(
  draft: DocumentationDraft,
  baseline: DocumentationDraft = emptyDocumentationDraft(),
): EncounterObservation[] {
  const value = trimDraft(draft);
  const previous = trimDraft(baseline);
  const observations: EncounterObservation[] = [];
  const matched = new Set<number>();
  value.complaints.forEach((row) => {
    if (chiefComplaintIsEmpty(row)) {
      return;
    }
    const savedIndex = previous.complaints.findIndex((item, index) => {
      if (matched.has(index) || chiefComplaintIsEmpty(item)) {
        return false;
      }
      if (row.obs.complaintGroupUuid || item.obs.complaintGroupUuid) {
        return item.obs.complaintGroupUuid === row.obs.complaintGroupUuid;
      }
      return complaintSignature(item) === complaintSignature(row);
    });
    const saved = savedIndex >= 0 ? previous.complaints[savedIndex] : undefined;
    if (saved && complaintSignature(saved) === complaintSignature(row)) {
      matched.add(savedIndex);
      return;
    }
    if (savedIndex >= 0) {
      matched.add(savedIndex);
    }
    const observation = complaintObservation(row);
    if (observation) {
      observations.push(observation);
    }
  });

  previous.complaints.forEach((row, index) => {
    const groupUuid = row.obs.complaintGroupUuid;
    if (!groupUuid || matched.has(index) || chiefComplaintIsEmpty(row)) {
      return;
    }
    observations.push({
      uuid: groupUuid,
      concept: conceptPayload(CHIEF_COMPLAINT_RECORD_CONCEPT),
      voided: true,
    });
  });

  if (value.hpi !== trimDraft(baseline).hpi && value.hpi) {
    observations.push(leafObs(HPI_CONCEPT, value.hpi, value.obs.hpiUuid));
  }

  if (value.consultationNote !== trimDraft(baseline).consultationNote && value.consultationNote) {
    observations.push(
      leafObs(CONSULTATION_NOTE_CONCEPT, value.consultationNote, value.obs.noteUuid),
    );
  }

  return observations;
}

export interface EncounterDetail {
  clinician: string;
  complaint: string;
  history: string;
  notes: string;
  vitals: string[];
  diagnoses: string[];
  orders: string[];
}

interface EncounterDetailOrder {
  voided?: boolean;
  display?: string;
  drugNonCoded?: string;
  commentToFulfiller?: string;
  dose?: number | string;
  duration?: number | string;
  concept?: { display?: string };
  drug?: { display?: string; dosageForm?: { display?: string }; form?: string };
  doseUnits?: { display?: string };
  frequency?: { display?: string };
  durationUnits?: { display?: string };
}

interface EncounterDetailPayload {
  encounterProviders?: Array<{
    display?: string;
    provider?: { display?: string };
  }>;
  obs?: RawObs[];
  orders?: EncounterDetailOrder[];
}

const VITALS_BY_UUID = new Map<string, { label: string; unit: string }>(
  Object.values(VITAL_CONCEPTS).map((concept) => [concept.uuid, concept]),
);

function clinicianName(encounter: EncounterDetailPayload): string {
  const names: string[] = [];
  for (const row of encounter.encounterProviders ?? []) {
    const display = (row.display || row.provider?.display || "").trim();
    if (!display) {
      continue;
    }
    const name = (
      display.includes(" - ")
        ? display.split(" - ").slice(1).join(" - ")
        : display.replace(/:\s*Unknown$/i, "")
    ).trim();
    if (name && !names.includes(name)) {
      names.push(name);
    }
  }
  return names.join(", ");
}

function orderLine(order: EncounterDetailOrder): string {
  const raw =
    order.drug?.display ||
    order.drugNonCoded ||
    order.concept?.display ||
    order.display ||
    "Order";
  const name = raw.replace(/^\(NEW\)\s*/i, "").replace(/:\s*null$/i, "").trim() || "Order";
  const dose = [
    order.dose,
    displayedDoseUnit(order.doseUnits?.display || "", order.drug?.dosageForm?.display || order.drug?.form || ""),
  ]
    .filter(Boolean)
    .join(" ");
  const duration = [order.duration, order.durationUnits?.display].filter(Boolean).join(" ");
  const parts = [name, dose, order.frequency?.display, duration].filter(Boolean);
  const comment = (order.commentToFulfiller || "").trim();
  if (comment) {
    parts.push(comment);
  }
  return parts.join(" · ");
}

function vitalLines(observations: RawObs[]): string[] {
  const lines: string[] = [];
  for (const obs of observations) {
    if (obs.voided) {
      continue;
    }
    const concept = VITALS_BY_UUID.get(obs.concept?.uuid || "");
    if (!concept) {
      continue;
    }
    const value = parseObsNumber(obs.value) || parseObsText(obs.value);
    if (!value) {
      continue;
    }
    lines.push(concept.unit ? `${concept.label} ${value} ${concept.unit}` : `${concept.label} ${value}`);
  }
  return lines;
}

export function encounterDetailFromPayload(
  encounter: EncounterDetailPayload,
  diagnoses: string[] = [],
): EncounterDetail {
  const observations = (encounter.obs ?? []).filter((row) => !row.voided);
  const documented = documentationFromObservations({
    complaintGroups: observations.filter(
      (row) => row.concept?.uuid === CHIEF_COMPLAINT_RECORD_CONCEPT.uuid,
    ),
    hpi: observations.filter((row) => row.concept?.uuid === HPI_CONCEPT.uuid),
    notes: observations.filter((row) => row.concept?.uuid === CONSULTATION_NOTE_CONCEPT.uuid),
  });
  return {
    clinician: clinicianName(encounter),
    complaint: formatChiefComplaintSummary(documented),
    history: documented.hpi.trim(),
    notes: documented.consultationNote.trim(),
    vitals: vitalLines(observations),
    diagnoses: diagnoses.map((item) => item.trim()).filter(Boolean),
    orders: (encounter.orders ?? [])
      .filter((order) => !order.voided)
      .map(orderLine)
      .filter(Boolean),
  };
}

export function encounterDetailIsEmpty(detail: EncounterDetail): boolean {
  return (
    !detail.complaint &&
    !detail.history &&
    !detail.notes &&
    detail.vitals.length === 0 &&
    detail.diagnoses.length === 0 &&
    detail.orders.length === 0
  );
}

const ENCOUNTER_DETAIL_REP =
  "custom:(uuid,encounterProviders:(display)," +
  "obs:(voided,value,concept:(uuid,display),groupMembers:(voided,value,concept:(uuid,display)))," +
  "orders:(voided,display,drugNonCoded,commentToFulfiller,dose,duration," +
  "concept:(display),drug:(display,dosageForm:(display)),doseUnits:(display)," +
  "frequency:(display),durationUnits:(display)))";

export async function fetchEncounterDetail(
  encounterUuid: string,
  patientUuid: string,
): Promise<EncounterDetail> {
  const query = new URLSearchParams({ v: ENCOUNTER_DETAIL_REP });
  const [encounter, diagnosisRows] = await Promise.all([
    openmrsGet<EncounterDetailPayload>(
      `/openmrs/ws/rest/v1/encounter/${encodeURIComponent(encounterUuid)}?${query.toString()}`,
    ),
    openmrsGet<
      | Array<{
          encounterUuid?: string;
          freeTextAnswer?: string;
          codedAnswer?: { name?: string; shortName?: string };
        }>
      | {
          results?: Array<{
            encounterUuid?: string;
            freeTextAnswer?: string;
            codedAnswer?: { name?: string; shortName?: string };
          }>;
        }
    >(`/openmrs/ws/rest/v1/bahmnicore/diagnosis/search?patientUuid=${encodeURIComponent(patientUuid)}`).catch(
      () => [],
    ),
  ]);
  const rows = Array.isArray(diagnosisRows) ? diagnosisRows : diagnosisRows.results ?? [];
  const diagnoses = rows
    .filter((row) => row.encounterUuid === encounterUuid)
    .map(
      (row) =>
        row.codedAnswer?.shortName || row.codedAnswer?.name || row.freeTextAnswer || "",
    );
  return encounterDetailFromPayload(encounter, diagnoses);
}

function formatOneChiefComplaint(row: ChiefComplaintDraft): string {
  const parts: string[] = [];
  const codedName =
    row.codedComplaintName ||
    (row.codedComplaintUuid === OTHER_GENERIC_COMPLAINT_UUID
      ? ""
      : row.codedComplaintUuid
        ? "Chief complaint"
        : "");
  if (codedName && codedName !== row.complaintText) {
    parts.push(codedName);
  }
  if (row.complaintText) {
    parts.push(row.complaintText);
  }
  if (row.durationValue && row.durationUnitUuid) {
    const unit = durationUnitName(row.durationUnitUuid).toLowerCase();
    parts.push(`${row.durationValue} ${unit}`);
  }
  return parts.join(" · ");
}

export function formatChiefComplaintSummary(draft: DocumentationDraft): string {
  return trimDraft(draft)
    .complaints
    .map(formatOneChiefComplaint)
    .filter(Boolean)
    .join("; ");
}

const VISIT_DOCUMENTATION_REP =
  "custom:(uuid,patient:(uuid),encounters:(uuid,encounterDatetime,obs:(uuid,obsDatetime,value,concept:(uuid,display),groupMembers:(uuid,value,concept:(uuid,display)))))";

export async function fetchConsultationDocumentation(
  patientUuid: string,
  visitUuid: string | null | undefined,
): Promise<DocumentationDraft> {
  if (!patientUuid || !visitUuid) {
    return emptyDocumentationDraft();
  }
  const query = new URLSearchParams({ v: VISIT_DOCUMENTATION_REP });
  const visit = await openmrsGet<VisitDocumentationPayload>(
    `/openmrs/ws/rest/v1/visit/${encodeURIComponent(visitUuid)}?${query.toString()}`,
  );
  return documentationForSelectedVisit(visit, visitUuid, patientUuid);
}

export async function fetchChiefComplaintAnswers(): Promise<CodedAnswer[]> {
  const data = await openmrsGet<{
    answers?: Array<{ uuid?: string; display?: string; name?: { name?: string } }>;
  }>(
    `/openmrs/ws/rest/v1/concept/${CHIEF_COMPLAINT_CODED_CONCEPT.uuid}?v=custom:(answers:(uuid,display,name:(name)))`,
  );
  return (data.answers ?? [])
    .filter((row) => row.uuid)
    .map((row) => ({
      uuid: row.uuid as string,
      name: row.display || row.name?.name || "Complaint",
    }));
}
