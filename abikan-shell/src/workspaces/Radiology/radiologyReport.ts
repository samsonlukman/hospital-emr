import { CONSULTATION_ENCOUNTER_TYPE } from "../../config/clinicalConcepts.ts";
import { OpenmrsRequestError } from "../../services/openmrs/client.ts";
import type { EncounterObservation } from "../../services/openmrs/clinicalEncounter.ts";
import type { RadiologyNoteSummary, RadiologyOrderSummary } from "../../types";
import { radiologyStaffName } from "./radiologyDesk.ts";

export const RADIOLOGY_NOTES_CONCEPT_UUID = "ae6e5490-ade9-486e-8268-9e4efd45b07e";

export const RADIOLOGY_REPORT_PLACEHOLDER =
  "Enter the radiology findings and impression.";
export const NO_RADIOLOGY_REPORT = "No report recorded for this examination.";
export const RADIOLOGY_NOTES_CONCEPT_NAME = "Radiology Notes";

export type RadiologyReportAvailability = "pending" | "available";

export function radiologyReportAvailability(
  note: RadiologyNoteSummary | null | undefined,
): RadiologyReportAvailability {
  return note?.uuid && note.value.trim() ? "available" : "pending";
}

export function radiologyReportActionLabel(
  note: RadiologyNoteSummary | null | undefined,
): "Write Report" | "Edit Report" {
  return radiologyReportAvailability(note) === "available" ? "Edit Report" : "Write Report";
}

export function radiologyReportOpenLabel(
  note: RadiologyNoteSummary | null | undefined,
): "Write Report" | "View Report" {
  return radiologyReportAvailability(note) === "available" ? "View Report" : "Write Report";
}

export function radiologyReportStatusLabel(
  note: RadiologyNoteSummary | null | undefined,
): "Report pending" | "Report available" {
  return radiologyReportAvailability(note) === "available"
    ? "Report available"
    : "Report pending";
}

function sameId(left: string | undefined, right: string | undefined): boolean {
  return Boolean(left && right && left === right);
}

/** One current Radiology Notes row for this patient + visit + order. Never falls back. */
export function radiologyNoteForOrder(
  notes: RadiologyNoteSummary[],
  input: {
    patientUuid: string;
    visitUuid: string;
    orderUuid: string;
  },
): RadiologyNoteSummary | null {
  const patientUuid = (input.patientUuid || "").trim();
  const visitUuid = (input.visitUuid || "").trim();
  const orderUuid = (input.orderUuid || "").trim();
  if (!patientUuid || !visitUuid || !orderUuid) {
    return null;
  }
  const matches = notes.filter(
    (note) =>
      sameId(note.patientUuid, patientUuid) &&
      sameId(note.visitUuid, visitUuid) &&
      sameId(note.orderUuid, orderUuid) &&
      Boolean(note.uuid),
  );
  if (matches.length === 0) {
    return null;
  }
  return [...matches].sort((left, right) =>
    (right.obsDatetime || right.observedAt || "").localeCompare(
      left.obsDatetime || left.observedAt || "",
    ),
  )[0];
}

export function radiologyNoteForListedOrder(
  notes: RadiologyNoteSummary[],
  order: Pick<RadiologyOrderSummary, "uuid" | "patientUuid" | "visitUuid">,
  scope: { patientUuid?: string; visitUuid?: string } = {},
): RadiologyNoteSummary | null {
  const patientUuid = (scope.patientUuid || order.patientUuid || "").trim();
  const visitUuid = (scope.visitUuid || order.visitUuid || "").trim();
  if (visitUuid) {
    return radiologyNoteForOrder(notes, {
      patientUuid,
      visitUuid,
      orderUuid: order.uuid,
    });
  }
  if (!patientUuid || !order.uuid) {
    return null;
  }
  const matches = notes.filter(
    (note) =>
      sameId(note.patientUuid, patientUuid) &&
      sameId(note.orderUuid, order.uuid) &&
      Boolean(note.uuid) &&
      Boolean(note.visitUuid),
  );
  if (matches.length === 0) {
    return null;
  }
  return [...matches].sort((left, right) =>
    (right.obsDatetime || right.observedAt || "").localeCompare(
      left.obsDatetime || left.observedAt || "",
    ),
  )[0];
}

export function radiologyExaminationReportView(
  order: Pick<RadiologyOrderSummary, "uuid" | "investigation" | "billingStatus">,
  notes: RadiologyNoteSummary[],
  input: { patientUuid: string; visitUuid: string | null | undefined },
): {
  examination: string;
  payment: string;
  report: string | null;
  empty: string | null;
  reportedBy: string;
  reportedAt: string;
} {
  const note = radiologyNoteForOrder(notes, {
    patientUuid: input.patientUuid,
    visitUuid: (input.visitUuid || "").trim(),
    orderUuid: order.uuid,
  });
  return {
    examination: order.investigation,
    payment: order.billingStatus || "",
    report: note?.value?.trim() ? note.value : null,
    empty: note?.value?.trim() ? null : NO_RADIOLOGY_REPORT,
    reportedBy:
      note?.reportedBy && radiologyStaffName(note.reportedBy) !== "—"
        ? radiologyStaffName(note.reportedBy)
        : "",
    reportedAt: note?.observedAt && note.observedAt !== "—" ? note.observedAt : "",
  };
}

