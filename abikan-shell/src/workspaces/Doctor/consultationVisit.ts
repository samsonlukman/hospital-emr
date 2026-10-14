import {
  DEFAULT_OUTPATIENT_LOCATION_NAME,
  receptionVisitTypeLabel,
} from "../../config/receptionVisitTypes.ts";
import type { PatientVisitSummary } from "../../types";
import type { InpatientStay } from "../../types/inpatient.ts";
import { visitNumberLabel } from "../../utils/dailyVisitNumber.ts";

export type BoundConsultationVisit =
  | { status: "selected"; visit: PatientVisitSummary }
  | { status: "no-selection" }
  | { status: "missing" }
  | { status: "mismatch" }
  | { status: "pending" };

/**
 * The selected visit is authoritative. Never substitute the first open visit.
 */
export function bindConsultationVisit(input: {
  selectedVisitUuid: string | null | undefined;
  patientUuid: string;
  visits: PatientVisitSummary[];
  extraVisit?: { visit: PatientVisitSummary; patientUuid: string } | null;
}): BoundConsultationVisit {
  const selected = (input.selectedVisitUuid || "").trim();
  if (!selected) {
    return { status: "no-selection" };
  }

  const listed = input.visits.find((visit) => visit.uuid === selected);
  if (listed) {
    return { status: "selected", visit: listed };
  }

  if (input.extraVisit && input.extraVisit.visit.uuid === selected) {
    if (!input.extraVisit.patientUuid || input.extraVisit.patientUuid !== input.patientUuid) {
      return { status: "mismatch" };
    }
    return { status: "selected", visit: input.extraVisit.visit };
  }

  if (input.extraVisit === null) {
    return { status: "missing" };
  }

  return { status: "pending" };
}

export function firstOpenVisit(visits: PatientVisitSummary[]): PatientVisitSummary | undefined {
  return visits.find((visit) => visit.open);
}

export function activeConsultationVisit(
  bound: BoundConsultationVisit,
): PatientVisitSummary | null {
  return bound.status === "selected" ? bound.visit : null;
}

export function consultationActionVisitUuid(bound: BoundConsultationVisit): string | undefined {
  return bound.status === "selected" ? bound.visit.uuid : undefined;
}

/** Header copy: "Visit #001 · General Outpatient". OPD-1 is not a visit type. */
export function consultationVisitHeaderLabel(
  visit: PatientVisitSummary | null | undefined,
): string | undefined {
  if (!visit) {
    return undefined;
  }
  const number = visitNumberLabel(visit.dailyVisitNumber);
  const type = receptionVisitTypeLabel(visit.visitType);
  return [number === "—" ? "" : number, type]
    .filter((part) => part && part !== "—")
    .join(" · ") || undefined;
}

/**
 * OPD-1 is the stored OpenMRS location for General Outpatient / Follow-up.
 * It is not useful as a doctor-facing visit label.
 */
export function isInternalOutpatientLocation(location: string | undefined): boolean {
  return (location || "").trim() === DEFAULT_OUTPATIENT_LOCATION_NAME;
}

export function doctorVisitLocationLabel(location: string | undefined): string | undefined {
  const value = (location || "").trim();
  if (!value || value === "—" || isInternalOutpatientLocation(value)) {
    return undefined;
  }
  return value;
}

export const VISIT_NOT_FOUND_MESSAGE =
  "This visit could not be found. Return to Clinical and open the patient again.";

export const VISIT_MISMATCH_MESSAGE =
  "This visit does not belong to this patient. Return to Clinical and open the correct patient.";

export const VISIT_NOT_SELECTED_MESSAGE =
  "Choose a visit from Previous visits to open this patient's chart.";

export const INPATIENT_ORDER_BLOCKED_AWAITING =
  "This patient is waiting for a bed. Nursing must assign a bed before inpatient orders.";

export const INPATIENT_ORDER_BLOCKED_NO_CONTEXT =
  "This admission does not have an active ward visit. Check the admission record before ordering.";

export const OUTPATIENT_VISIT_REQUIRED_PRESCRIBE =
  "Start an open visit before prescribing.";

export const OUTPATIENT_VISIT_REQUIRED_LAB =
  "Start an open visit before ordering laboratory tests.";

export const OUTPATIENT_VISIT_REQUIRED_IMAGING =
  "Start an open visit before ordering imaging.";

export const OUTPATIENT_VISIT_REQUIRED_DOCUMENT =
  "Start an open visit before documenting this consultation.";

export const OUTPATIENT_VISIT_REQUIRED_SAVE =
  "Start an open visit before saving.";

export const INPATIENT_ORDER_USES_ADMISSION =
  "Orders and prescriptions use this patient's current admission.";

