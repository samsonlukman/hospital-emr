import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes.ts";
import { attendingDoctorName } from "../../services/openmrs/visitAttendingProvider.ts";
import type { RadiologyOrderSummary } from "../../types";
import {
  formatDailyVisitNumber,
  MISSING_DAILY_VISIT_NUMBER,
  visitNumberLabel,
} from "../../utils/dailyVisitNumber.ts";
import { doctorVisitLocationLabel } from "../Doctor/consultationVisit.ts";
import { radiologyBillingStatus, type RadiologyBillingStatus } from "./radiologyOrder.ts";

export const RADIOLOGY_SET_PRICE = "Set Price";
export const RADIOLOGY_SAVE_PRICE = "Save Price";
export const RADIOLOGY_PRICE_HELPER =
  "Amount is in Nigerian naira (NGN). Accounts collects payment. You can still write the report if unpaid.";
export const RADIOLOGY_HOME_HELP =
  "Use the worklist for pending examinations, or create a New Imaging Study when Radiology starts the request. You do not collect payment here.";
export const RADIOLOGY_WORKLIST_HELP =
  "Pending examinations that do not yet have a Radiology Report. Doctor orders and Radiology Direct studies appear here.";
export const RADIOLOGY_WORKLIST_EMPTY = "No pending Radiology examinations.";
export const RADIOLOGY_REPORTED_EMPTY = "No reported examinations match this search.";
export const RADIOLOGY_WORKLIST_SEARCH_PLACEHOLDER = "Patient, hospital number, or examination";
export const NO_RADIOLOGY_ORDERS = "No imaging studies";
export const NO_RADIOLOGY_ORDERS_HELP = "This patient has no imaging studies yet.";
export const NO_PRICE_SET = "No price set.";
export const NO_PAYMENT_RECORDED = "No payment recorded.";
export const RADIOLOGY_DIRECT_LABEL = "Radiology Direct";
export const DOCTOR_ORDER_LABEL = "Doctor Order";
export const EXTERNAL_REFERRAL_LABEL = "External Referral";
export const EXTERNAL_PATIENT_LABEL = "External Patient";
export const REGISTERED_PATIENT_LABEL = "Registered Patient";

export function radiologyRequestSourceLabel(
  source: string | undefined,
  comment?: string,
): string {
  if (source === "radiology_direct") {
    return RADIOLOGY_DIRECT_LABEL;
  }
  if (source === "external_referral") {
    return EXTERNAL_REFERRAL_LABEL;
  }
  if (source === "doctor_order") {
    return DOCTOR_ORDER_LABEL;
  }
  const text = (comment || "").trim();
  if (text.startsWith("[Radiology Direct]") || text.startsWith("Radiology Direct")) {
    return RADIOLOGY_DIRECT_LABEL;
  }
  return DOCTOR_ORDER_LABEL;
}

export function radiologyPatientTypeLabel(
  type: string | undefined,
  isExternal?: boolean,
): string {
  if (isExternal || type === "external") {
    return EXTERNAL_PATIENT_LABEL;
  }
  return REGISTERED_PATIENT_LABEL;
}

export function radiologyClinicalIndication(comment: string | undefined): string {
  const text = (comment || "").trim();
  for (const prefix of ["[Radiology Direct]", "Radiology Direct:", "Radiology Direct"]) {
    if (text.startsWith(prefix)) {
      return text.slice(prefix.length).trim().replace(/^[:\-\s]+/, "");
    }
  }
  return text;
}

const LOGIN_LIKE = /^[a-z0-9._-]+\.[a-z0-9._-]+$/i;

/** Staff-facing name only. Never show a login id. */
export function radiologyStaffName(display: string | undefined): string {
  const named = attendingDoctorName({ display });
  if (!named) {
    return "—";
  }
  if (LOGIN_LIKE.test(named) && !named.includes(" ")) {
    return "—";
  }
  return named;
}

export function radiologyVisitLabel(input: {
  dailyVisitNumber?: string;
  visitType?: string;
}): string {
  const number = visitNumberLabel(input.dailyVisitNumber);
  const type = receptionVisitTypeLabel(input.visitType);
  return [number === "—" ? "" : number, type]
    .filter((part) => part && part !== "—")
    .join(" · ") || "—";
}

/** Staff-facing daily visit number, e.g. 001. Never OPD-1. */
export function radiologyDailyVisitNumber(value: unknown): string | undefined {
  const formatted = formatDailyVisitNumber(value);
  return formatted === MISSING_DAILY_VISIT_NUMBER ? undefined : formatted;
}

export function radiologyPaymentTone(
  status: RadiologyBillingStatus,
): "info" | "success" | "warning" {
  if (status === "Paid") {
    return "success";
  }
  if (status === "Unpaid" || status === "Partially paid") {
    return "warning";
  }
  return "info";
}

export function radiologyLocationLabel(location: string | undefined): string | undefined {
  return doctorVisitLocationLabel(location);
}

export function radiologyPaymentLabel(input: {
  hasCharge?: boolean;
  paymentStatus?: string;
}): RadiologyBillingStatus {
  return radiologyBillingStatus(input);
}

export function radiologyShowsUnimplementedImagesUi(): false {
  return false;
}

export function radiologyStaffFacingCopyHasImagesPlaceholder(): boolean {
  return [
    RADIOLOGY_HOME_HELP,
    RADIOLOGY_WORKLIST_HELP,
    RADIOLOGY_WORKLIST_EMPTY,
    RADIOLOGY_REPORTED_EMPTY,
    NO_RADIOLOGY_ORDERS,
    NO_RADIOLOGY_ORDERS_HELP,
    NO_PRICE_SET,
    NO_PAYMENT_RECORDED,
  ].some((text) => /images\s*—\s*coming soon|open images|view images/i.test(text));
}

export function radiologyOrderIdentity(order: Pick<RadiologyOrderSummary, "uuid" | "patientUuid" | "visitUuid">): {
  patientUuid: string;
  visitUuid: string;
  orderUuid: string;
} | null {
  const patientUuid = (order.patientUuid || "").trim();
  const visitUuid = (order.visitUuid || "").trim();
  const orderUuid = (order.uuid || "").trim();
  if (!patientUuid || !visitUuid || !orderUuid) {
    return null;
  }
  return { patientUuid, visitUuid, orderUuid };
}