export function radiologyNotesForVisit(
  notes: RadiologyNoteSummary[],
  input: { patientUuid: string; visitUuid: string },
): RadiologyNoteSummary[] {
  const patientUuid = (input.patientUuid || "").trim();
  const visitUuid = (input.visitUuid || "").trim();
  if (!patientUuid || !visitUuid) {
    return [];
  }
  return notes.filter(
    (note) =>
      sameId(note.patientUuid, patientUuid) && sameId(note.visitUuid, visitUuid),
  );
}

export function preparedRadiologyReportText(
  value: string,
): { ok: true; text: string } | { ok: false; message: string } {
  const text = value.replace(/\u00a0/g, " ").trim();
  if (!text || text === RADIOLOGY_REPORT_PLACEHOLDER) {
    return {
      ok: false,
      message: "Enter the radiology findings and impression before saving.",
    };
  }
  return { ok: true, text };
}

export function radiologyReportObservation(input: {
  observationUuid?: string;
  value: string;
  orderUuid: string;
}): EncounterObservation {
  return {
    ...(input.observationUuid ? { uuid: input.observationUuid } : {}),
    concept: {
      uuid: RADIOLOGY_NOTES_CONCEPT_UUID,
      name: RADIOLOGY_NOTES_CONCEPT_NAME,
      dataType: "Text",
    },
    value: input.value,
    orderUuid: input.orderUuid,
    voided: false,
  };
}

/** Reuse the existing encounter. Never omit encounterUuid. Never add a new order. */
export function radiologyReportEncounterPayload(input: {
  patientUuid: string;
  visitUuid: string;
  visitType: string;
  encounterUuid: string;
  encounterDateTime: string;
  locationUuid: string;
  providerUuid: string;
  observation: EncounterObservation;
  encounterTypeUuid?: string;
}): {
  patientUuid: string;
  visitUuid: string;
  visitType: string;
  encounterTypeUuid: string;
  encounterUuid: string;
  encounterDateTime: string;
  locationUuid: string;
  providers: Array<{ uuid: string }>;
  observations: EncounterObservation[];
  bahmniDiagnoses: [];
  orders: [];
  drugOrders: [];
} {
  return {
    patientUuid: input.patientUuid,
    visitUuid: input.visitUuid,
    visitType: input.visitType,
    encounterTypeUuid: input.encounterTypeUuid || CONSULTATION_ENCOUNTER_TYPE,
    encounterUuid: input.encounterUuid,
    encounterDateTime: input.encounterDateTime,
    locationUuid: input.locationUuid,
    providers: [{ uuid: input.providerUuid }],
    observations: [input.observation],
    bahmniDiagnoses: [],
    orders: [],
    drugOrders: [],
  };
}

export function canWriteRadiologyReport(input: {
  patientUuid: string;
  visitUuid: string;
  encounterUuid: string;
  orderUuid: string;
  orderPatientUuid?: string;
  orderVisitUuid?: string;
  orderEncounterUuid?: string;
}): { ok: true } | { ok: false; message: string } {
  const patientUuid = (input.patientUuid || "").trim();
  const visitUuid = (input.visitUuid || "").trim();
  const encounterUuid = (input.encounterUuid || "").trim();
  const orderUuid = (input.orderUuid || "").trim();
  if (!orderUuid) {
    return { ok: false, message: "This imaging request was not found." };
  }
  if (!patientUuid || !visitUuid) {
    return {
      ok: false,
      message: "This imaging request is not linked to a visit, so a report cannot be recorded.",
    };
  }
  if (!encounterUuid) {
    return {
      ok: false,
      message: "This imaging request has no consultation, so a report cannot be recorded.",
    };
  }
  if (input.orderPatientUuid && input.orderPatientUuid !== patientUuid) {
    return {
      ok: false,
      message: "This imaging request does not belong to this patient.",
    };
  }
  if (input.orderVisitUuid && input.orderVisitUuid !== visitUuid) {
    return {
      ok: false,
      message: "This imaging request is not on the selected visit.",
    };
  }
  if (input.orderEncounterUuid && input.orderEncounterUuid !== encounterUuid) {
    return {
      ok: false,
      message: "This imaging request is not on the selected visit.",
    };
  }
  return { ok: true };
}

export function existingRadiologyNoteUuid(
  note: RadiologyNoteSummary | null | undefined,
): string | undefined {
  const uuid = note?.uuid?.trim();
  return uuid || undefined;
}

const TECHNICAL_ERROR =
  /openmrs|bahmni|uuid|endpoint|obs\b|econnreset|enotfound|etimedout|econnrefused|failed to fetch|networkerror|network request failed|load failed/i;

export function staffMessageForRadiologyReportError(error: unknown): string {
  if (error instanceof OpenmrsRequestError) {
    if (error.status === 401 || error.message === "unauthenticated") {
      return "Sign in required.";
    }
    if (error.status === 403) {
      return "You do not have permission to save this report.";
    }
    if (error.status === 404) {
      return "This imaging request was not found.";
    }
    if (
      error.message &&
      !TECHNICAL_ERROR.test(error.message) &&
      (error.message.includes(" ") || error.status === 409 || error.status === 422)
    ) {
      return error.message;
    }
  }
  return "The report could not be saved. Try again.";
}