export const ADMIT_NURSING_ASSIGNS_BED =
  "Nursing will choose the ward and bed after you admit.";

export function canRequestAdmission(
  stay: InpatientStay | null | undefined,
  patientUuid: string,
): boolean {
  const ownStay = stayBelongsToPatient(stay, patientUuid) ? stay : null;
  return !ownStay?.assignment && !ownStay?.awaiting;
}

export type ClinicalOrderContext =
  | {
      status: "ready";
      visit: PatientVisitSummary;
      source: "active-admission" | "selected-open";
    }
  | {
      status: "blocked";
      reason: string;
      code: "awaiting-bed" | "no-inpatient-context" | "outpatient-visit-required";
    };

function stayBelongsToPatient(
  stay: InpatientStay | null | undefined,
  patientUuid: string,
): boolean {
  const stayPatient = (stay?.patient?.uuid || "").trim();
  return Boolean(stayPatient) && stayPatient === patientUuid;
}

function visitFromAdmission(
  stay: InpatientStay,
  visits: PatientVisitSummary[],
): PatientVisitSummary | null {
  const visitUuid = (stay.visitUuid || "").trim();
  if (!visitUuid) {
    return null;
  }
  const listed = visits.find((visit) => visit.uuid === visitUuid);
  if (listed) {
    return listed.open ? listed : { ...listed, open: true, stop: null };
  }
  return {
    uuid: visitUuid,
    start: "",
    startDate: "",
    startDatetime: stay.visitStartDatetime || "",
    stop: null,
    visitType: "IPD",
    location: stay.assignment?.areaName || "",
    open: true,
    dailyVisitNumber: "",
    attendedBy: "",
  };
}

/**
 * Admitted inpatients use the existing IPD visit. Outpatients still need the
 * selected open visit. Never substitutes the first open OPD visit.
 */
export function resolveClinicalOrderContext(input: {
  patientUuid: string;
  selectedVisit: PatientVisitSummary | null;
  stay: InpatientStay | null | undefined;
  visits: PatientVisitSummary[];
}): ClinicalOrderContext {
  const ownStay = stayBelongsToPatient(input.stay, input.patientUuid)
    ? input.stay
    : null;
  const admitted = Boolean(ownStay?.assignment);

  if (admitted && ownStay) {
    const visit = visitFromAdmission(ownStay, input.visits);
    if (visit) {
      return { status: "ready", visit, source: "active-admission" };
    }
    return {
      status: "blocked",
      reason: INPATIENT_ORDER_BLOCKED_NO_CONTEXT,
      code: "no-inpatient-context",
    };
  }

  if (ownStay?.awaiting) {
    return {
      status: "blocked",
      reason: INPATIENT_ORDER_BLOCKED_AWAITING,
      code: "awaiting-bed",
    };
  }

  if (input.selectedVisit?.open) {
    return {
      status: "ready",
      visit: input.selectedVisit,
      source: "selected-open",
    };
  }

  return {
    status: "blocked",
    reason: OUTPATIENT_VISIT_REQUIRED_PRESCRIBE,
    code: "outpatient-visit-required",
  };
}

export function clinicalOrderVisit(
  context: ClinicalOrderContext,
): PatientVisitSummary | null {
  return context.status === "ready" ? context.visit : null;
}

export function orderBlockedReason(
  context: ClinicalOrderContext,
  action: "prescribe" | "laboratory" | "imaging" | "document" | "save",
): string {
  if (context.status === "ready") {
    return "";
  }
  if (context.code !== "outpatient-visit-required") {
    return context.reason;
  }
  if (action === "laboratory") {
    return OUTPATIENT_VISIT_REQUIRED_LAB;
  }
  if (action === "imaging") {
    return OUTPATIENT_VISIT_REQUIRED_IMAGING;
  }
  if (action === "document") {
    return OUTPATIENT_VISIT_REQUIRED_DOCUMENT;
  }
  if (action === "save") {
    return OUTPATIENT_VISIT_REQUIRED_SAVE;
  }
  return OUTPATIENT_VISIT_REQUIRED_PRESCRIBE;
}

export function clinicalOrderVisitType(visitType?: string): string {
  const value = (visitType || "").trim();
  return value || "OPD";
}

export function shouldOfferStartOpdVisit(input: {
  orderContext: ClinicalOrderContext;
  stay: InpatientStay | null | undefined;
  patientUuid: string;
}): boolean {
  if (input.orderContext.status === "ready") {
    return false;
  }
  if (input.orderContext.code !== "outpatient-visit-required") {
    return false;
  }
  const ownStay = stayBelongsToPatient(input.stay, input.patientUuid)
    ? input.stay
    : null;
  return !ownStay?.assignment && !ownStay?.awaiting;
}
