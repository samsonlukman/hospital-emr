import type { InpatientStay, InpatientVitalReading, MarPayload, NursingNote } from "../../types/inpatient";

export interface NursingTask {
  id: string;
  title: string;
  detail: string;
  action: string;
  href: string;
}

export function stayNeedsBed(stay: InpatientStay | null): boolean {
  if (!stay) {
    return false;
  }
  return Boolean(stay.awaiting) && !stay.assignment;
}

export function stayIsOccupied(stay: InpatientStay | null): boolean {
  return Boolean(stay?.assignment);
}

export function vitalsRecordedOnAdmission(
  readings: InpatientVitalReading[],
  admissionEncounterUuid: string,
): boolean {
  if (!admissionEncounterUuid) {
    return false;
  }
  return readings.some((row) => row.encounterUuid === admissionEncounterUuid);
}

export function notesOnAdmission(notes: NursingNote[], admissionEncounterUuid: string): number {
  if (!admissionEncounterUuid) {
    return 0;
  }
  return notes.filter((row) => row.admissionEncounterUuid === admissionEncounterUuid).length;
}

export function marAttention(payload: MarPayload | null): {
  eligible: number;
  outsideWindow: number;
} {
  if (!payload?.activeAdmission) {
    return { eligible: 0, outsideWindow: 0 };
  }
  let eligible = 0;
  let outsideWindow = 0;
  for (const order of payload.orders) {
    if (order.asNeeded) {
      continue;
    }
    for (const slot of order.slots) {
      if (slot.status !== "SCHEDULED") {
        continue;
      }
      if (slot.timing.canAdministerNormally) {
        eligible += 1;
      } else if (slot.timing.status === "early" || slot.timing.status === "late") {
        outsideWindow += 1;
      }
    }
  }
  return { eligible, outsideWindow };
}

export function nursingTasksFromState(input: {
  stay: InpatientStay | null;
  admissionEncounterUuid: string;
  vitals: InpatientVitalReading[];
  notes: NursingNote[];
  mar: MarPayload | null;
}): NursingTask[] {
  const tasks: NursingTask[] = [];
  if (stayNeedsBed(input.stay)) {
    tasks.push({
      id: "assign-bed",
      title: "Assign a bed",
      detail: "The doctor has asked to admit this patient and no bed is assigned yet.",
      action: "Open Admission and choose a ward bed.",
      href: "#admission",
    });
  }
  if (!stayIsOccupied(input.stay)) {
    return tasks;
  }
  if (!vitalsRecordedOnAdmission(input.vitals, input.admissionEncounterUuid)) {
    tasks.push({
      id: "record-vitals",
      title: "Record vitals",
      detail: "No vitals have been recorded on this admission yet.",
      action: "Open Vitals and save the measurements you took.",
      href: "#vitals",
    });
  }
  const mar = marAttention(input.mar);
  if (mar.eligible > 0) {
    tasks.push({
      id: "administer-mar",
      title: "Administer scheduled medication",
      detail:
        mar.eligible === 1
          ? "One scheduled dose is due now."
          : `${mar.eligible} scheduled doses are due now.`,
      action: "Open Medication and record the dose.",
      href: "#mar",
    });
  }
  if (mar.outsideWindow > 0) {
    tasks.push({
      id: "review-mar-window",
      title: "Review a dose outside the scheduled window",
      detail: "A scheduled dose is early or late. It still needs a recorded outcome.",
      action: "Open Medication and use Administer outside scheduled window.",
      href: "#mar",
    });
  }
  if (notesOnAdmission(input.notes, input.admissionEncounterUuid) === 0) {
    tasks.push({
      id: "write-note",
      title: "Write a nursing note",
      detail: "No nursing note has been recorded on this admission yet.",
      action: "Open Notes and save the observation.",
      href: "#notes",
    });
  }
  return tasks;
}
