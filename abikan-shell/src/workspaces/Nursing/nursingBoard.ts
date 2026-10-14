import { PatientAccountRequestError } from "../../services/patientAccount";
import type { InpatientArea, InpatientBed } from "../../types/inpatient";

export type NursingView =
  | "dashboard"
  | "ward-board"
  | "patients"
  | "visits"
  | "treatments"
  | "admissions"
  | "transfers"
  | "discharges"
  | "pricing";

export function nursingViewFromNav(navItemId: string | null): NursingView {
  if (
    navItemId === "ward-board" ||
    navItemId === "patients" ||
    navItemId === "visits" ||
    navItemId === "todays-visits" ||
    navItemId === "treatments" ||
    navItemId === "admissions" ||
    navItemId === "transfers" ||
    navItemId === "discharges" ||
    navItemId === "pricing"
  ) {
    return navItemId === "todays-visits" ? "visits" : navItemId;
  }
  return "dashboard";
}

export function isOccupied(bed: InpatientBed): boolean {
  return Boolean(bed.patientUuid) || bed.status === "OCCUPIED";
}

export function bedStatusLabel(bed: InpatientBed): "Occupied" | "Available" {
  return isOccupied(bed) ? "Occupied" : "Available";
}

export function displayBedNumber(bedNumber: string): string {
  const trimmed = (bedNumber || "").trim();
  if (!trimmed) {
    return "Bed";
  }
  if (/^bed\b/i.test(trimmed)) {
    return trimmed.replace(/^bed\s*/i, "Bed ");
  }
  return `Bed ${trimmed}`;
}

export function locationLabel(areaName: string, bedNumber: string): string {
  return `${areaName} — ${displayBedNumber(bedNumber)}`;
}

export function availableBeds(
  areas: InpatientArea[],
  excludeBedUuid?: string,
): Array<{ area: InpatientArea; bed: InpatientBed }> {
  return areas.flatMap((area) =>
    area.beds
      .filter((bed) => bed.status === "AVAILABLE" && bed.bedUuid !== excludeBedUuid)
      .map((bed) => ({ area, bed })),
  );
}

export function staffBedConflictMessage(reason: unknown): string | null {
  if (!(reason instanceof PatientAccountRequestError)) {
    return null;
  }
  if (
    reason.code === "bed_occupied" ||
    reason.code === "openmrs_conflict" ||
    /just been assigned/i.test(reason.message)
  ) {
    return "This bed has just been assigned to another patient. Please choose another bed.";
  }
  return null;
}

export function wardRequestError(reason: unknown, fallback: string): string {
  return (
    staffBedConflictMessage(reason) ||
    (reason instanceof PatientAccountRequestError ? reason.message : fallback)
  );
}

export {
  mergeNursingDayPatients,
  type NursingDayPatient,
  type NursingDayStatus,
} from "./nursingDayPatients";
