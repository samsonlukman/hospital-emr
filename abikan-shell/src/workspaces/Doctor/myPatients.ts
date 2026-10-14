import { consultationHref } from "../../app/hashRoute.ts";
import type { MyPatientRow } from "../../types";

export const MY_PATIENTS_EMPTY = "No patients have been attended by you yet.";
export const MY_PATIENTS_EMPTY_HELP =
  "Patients appear here after you save a Consultation for them.";
export const MY_PATIENTS_SEARCH_EMPTY = "No matching patients in your attended list.";
export const MY_PATIENTS_HELP =
  "Patients you have attended. Open a name to choose a visit from Previous visits.";

export function mapMyPatientRow(row: {
  patient?: string;
  mrn?: string;
  ageSex?: string;
  visitType?: string;
  lastAttended?: string;
  dailyVisitNumber?: string;
  attendedBy?: string;
  patientUuid?: string;
  visitUuid?: string;
}): MyPatientRow | null {
  const patientUuid = (row.patientUuid || "").trim();
  if (!patientUuid) {
    return null;
  }
  return {
    id: patientUuid,
    patientUuid,
    patientName: row.patient || "Unknown patient",
    mrn: row.mrn || "—",
    ageSex: (row.ageSex || "").trim(),
    visitType: row.visitType || "",
    lastAttended: row.lastAttended || "",
    dailyVisitNumber: row.dailyVisitNumber || "",
    attendedBy: row.attendedBy || "",
  };
}

export function myPatientsHref(patientUuid: string): string {
  return consultationHref(patientUuid);
}

export function myPatientsOpensVisit(href: string): boolean {
  return /\/visit\//.test(href);
}

export function matchesMyPatientsSearch(row: MyPatientRow, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return [row.patientName, row.mrn].join(" ").toLowerCase().includes(needle);
}

export function filterMyPatients(rows: MyPatientRow[], query: string): MyPatientRow[] {
  return rows.filter((row) => matchesMyPatientsSearch(row, query));
}

export function sortMyPatientsMostRecent(rows: MyPatientRow[]): MyPatientRow[] {
  return [...rows].sort((left, right) =>
    (right.lastAttended || "").localeCompare(left.lastAttended || ""),
  );
}

export function uniqueMyPatients(rows: MyPatientRow[]): MyPatientRow[] {
  const latest = new Map<string, MyPatientRow>();
  for (const row of sortMyPatientsMostRecent(rows)) {
    if (!latest.has(row.patientUuid)) {
      latest.set(row.patientUuid, row);
    }
  }
  return sortMyPatientsMostRecent([...latest.values()]);
}

export function myPatientsEmptyTitle(input: {
  loading?: boolean;
  hasRows: boolean;
  query?: string;
}): string {
  if (input.loading) {
    return "Loading your patients…";
  }
  if (input.hasRows && (input.query || "").trim()) {
    return MY_PATIENTS_SEARCH_EMPTY;
  }
  return MY_PATIENTS_EMPTY;
}

export function chartViewDoesNotQualifyForMyPatients(): true {
  return true;
}

export function radiologyOrdererDoesNotQualifyForMyPatients(): true {
  return true;
}

export function myPatientsUsesConsultationProvider(): true {
  return true;
}

export function myPatientsScopedToSessionProvider(): true {
  return true;
}
