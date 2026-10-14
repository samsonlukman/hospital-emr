import { OPD_VISIT_TYPE_NAME } from "../../config/clinicalConcepts";
import { hospitalRadiologyLabel } from "../../config/radiologyMenu";
import type {
  PacsQueryState,
  PacsStudySummary,
  RadiologyEncounterSummary,
  RadiologyNoteSummary,
  RadiologyOrderSummary,
} from "../../types";
import { formatClinicalWhen } from "../../utils/datetime";
import {
  canWriteRadiologyReport,
  existingRadiologyNoteUuid,
  preparedRadiologyReportText,
  radiologyNoteForOrder,
  radiologyReportEncounterPayload,
  radiologyReportObservation,
  RADIOLOGY_NOTES_CONCEPT_UUID,
} from "../../workspaces/Radiology/radiologyReport";
import { OpenmrsRequestError, openmrsGet, openmrsPost } from "./client";
import {
  BAHMNI_ENCOUNTER_URL,
  fetchProviderUuidForUser,
  formatOpenmrsDateTime,
} from "./clinicalEncounter";
import { parsePatientDisplay } from "./clinicalPatient";
import { visitHasStarted, VISIT_NOT_STARTED_MESSAGE } from "./visitWindow";
import { attendingDoctorName } from "./visitAttendingProvider";

export const RADIOLOGY_ORDER_TYPE_UUID = "d3561dc0-5e07-11ef-8f7c-0242ac120002";
export const RADIOLOGY_ENCOUNTER_TYPE_UUID = "d3a89c59-5e07-11ef-8f7c-0242ac120002";
export { RADIOLOGY_NOTES_CONCEPT_UUID };

interface NamedValue {
  uuid?: string;
  name?: string;
  display?: string;
}

interface BahmniOrderResponse {
  uuid?: string;
  orderUuid?: string;
  orderNumber?: string;
  dateCreated?: string;
  dateActivated?: string;
  orderDate?: string;
  urgency?: string;
  commentToFulfiller?: string;
  accessionNumber?: string;
  provider?: string | NamedValue;
  concept?: NamedValue;
  conceptName?: string;
  patientUuid?: string;
  patient?: { uuid?: string; display?: string };
}

interface EncounterResponse {
  uuid?: string;
  display?: string;
  encounterDatetime?: string;
}

interface ImagingStudyRaw {
  started?: string;
  status?: string;
  identifier?: Array<{ system?: string; value?: string }>;
}

function displayOf(value: string | NamedValue | undefined): string {
  if (!value) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  return value.display || value.name || "";
}

function mapOrder(
  raw: BahmniOrderResponse,
  extras: {
    visitUuid?: string;
    encounterUuid?: string;
    encounterTypeUuid?: string;
    encounterDatetime?: string;
    visitType?: string;
  } = {},
): RadiologyOrderSummary {
  const patientDisplay = raw.patient?.display || "";
  const parsed = parsePatientDisplay(patientDisplay);
  const conceptUuid = raw.concept?.uuid || "";
  const comment = raw.commentToFulfiller || "";
  const requestSource =
    extras.encounterTypeUuid === RADIOLOGY_ENCOUNTER_TYPE_UUID ||
    comment.startsWith("[Radiology Direct]") ||
    comment.startsWith("Radiology Direct")
      ? "radiology_direct"
      : "doctor_order";
  return {
    uuid: raw.uuid || raw.orderUuid || "",
    orderNumber: raw.orderNumber || "—",
    investigation: hospitalRadiologyLabel(
      conceptUuid,
      raw.conceptName || displayOf(raw.concept) || "Radiology order",
    ),
    conceptUuid,
    visitUuid: extras.visitUuid || "",
    encounterUuid: extras.encounterUuid || "",
    encounterTypeUuid: extras.encounterTypeUuid || "",
    encounterDatetime: extras.encounterDatetime || "",
    visitType: extras.visitType || "",
    patientUuid: raw.patientUuid || raw.patient?.uuid || "",
    patientName: parsed.name || "Unknown patient",
    mrn: parsed.mrn,
    ordered: formatClinicalWhen(raw.dateActivated || raw.dateCreated || raw.orderDate),
    urgency: raw.urgency === "STAT" ? "STAT" : raw.urgency || "Routine",
    comment,
    clinicalIndication: comment
      .replace(/^\[Radiology Direct\]\s*/i, "")
      .replace(/^Radiology Direct:?\s*/i, "")
      .trim(),
    requestSource,
    requestSourceLabel: requestSource === "radiology_direct" ? "Radiology Direct" : "Doctor Order",
    provider: displayOf(raw.provider) || "—",
    accession: raw.accessionNumber || "—",
  };
}

