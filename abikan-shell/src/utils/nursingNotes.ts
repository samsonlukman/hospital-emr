import type { NursingNote } from "../types/inpatient";

export function notesForAdmission(
  notes: NursingNote[],
  admissionEncounterUuid: string,
): NursingNote[] {
  if (!admissionEncounterUuid) {
    return [];
  }
  return notes.filter((note) => note.admissionEncounterUuid === admissionEncounterUuid);
}

export function canCreateNursingNote(
  allowed: boolean,
  activeAdmissionEncounterUuid: string,
): boolean {
  return allowed && Boolean(activeAdmissionEncounterUuid.trim());
}

export function canSubmitNursingNote(content: string, saving: boolean): boolean {
  return Boolean(content.trim()) && !saving;
}

export function nursingNoteRequestBody(note: string, requestId: string) {
  return { note, requestId };
}
