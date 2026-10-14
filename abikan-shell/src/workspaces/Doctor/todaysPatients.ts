import type { DoctorQueueRow } from "../../types";

const INCLUDED = new Set(["opd", "special opd", "follow up", "anc"]);
const EXCLUDED = new Set(["ipd", "emergency"]);

export function isClinicalTodayVisitType(name: string): boolean {
  const key = name.trim().toLowerCase();
  if (!key || EXCLUDED.has(key)) {
    return false;
  }
  return INCLUDED.has(key);
}

export function focusPatientSearch(): void {
  document.getElementById("global-patient-search")?.focus();
}

export function mapTodaysPatientRow(row: {
  patient?: string;
  mrn?: string;
  visitType?: string;
  time?: string;
  visitStart?: string;
  status?: string;
  dailyVisitNumber?: string;
  patientUuid?: string;
  visitUuid?: string;
}): DoctorQueueRow | null {
  const patientUuid = row.patientUuid || "";
  const visitUuid = row.visitUuid || "";
  if (!patientUuid || !visitUuid) {
    return null;
  }
  return {
    id: visitUuid,
    patientUuid,
    visitUuid,
    patientName: row.patient || "Unknown patient",
    mrn: row.mrn || "—",
    visitType: row.visitType || "Visit",
    time: row.time || "—",
    status: row.status || "Open",
    dailyVisitNumber: row.dailyVisitNumber || "",
    visitStart: row.visitStart || "",
  };
}

function visitRank(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : -1;
}

/** Newest visit first. Arrival time wins, then the day's visit number. */
export function latestPatientsFirst(rows: DoctorQueueRow[]): DoctorQueueRow[] {
  return [...rows].sort((left, right) => {
    const byStart = (right.visitStart || "").localeCompare(left.visitStart || "");
    if (byStart !== 0) {
      return byStart;
    }
    const byNumber = visitRank(right.dailyVisitNumber) - visitRank(left.dailyVisitNumber);
    if (byNumber !== 0) {
      return byNumber;
    }
    return (right.time || "").localeCompare(left.time || "");
  });
}
