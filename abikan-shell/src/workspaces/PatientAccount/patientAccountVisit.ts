import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes.ts";
import type { PatientVisitSummary } from "../../types";
import { visitNumberLabel } from "../../utils/dailyVisitNumber.ts";
import {
  bindConsultationVisit,
  type BoundConsultationVisit,
} from "../Doctor/consultationVisit.ts";

/**
 * Patient Account bills are patient-level.
 * The header visit line is visit-level only when a visit is explicitly selected.
 * Never substitute the first open visit, the latest visit, or a billed visit.
 */
export function bindPatientAccountVisit(input: {
  selectedVisitUuid: string | null | undefined;
  patientUuid: string;
  visits: PatientVisitSummary[];
  extraVisit?: { visit: PatientVisitSummary; patientUuid: string } | null;
}): BoundConsultationVisit {
  return bindConsultationVisit(input);
}

export function selectedPatientAccountVisit(
  bound: BoundConsultationVisit,
): PatientVisitSummary | null {
  return bound.status === "selected" ? bound.visit : null;
}

/** Header copy: "Visit #001 · General Outpatient". Location is not included. */
export function patientAccountVisitLabel(visit: PatientVisitSummary | null): string | undefined {
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
 * It is not a visit type and adds no clinical value on this financial screen.
 */
export const PATIENT_ACCOUNT_SHOWS_LOCATION = false;
