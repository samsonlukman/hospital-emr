import type { InpatientAwaiting, InpatientBed } from "../../types/inpatient.ts";
import type { DoctorQueueRow } from "../../types/index.ts";

function bedLabel(bedNumber: string): string {
  const trimmed = (bedNumber || "").trim();
  if (!trimmed) {
    return "Bed";
  }
  if (/^bed\b/i.test(trimmed)) {
    return trimmed.replace(/^bed\s*/i, "Bed ");
  }
  return `Bed ${trimmed}`;
}

export type NursingDayStatus = "Occupied" | "Admit requested" | "Visit today";

export interface NursingDayPatient {
  key: string;
  patientUuid: string;
  name: string;
  mrn: string;
  age: string;
  sex: string;
  detail: string;
  status: NursingDayStatus;
  visitType: string;
}

export function mergeNursingDayPatients(
  occupiedPatients: Array<{ areaName: string; bed: InpatientBed }>,
  awaiting: InpatientAwaiting[],
  visits: DoctorQueueRow[],
): NursingDayPatient[] {
  const rows: NursingDayPatient[] = [];
  const seen = new Set<string>();

  for (const { areaName, bed } of occupiedPatients) {
    const patientUuid = bed.patientUuid || "";
    if (patientUuid) {
      seen.add(patientUuid);
    }
    rows.push({
      key: bed.bedUuid || patientUuid || bed.bedNumber,
      patientUuid,
      name: bed.patientName || "Patient assigned",
      mrn: bed.mrn || "—",
      age: bed.age || "—",
      sex: bed.sex || "—",
      detail: `${areaName} · ${bedLabel(bed.bedNumber)}`,
      status: "Occupied",
      visitType: "IPD",
    });
  }

  for (const row of awaiting) {
    if (seen.has(row.patientUuid)) {
      continue;
    }
    seen.add(row.patientUuid);
    rows.push({
      key: row.patientUuid,
      patientUuid: row.patientUuid,
      name: row.patientName,
      mrn: row.mrn,
      age: row.age,
      sex: row.sex,
      detail: "Waiting for a bed",
      status: "Admit requested",
      visitType: "IPD",
    });
  }

  for (const visit of visits) {
    if (!visit.patientUuid || seen.has(visit.patientUuid)) {
      continue;
    }
    seen.add(visit.patientUuid);
    rows.push({
      key: visit.visitUuid || visit.patientUuid,
      patientUuid: visit.patientUuid,
      name: visit.patientName,
      mrn: visit.mrn,
      age: "—",
      sex: "—",
      detail: visit.time && visit.time !== "—" ? visit.time : "Visit today",
      status: "Visit today",
      visitType: visit.visitType,
    });
  }

  return rows;
}