function identifierValue(
  identifiers: ImagingStudyRaw["identifier"],
  system: string,
): string {
  const match = identifiers?.find((item) => item.system === system);
  return match?.value || "";
}

function mapStudy(raw: ImagingStudyRaw): PacsStudySummary {
  return {
    studyUid: identifierValue(raw.identifier, "urn:dicom:uid") || "—",
    accessionNumber: identifierValue(raw.identifier, "urn:bahmni:accession") || "—",
    started: formatClinicalWhen(raw.started),
    status: raw.status || "—",
  };
}

function obsValue(value: string | { display?: string; uuid?: string } | undefined): string {
  if (!value) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  return value.display || "—";
}

export async function fetchRadiologyOrders(
  patientUuid: string,
): Promise<RadiologyOrderSummary[]> {
  const query = new URLSearchParams({
    patientUuid,
    orderTypeUuid: RADIOLOGY_ORDER_TYPE_UUID,
  });
  const response = await openmrsGet<BahmniOrderResponse[] | { results?: BahmniOrderResponse[] }>(
    `/openmrs/ws/rest/v1/bahmnicore/orders?${query.toString()}`,
  );
  const rows = Array.isArray(response) ? response : response.results ?? [];
  return rows.map((row) => mapOrder(row)).filter((mapped) => mapped.uuid);
}

