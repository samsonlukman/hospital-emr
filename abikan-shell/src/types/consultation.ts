import type { PatientAccountMoney } from "./patientAccount";

export type ConsultationPaymentStatus = "UNPAID" | "PAID";

export interface ConsultationVisitInfo {
  uuid: string;
  startDatetime: string;
  open: boolean;
  visitType: string;
  location: string;
}

export interface ConsultationEncounterInfo {
  uuid: string;
}

export interface ConsultationChargePayload {
  status: "ok" | "error";
  patient: { uuid: string; name: string; mrn: string };
  visit: ConsultationVisitInfo | null;
  encounter: ConsultationEncounterInfo | null;
  feeName: string;
  feeAmount: PatientAccountMoney;
  paymentStatus: ConsultationPaymentStatus;
  hasCharge: boolean;
  canCreateCharge: boolean;
  blockReason: string | null;
  nhis?: boolean;
  pharmacyDiscountPercent?: number;
  partnerFound?: boolean;
  alreadyCreated?: boolean;
  recordedBy?: string;
  tax?: PatientAccountMoney;
  outstanding?: PatientAccountMoney;
  message?: string | null;
  code?: string;
}
