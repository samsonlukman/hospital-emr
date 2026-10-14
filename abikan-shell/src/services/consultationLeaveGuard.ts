import {
  readConsultationPatientUuid,
  readConsultationVisitUuid,
  type ShellRoute,
} from "../app/hashRoute";

const LEAVE_MESSAGE = "You have unsaved clinical information. Leave without saving?";

let dirty = false;
let consultationHash = "";

function consultationIdentity(rawHash: string): string {
  return `${readConsultationPatientUuid(rawHash) || ""}|${readConsultationVisitUuid(rawHash) || ""}`;
}

export function setConsultationLeaveGuard(next: { dirty: boolean; hash: string }): void {
  dirty = next.dirty;
  consultationHash = next.hash;
}

export function allowConsultationLeave(nextRoute: ShellRoute): boolean {
  if (!dirty) {
    return true;
  }
  if (
    nextRoute === "consultation" &&
    consultationHash &&
    consultationIdentity(window.location.hash) === consultationIdentity(consultationHash)
  ) {
    return true;
  }
  const confirmed = window.confirm(LEAVE_MESSAGE);
  if (confirmed) {
    dirty = false;
    return true;
  }
  if (consultationHash && window.location.hash !== consultationHash) {
    window.location.hash = consultationHash;
  }
  return false;
}

export function confirmLeaveConsultation(): boolean {
  if (!dirty) {
    return true;
  }
  const confirmed = window.confirm(LEAVE_MESSAGE);
  if (confirmed) {
    dirty = false;
  }
  return confirmed;
}
