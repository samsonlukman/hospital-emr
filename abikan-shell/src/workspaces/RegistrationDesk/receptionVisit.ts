import type { RegistrationChargePayload, RegistrationStartedVisit } from "../../types/registration";

export const VISIT_ALREADY_OPEN_CODE = "visit_already_open";
export const ADMISSION_IN_PROGRESS_CODE = "admission_in_progress";
export const CARD_ALREADY_REGISTERED_CODE = "card_already_registered";

export const VISIT_ALREADY_OPEN_MESSAGE =
  "Patient already has an open visit. Continue with the existing visit.";
export const ADMISSION_IN_PROGRESS_MESSAGE =
  "This patient is already admitted. Continue with the existing admission visit.";
export const CONTINUE_EXISTING_VISIT_LABEL = "Continue with existing visit";
export const CREATE_VISIT_NO_CARD_COPY =
  "This patient is already registered. No hospital card fee is needed to start a visit.";

export function createVisitShowsCardFee(): boolean {
  return false;
}

export function isExistingVisitCode(code: string | undefined): boolean {
  return code === VISIT_ALREADY_OPEN_CODE || code === ADMISSION_IN_PROGRESS_CODE;
}

export function shouldOfferStartVisit(input: {
  openVisit?: { uuid?: string } | null;
  admissionActive?: boolean;
}): boolean {
  return !input.openVisit?.uuid && !input.admissionActive;
}

export function shouldOfferCardFee(charge: Pick<
  RegistrationChargePayload,
  "canCreateCharge" | "cardAlreadyRegistered"
> | null): boolean {
  return Boolean(charge?.canCreateCharge) && !charge?.cardAlreadyRegistered;
}

export function shouldShowCardFeeCard(charge: Pick<
  RegistrationChargePayload,
  "canCreateCharge" | "hasCharge" | "cardAlreadyRegistered"
> | null): boolean {
  if (!charge) {
    return false;
  }
  if (charge.cardAlreadyRegistered) {
    return false;
  }
  return charge.canCreateCharge || charge.hasCharge;
}

export function existingVisitNotice(input: {
  openVisit?: { uuid?: string } | null;
  admissionActive?: boolean;
}): string | null {
  if (input.admissionActive) {
    return ADMISSION_IN_PROGRESS_MESSAGE;
  }
  if (input.openVisit?.uuid) {
    return VISIT_ALREADY_OPEN_MESSAGE;
  }
  return null;
}

export function readStartVisitResult(body: RegistrationStartedVisit): {
  kind: "created" | "existing";
  visit: RegistrationStartedVisit;
  message: string;
} {
  if (body.status === "existing" || isExistingVisitCode(body.code) || body.created === false) {
    return {
      kind: "existing",
      visit: body,
      message:
        body.message ||
        (body.code === ADMISSION_IN_PROGRESS_CODE
          ? ADMISSION_IN_PROGRESS_MESSAGE
          : VISIT_ALREADY_OPEN_MESSAGE),
    };
  }
  return {
    kind: "created",
    visit: body,
    message: "Visit successfully created.",
  };
}

export function patientOwnsVisit(
  patientUuid: string,
  visitPatientUuid: string | null | undefined,
): boolean {
  return Boolean(patientUuid) && patientUuid === (visitPatientUuid || "");
}

export const CLOSE_VISIT_LABEL = "Close Visit";
export const CLOSING_VISIT_LABEL = "Closing visit...";
export const CLOSE_VISIT_CONFIRM_TITLE = "Close this outpatient visit?";
export const CLOSE_VISIT_CONFIRM_COPY =
  "Closing the visit will mark the patient's current outpatient visit as completed. Clinical records already recorded on this visit will remain unchanged.";
export const VISIT_CLOSED_SUCCESS_MESSAGE = "Visit closed successfully.";
export const VISIT_ALREADY_CLOSED_CODE = "visit_already_closed";
export const CANNOT_CLOSE_ADMISSION_CODE = "cannot_close_admission";

export type OutpatientVisitStatusKind = "awaiting" | "attended" | "closed";

export interface OutpatientVisitStatus {
  kind: OutpatientVisitStatusKind;
  badge: string;
  label: string;
}

const MISSING_DOCTOR = "—";

export function isInpatientVisitType(visitType: string | undefined): boolean {
  return (visitType || "").trim().toUpperCase() === "IPD";
}

export function canCloseOutpatientVisit(input: {
  visit?: { uuid?: string; visitType?: string; open?: boolean } | null;
  admissionActive?: boolean;
  patientUuid?: string;
  visitPatientUuid?: string | null;
}): boolean {
  if (!input.visit?.uuid) {
    return false;
  }
  if (input.visit.open === false) {
    return false;
  }
  if (input.admissionActive || isInpatientVisitType(input.visit.visitType)) {
    return false;
  }
  if (input.patientUuid && !patientOwnsVisit(input.patientUuid, input.visitPatientUuid ?? input.patientUuid)) {
    return false;
  }
  return true;
}

export function outpatientVisitStatus(input: {
  open?: boolean;
  stop?: string | null;
  attendedBy?: string;
}): OutpatientVisitStatus {
  const closed = input.open === false || Boolean(input.stop);
  if (closed) {
    return { kind: "closed", badge: "Closed", label: "Closed" };
  }
  const doctor = (input.attendedBy || "").trim();
  if (doctor && doctor !== MISSING_DOCTOR) {
    return {
      kind: "attended",
      badge: "Active — Attended",
      label: `Active — Attended by Dr. ${doctor}`,
    };
  }
  return {
    kind: "awaiting",
    badge: "Active — Awaiting consultation",
    label: "Active — Awaiting consultation",
  };
}
