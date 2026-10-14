import type { PatientAccountMoney } from "./patientAccount";

export type RadiologyPaymentStatus = "UNPAID" | "PARTIALLY PAID" | "PAID";

export interface RadiologyExaminationCharge {
  orderUuid: string;
  orderNumber: string;
  examinationName: string;
  visitUuid: string;
  encounterUuid: string;
  feeName: string;
  feeAmount: PatientAccountMoney;
  paymentStatus: RadiologyPaymentStatus;
  billingStatus?: "Ordered" | "Price pending" | "Unpaid" | "Partially paid" | "Paid";
  hasCharge: boolean;
  outstanding?: PatientAccountMoney;
  tax?: PatientAccountMoney;
}

export interface RadiologyChargePayload {
  status: "ok" | "error";
  patient: { uuid: string; name: string; mrn: string };
  examinations: RadiologyExaminationCharge[];
  feeAmount: PatientAccountMoney;
  paymentStatus: RadiologyPaymentStatus;
  hasCharge: boolean;
  canCreateCharge: boolean;
  blockReason: string | null;
  partnerFound?: boolean;
  alreadyCreated?: boolean;
  recordedBy?: string;
  outstanding?: PatientAccountMoney;
  message?: string | null;
  code?: string;
}

export type RadiologyWorklistReportStatus = "Report pending" | "Report available";

export interface RadiologyWorklistRow {
  uuid: string;
  orderNumber: string;
  investigation: string;
  conceptUuid: string;
  category: string;
  patientUuid: string;
  patientName: string;
  mrn: string;
  visitUuid: string;
  encounterUuid: string;
  encounterTypeUuid?: string;
  visitType: string;
  dailyVisitNumber: string;
  ordered: string;
  urgency: string;
  comment: string;
  clinicalIndication?: string;
  requestSource?: "doctor_order" | "radiology_direct" | "external_referral" | string;
  requestSourceLabel?: string;
  patientType?: "registered" | "external" | string;
  patientTypeLabel?: string;
  buyerPhone?: string;
  buyerSex?: string;
  buyerDob?: string;
  buyerAddress?: string;
  referrer?: string;
  studyId?: string;
  isExternal?: boolean;
  linkedPatientUuid?: string;
  linkedAt?: string;
  linkedBy?: string;
  reportText?: string;
  reportedBy?: string;
  reportedAt?: string;
  provider: string;
  hasReport: boolean;
  reportStatus: RadiologyWorklistReportStatus;
  hasCharge: boolean;
  paymentStatus: RadiologyPaymentStatus;
  billingStatus: "Price pending" | "Unpaid" | "Partially paid" | "Paid";
  feeFormatted?: string;
}

export interface RadiologyWorklistPayload {
  status: "ok";
  pending: RadiologyWorklistRow[];
  reported: RadiologyWorklistRow[];
  orders: RadiologyWorklistRow[];
}

export interface RadiologyHistoryPayload {
  status: "ok" | "error";
  items: RadiologyWorklistRow[];
  total: number;
  offset: number;
  limit: number;
  message?: string;
  code?: string;
}

export interface RadiologyOrderCreateResult {
  status: "ok";
  encounterUuid?: string;
  visitUuid?: string;
  orders?: Array<{ uuid: string; orderNumber?: string; testName?: string; visitUuid?: string }>;
  requestSource?: string;
  requestSourceLabel?: string;
  message?: string;
}

export interface RadiologyExternalStudyPayload extends RadiologyWorklistRow {
  status: "ok";
  message?: string;
  alreadyCreated?: boolean;
  alreadyLinked?: boolean;
}

export interface RadiologyHistoryQuery {
  q?: string;
  from?: string;
  to?: string;
  requestSource?: string;
  patientType?: string;
  report?: string;
  category?: string;
  offset?: number;
  limit?: number;
}
