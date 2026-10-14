export type FamilyFeeStatus = "pending" | "billed";

export type FamilyRegistrationMode = "none" | "existing" | "new";

export interface HospitalFamilyMember {
  patientUuid: string;
  relationship: string;
  name: string;
  identifier: string;
  linkedAt?: string;
  linkedBy?: string;
  age?: number | null;
  sex?: string;
}

export interface HospitalFamily {
  familyId: string;
  familyName: string;
  cardNumber: string;
  memberCount: number;
  feeStatus: FamilyFeeStatus;
  feePatientUuid: string;
  createdAt?: string;
  createdBy?: string;
  relationship?: string;
  isFeePatient?: boolean;
  members?: HospitalFamilyMember[];
  transferred?: boolean;
}

export interface HospitalFamilyListPayload {
  status: "ok" | "error";
  families: HospitalFamily[];
  query?: string;
  message?: string;
}

export interface HospitalFamilyDetailPayload {
  status: "ok" | "error";
  family: HospitalFamily | null;
  message?: string;
  code?: string;
}