export async function fetchRadiologyOrder(
  orderUuid: string,
): Promise<RadiologyOrderSummary | null> {
  const selected = orderUuid.trim();
  if (!selected) {
    return null;
  }
  try {
    const raw = await openmrsGet<{
      uuid?: string;
      voided?: boolean;
      orderNumber?: string;
      dateActivated?: string;
      dateCreated?: string;
      urgency?: string;
      commentToFulfiller?: string;
      accessionNumber?: string;
      patient?: { uuid?: string; display?: string };
      encounter?: {
        uuid?: string;
        encounterDatetime?: string;
        visit?: { uuid?: string; visitType?: { name?: string } };
      };
      concept?: NamedValue;
      orderType?: NamedValue;
      orderer?: NamedValue;
    }>(
      `/openmrs/ws/rest/v1/order/${encodeURIComponent(selected)}?v=custom:(uuid,orderNumber,dateActivated,dateCreated,urgency,commentToFulfiller,accessionNumber,voided,patient:(uuid,display),encounter:(uuid,encounterDatetime,visit:(uuid,visitType:(name))),concept:(uuid,display),orderType:(uuid,display),orderer:(display))`,
    );
    if (!raw.uuid || raw.voided) {
      return null;
    }
    const typeUuid = raw.orderType?.uuid || "";
    const typeName = raw.orderType?.display || raw.orderType?.name || "";
    if (typeUuid !== RADIOLOGY_ORDER_TYPE_UUID && typeName !== "Radiology Order") {
      return null;
    }
    const visit = raw.encounter?.visit;
    return mapOrder(
      {
        uuid: raw.uuid,
        orderNumber: raw.orderNumber,
        dateActivated: raw.dateActivated,
        dateCreated: raw.dateCreated,
        urgency: raw.urgency,
        commentToFulfiller: raw.commentToFulfiller,
        accessionNumber: raw.accessionNumber,
        provider: raw.orderer,
        concept: raw.concept,
        patient: raw.patient,
      },
      {
        visitUuid: visit?.uuid || "",
        encounterUuid: raw.encounter?.uuid || "",
        encounterDatetime: raw.encounter?.encounterDatetime || "",
        visitType: visit?.visitType?.name || "",
      },
    );
  } catch (error) {
    if (error instanceof OpenmrsRequestError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

interface VisitOrderRaw {
  uuid?: string;
  orderNumber?: string;
  dateActivated?: string;
  dateCreated?: string;
  urgency?: string;
  commentToFulfiller?: string;
  accessionNumber?: string;
  orderer?: NamedValue;
  concept?: NamedValue;
  orderType?: NamedValue;
  patient?: { uuid?: string; display?: string };
}

/**
 * Orders on the selected visit only. Empty when no visitUuid is provided.
 */
export async function fetchRadiologyOrdersForVisit(
  patientUuid: string,
  visitUuid: string | null | undefined,
): Promise<RadiologyOrderSummary[]> {
  const selected = (visitUuid || "").trim();
  if (!selected) {
    return [];
  }
  const visit = await openmrsGet<{
    uuid?: string;
    visitType?: { name?: string };
    patient?: { uuid?: string; display?: string };
    encounters?: Array<{
      uuid?: string;
      encounterDatetime?: string;
      encounterType?: { uuid?: string; display?: string; name?: string };
      orders?: VisitOrderRaw[];
    }>;
  }>(
    `/openmrs/ws/rest/v1/visit/${encodeURIComponent(selected)}?v=custom:(uuid,visitType:(name),patient:(uuid,display),encounters:(uuid,encounterDatetime,encounterType:(uuid,display),orders:(uuid,orderNumber,dateActivated,dateCreated,urgency,commentToFulfiller,accessionNumber,orderer:(display),concept:(uuid,display),orderType:(uuid,display),patient:(uuid,display))))`,
  );
  if (!visit.uuid || visit.uuid !== selected) {
    return [];
  }
  if (visit.patient?.uuid && visit.patient.uuid !== patientUuid) {
    return [];
  }
  const rows: RadiologyOrderSummary[] = [];
  for (const encounter of visit.encounters ?? []) {
    for (const raw of encounter.orders ?? []) {
      const typeUuid = raw.orderType?.uuid || "";
      const typeName = raw.orderType?.display || raw.orderType?.name || "";
      if (typeUuid !== RADIOLOGY_ORDER_TYPE_UUID && typeName !== "Radiology Order") {
        continue;
      }
      const mapped = mapOrder(
        {
          uuid: raw.uuid,
          orderNumber: raw.orderNumber,
          dateActivated: raw.dateActivated,
          dateCreated: raw.dateCreated,
          urgency: raw.urgency,
          commentToFulfiller: raw.commentToFulfiller,
          accessionNumber: raw.accessionNumber,
          provider: raw.orderer,
          concept: raw.concept,
          patient: raw.patient || visit.patient,
        },
        {
          visitUuid: selected,
          encounterUuid: encounter.uuid || "",
          encounterTypeUuid: encounter.encounterType?.uuid || "",
          encounterDatetime: encounter.encounterDatetime || "",
          visitType: visit.visitType?.name || "",
        },
      );
      if (mapped.uuid) {
        rows.push({ ...mapped, patientUuid: mapped.patientUuid || patientUuid });
      }
    }
  }
  return rows;
}

interface VisitObsRaw {
  uuid?: string;
  obsDatetime?: string;
  value?: string | { display?: string; uuid?: string };
  voided?: boolean;
  concept?: { uuid?: string; display?: string };
  order?: { uuid?: string };
}

const VISIT_NOTES_REPRESENTATION =
  "custom:(uuid,startDatetime,visitType:(name),patient:(uuid),encounters:(uuid,encounterDatetime,obs:(uuid,obsDatetime,value,voided,concept:(uuid,display),order:(uuid))))";

function mapVisitNote(
  raw: VisitObsRaw,
  input: { visitUuid: string; patientUuid: string; encounterUuid: string },
): RadiologyNoteSummary | null {
  if (raw.voided || !raw.uuid) {
    return null;
  }
  if ((raw.concept?.uuid || "") !== RADIOLOGY_NOTES_CONCEPT_UUID) {
    return null;
  }
  const value = obsValue(raw.value);
  if (!value || value === "—") {
    return null;
  }
  return {
    uuid: raw.uuid,
    value,
    observedAt: formatClinicalWhen(raw.obsDatetime),
    obsDatetime: raw.obsDatetime || "",
    encounterUuid: input.encounterUuid,
    orderUuid: raw.order?.uuid || "",
    visitUuid: input.visitUuid,
    patientUuid: input.patientUuid,
    reportedBy: "—",
  };
}

export async function fetchRadiologyNoteAuthor(observationUuid: string): Promise<string> {
  if (!observationUuid.trim()) {
    return "—";
  }
  try {
    const obs = await openmrsGet<{
      auditInfo?: { creator?: { display?: string; person?: { display?: string } } };
    }>(
      `/openmrs/ws/rest/v1/obs/${encodeURIComponent(observationUuid)}?v=custom:(uuid,auditInfo:(creator:(display,person:(display))))`,
    );
    const creator = obs.auditInfo?.creator;
    const named = attendingDoctorName({
      display: creator?.display,
      person: creator?.person,
    });
    if (!named) {
      return "—";
    }
    if (/^[a-z0-9._-]+\.[a-z0-9._-]+$/i.test(named) && !named.includes(" ")) {
      return "—";
    }
    return named;
  } catch {
    return "—";
  }
}

async function withRadiologyNoteAuthors(
  notes: RadiologyNoteSummary[],
): Promise<RadiologyNoteSummary[]> {
  return Promise.all(
    notes.map(async (note) => ({
      ...note,
      reportedBy: await fetchRadiologyNoteAuthor(note.uuid),
    })),
  );
}

function notesFromVisitPayload(
  visit: {
    uuid?: string;
    patient?: { uuid?: string };
    encounters?: Array<{ uuid?: string; obs?: VisitObsRaw[] }>;
  },
  patientUuid: string,
): RadiologyNoteSummary[] {
  const visitUuid = visit.uuid || "";
  if (!visitUuid) {
    return [];
  }
  if (visit.patient?.uuid && visit.patient.uuid !== patientUuid) {
    return [];
  }
  const rows: RadiologyNoteSummary[] = [];
  for (const encounter of visit.encounters ?? []) {
    for (const raw of encounter.obs ?? []) {
      const mapped = mapVisitNote(raw, {
        visitUuid,
        patientUuid: visit.patient?.uuid || patientUuid,
        encounterUuid: encounter.uuid || "",
      });
      if (mapped) {
        rows.push(mapped);
      }
    }
  }
  return rows;
}

/**
 * Radiology Notes on the selected visit only. Empty when visitUuid is missing
 * or the visit belongs to another patient.
 */
export async function fetchRadiologyNotesForVisit(
  patientUuid: string,
  visitUuid: string | null | undefined,
): Promise<RadiologyNoteSummary[]> {
  const selected = (visitUuid || "").trim();
  if (!selected || !patientUuid.trim()) {
    return [];
  }
  const visit = await openmrsGet<{
    uuid?: string;
    patient?: { uuid?: string };
    encounters?: Array<{ uuid?: string; obs?: VisitObsRaw[] }>;
  }>(`/openmrs/ws/rest/v1/visit/${encodeURIComponent(selected)}?v=${VISIT_NOTES_REPRESENTATION}`);
  if (!visit.uuid || visit.uuid !== selected) {
    return [];
  }
  return withRadiologyNoteAuthors(notesFromVisitPayload(visit, patientUuid));
}

/** Visit-tagged notes for a patient. Not a latest-note fallback. */
export async function fetchRadiologyNotes(
  patientUuid: string,
): Promise<RadiologyNoteSummary[]> {
  const query = new URLSearchParams({
    patient: patientUuid,
    v: VISIT_NOTES_REPRESENTATION,
    limit: "20",
  });
  const response = await openmrsGet<{
    results?: Array<{
      uuid?: string;
      patient?: { uuid?: string };
      encounters?: Array<{ uuid?: string; obs?: VisitObsRaw[] }>;
    }>;
  }>(`/openmrs/ws/rest/v1/visit?${query.toString()}`);
  const rows: RadiologyNoteSummary[] = [];
  for (const visit of response.results ?? []) {
    rows.push(...notesFromVisitPayload(visit, patientUuid));
  }
  return rows;
}

export async function saveRadiologyReport(input: {
  patientUuid: string;
  visitUuid: string;
  visitType?: string;
  visitStartDatetime?: string;
  encounterUuid: string;
  encounterDatetime?: string;
  orderUuid: string;
  locationUuid: string;
  userUuid: string;
  text: string;
}): Promise<RadiologyNoteSummary> {
  const prepared = preparedRadiologyReportText(input.text);
  if (!prepared.ok) {
    throw new OpenmrsRequestError(prepared.message, 422);
  }
  const allowed = canWriteRadiologyReport({
    patientUuid: input.patientUuid,
    visitUuid: input.visitUuid,
    encounterUuid: input.encounterUuid,
    orderUuid: input.orderUuid,
  });
  if (!allowed.ok) {
    throw new OpenmrsRequestError(allowed.message, 409);
  }
  if (!input.locationUuid) {
    throw new OpenmrsRequestError("A consulting location is required.", 422);
  }
  if (!visitHasStarted(input.visitStartDatetime)) {
    throw new OpenmrsRequestError(VISIT_NOT_STARTED_MESSAGE, 409);
  }

  const [currentNotes, visitOrders] = await Promise.all([
    fetchRadiologyNotesForVisit(input.patientUuid, input.visitUuid),
    fetchRadiologyOrdersForVisit(input.patientUuid, input.visitUuid),
  ]);
  const matchingOrder = visitOrders.find((row) => row.uuid === input.orderUuid);
  if (!matchingOrder) {
    throw new OpenmrsRequestError("This imaging request is not on the selected visit.", 409);
  }
  if (matchingOrder.encounterUuid && matchingOrder.encounterUuid !== input.encounterUuid) {
    throw new OpenmrsRequestError("This imaging request is not on the selected visit.", 409);
  }

  const existing = radiologyNoteForOrder(currentNotes, {
    patientUuid: input.patientUuid,
    visitUuid: input.visitUuid,
    orderUuid: input.orderUuid,
  });
  const providerUuid = await fetchProviderUuidForUser(input.userUuid);
  await openmrsPost(
    BAHMNI_ENCOUNTER_URL,
    radiologyReportEncounterPayload({
      patientUuid: input.patientUuid,
      visitUuid: input.visitUuid,
      visitType: input.visitType || matchingOrder.visitType || OPD_VISIT_TYPE_NAME,
      encounterUuid: input.encounterUuid,
      encounterDateTime:
        input.encounterDatetime || matchingOrder.encounterDatetime || formatOpenmrsDateTime(),
      locationUuid: input.locationUuid,
      providerUuid,
      encounterTypeUuid: matchingOrder.encounterTypeUuid,
      observation: radiologyReportObservation({
        observationUuid: existingRadiologyNoteUuid(existing),
        value: prepared.text,
        orderUuid: input.orderUuid,
      }),
    }),
  );

  const savedNotes = await fetchRadiologyNotesForVisit(input.patientUuid, input.visitUuid);
  const saved = radiologyNoteForOrder(savedNotes, {
    patientUuid: input.patientUuid,
    visitUuid: input.visitUuid,
    orderUuid: input.orderUuid,
  });
  if (!saved) {
    throw new OpenmrsRequestError("The report could not be saved. Try again.", 502);
  }
  return saved;
}

export async function fetchRadiologyEncounters(
  patientUuid: string,
): Promise<RadiologyEncounterSummary[]> {
  const query = new URLSearchParams({
    patient: patientUuid,
    encounterType: RADIOLOGY_ENCOUNTER_TYPE_UUID,
    v: "custom:(uuid,display,encounterDatetime)",
  });
  const response = await openmrsGet<{ results?: EncounterResponse[] }>(
    `/openmrs/ws/rest/v1/encounter?${query.toString()}`,
  );
  return (response.results ?? [])
    .map((raw) => ({
      uuid: raw.uuid || "",
      display: raw.display || "Radiology encounter",
      encounterDatetime: formatClinicalWhen(raw.encounterDatetime),
    }))
    .filter((row) => row.uuid);
}

export async function fetchPacsStudies(patientId: string): Promise<PacsQueryState> {
  if (!patientId || patientId === "—") {
    return { status: "skipped", message: "", studies: [] };
  }
  try {
    const query = new URLSearchParams({ patientId });
    const response = await openmrsGet<ImagingStudyRaw[] | { results?: ImagingStudyRaw[] }>(
      `/openmrs/ws/rest/v1/pacs/studies?${query.toString()}`,
    );
    const rows = Array.isArray(response) ? response : response.results ?? [];
    return {
      status: "ok",
      message: "",
      studies: rows.map(mapStudy).filter((row) => row.studyUid !== "—" || row.accessionNumber !== "—"),
    };
  } catch (error) {
    if (error instanceof OpenmrsRequestError && error.status === 501) {
      return {
        status: "unconfigured",
        message: error.message || "PACS Server configuration is not defined",
        studies: [],
      };
    }
    return {
      status: "error",
      message:
        error instanceof Error ? error.message : "Unable to query the PACS server",
      studies: [],
    };
  }
}

export function canOpenOviyam(order: RadiologyOrderSummary): boolean {
  return Boolean(order.mrn && order.mrn !== "—" && order.orderNumber && order.orderNumber !== "—");
}
