import type { PatientAccountMoney } from "./patientAccount";
import type {
  LaboratoryBoardOrder,
  LaboratoryOrderCreateResult,
  LaboratoryPatientType,
  LaboratoryRequestSource,
} from "./laboratoryCatalogue";

export type LaboratoryPaymentStatus = "UNPAID" | "PAID" | "PARTIALLY PAID";

export interface LaboratoryTestCharge {
  orderUuid: string;
  orderNumber: string;
  testName: string;
  visitUuid: string;
  encounterUuid: string;
  feeName: string;
  feeAmount: PatientAccountMoney;
  paymentStatus: LaboratoryPaymentStatus;
  hasCharge: boolean;
  requestKey?: string;
  outstanding?: PatientAccountMoney;
  tax?: PatientAccountMoney;
}

export interface LaboratoryChargePayload {
  status: "ok" | "error";
  patient: { uuid: string; name: string; mrn: string };
  tests: LaboratoryTestCharge[];
  feeAmount: PatientAccountMoney;
  paymentStatus: LaboratoryPaymentStatus;
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

export interface LaboratoryExternalPatientSummary {
  externalId: string;
  patientName: string;
  buyerPhone?: string;
  buyerSex?: string;
  buyerDob?: string;
  buyerAddress?: string;
  requestSource?: LaboratoryRequestSource;
  requestSourceLabel?: string;
  referrer?: string;
  openmrsUuid?: string;
  linkedPatientUuid?: string;
  linkedAt?: string;
  linkedBy?: string;
  patientType?: LaboratoryPatientType;
  isExternal?: boolean;
}

export interface LaboratoryExternalPatientPayload extends LaboratoryExternalPatientSummary {
  status: "ok" | "error";
  orders?: LaboratoryBoardOrder[];
  message?: string;
  alreadyLinked?: boolean;
  code?: string;
}

export interface LaboratoryExternalOrderPayload extends LaboratoryOrderCreateResult {
  externalId?: string;
  patientName?: string;
  alreadyCreated?: boolean;
}

export interface LaboratoryExternalPatientSearchPayload {
  status: "ok" | "error";
  items: LaboratoryExternalPatientSummary[];
  message?: string;
  code?: string;
}

export interface LaboratoryLinkedExternalPayload {
  status: "ok" | "error";
  items: LaboratoryBoardOrder[];
  message?: string;
  code?: string;
}
