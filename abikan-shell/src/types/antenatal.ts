import type { PatientAccountMoney } from "./patientAccount";

export type AncPregnancyStatus = "active" | "completed" | "transferred";

export type AncPaymentStatus = "UNPAID" | "PAID" | string | null;

export interface AncActor {
  uuid: string;
  username: string;
  display: string;
}

/** Pregnancy card fields stored on an ANC episode. */
export interface AncPregnancyCardFields {
  gravida?: number | string | null;
  para?: number | string | null;
  abortions?: number | string | null;
  livingChildren?: number | string | null;
  previousPregnancyHistory?: string | null;
  lmp?: string | null;
  edd?: string | null;
  gestationalAgeWeeks?: number | string | null;
  previousCaesarean?: boolean | string | null;
  significantObstetricHistory?: string | null;
  bloodGroup?: string | null;
  genotype?: string | null;
  occupation?: string | null;
  nextOfKin?: string | null;
  nextOfKinPhone?: string | null;
  bookingDate?: string | null;
  gestationalAgeAtBooking?: number | string | null;
  heightCm?: number | string | null;
  notes?: string | null;
}

/** Per-visit ANC assessment fields. */
export interface AncVisitFields {
  visitDate?: string | null;
  gestationalAgeWeeks?: number | string | null;
  weightKg?: number | string | null;
  systolic?: number | string | null;
  diastolic?: number | string | null;
  pulse?: number | string | null;
  temperatureC?: number | string | null;
  fundalHeightCm?: number | string | null;
  fetalHeartRate?: number | string | null;
  presentation?: string | null;
  urinalysis?: string | null;
  laboratoryFindings?: string | null;
  ultrasoundFindings?: string | null;
  supplements?: string | null;
  vaccinations?: string | null;
  keyFindings?: string | null;
  treatment?: string | null;
  nextAppointment?: string | null;
  clinician?: string | null;
}

export interface AncVisitRecord extends AncVisitFields {
  visitId: string;
  pregnancyId: string;
  patientUuid: string;
  openmrsVisitUuid?: string;
  createdAt: string;
  createdBy: AncActor;
}

export interface AncPregnancy {
  pregnancyId: string;
  patientUuid: string;
  status: AncPregnancyStatus;
  createdAt: string;
  completedAt?: string;
  createdBy: AncActor;
  card: AncPregnancyCardFields;
  visitCount: number;
  latestVisit: AncVisitRecord | null;
  visits: AncVisitRecord[];
  /** Fee validity for this pregnancy card. */
  feePeriodId?: string;
  feePeriodStartedAt?: string;
  expiresAt?: string;
  expiresAtLabel?: string;
  cardEnabled?: boolean;
  cardExpired?: boolean;
  validityDays?: number;
}

export interface AncPatientSummary {
  status: "ok" | "error";
  hasAnc: boolean;
  /** True when the patient has an active antenatal pregnancy (enrolled). */
  enrolled: boolean;
  /** True when the active ANC card is within its paid/created validity year. */
  cardEnabled?: boolean;
  cardExpired?: boolean;
  expiresAt?: string;
  expiresAtLabel?: string;
  activePregnancy: AncPregnancy | null;
  pregnancies: AncPregnancy[];
  defaultFeeAmount: number;
  fee?: AncChargePayload | null;
  canCreateFee?: boolean;
  feeAlreadyRegistered?: boolean;
  message?: string | null;
  code?: string;
}

export interface AncCardListRow {
  patientUuid: string;
  pregnancyId: string;
  name: string;
  hospitalNumber: string;
  status: AncPregnancyStatus;
  enrolledAt: string;
  enrolledAtLabel: string;
  cardEnabled?: boolean;
  cardExpired?: boolean;
  expiresAt?: string;
  expiresAtLabel?: string;
}

export interface AncCardListPayload {
  status: "ok" | "error";
  q: string;
  limit: number;
  startIndex: number;
  total: number;
  hasMore: boolean;
  patients: AncCardListRow[];
  message?: string;
  code?: string;
}

export interface AncPregnancyResponse {
  status: "ok" | "error";
  pregnancy: AncPregnancy;
  created?: boolean;
  code?: string;
  message?: string | null;
}

export interface AncVisitResponse {
  status: "ok" | "error";
  visit: AncVisitRecord;
  pregnancy?: AncPregnancy;
  message?: string | null;
  code?: string;
}

export interface AncChargePayload {
  status: "ok" | "error";
  hasCharge: boolean;
  pregnancyId: string;
  patientUuid: string;
  feeName: string;
  feeAmount: PatientAccountMoney;
  defaultAmount: number;
  paymentStatus: AncPaymentStatus;
  canCreate: boolean;
  alreadyRegistered?: boolean;
  saleName?: string;
  recordedBy?: string;
  alreadyCreated?: boolean;
  feePeriodId?: string;
  cardEnabled?: boolean;
  cardExpired?: boolean;
  expiresAt?: string;
  expiresAtLabel?: string;
  validityDays?: number;
  message?: string | null;
  code?: string;
}

export interface AncEnrollResponse {
  status: "ok" | "error";
  created?: boolean;
  pregnancy: AncPregnancy;
  summary?: AncPatientSummary;
  message?: string | null;
  code?: string;
}

export type AncPregnancyWriteBody = AncPregnancyCardFields & {
  startNew?: boolean;
  completeExisting?: boolean;
  status?: AncPregnancyStatus;
  card?: AncPregnancyCardFields;
};

export type AncVisitWriteBody = AncVisitFields & {
  pregnancyId?: string;
  openmrsVisitUuid?: string;
  visitUuid?: string;
  visit?: AncVisitFields;
};
