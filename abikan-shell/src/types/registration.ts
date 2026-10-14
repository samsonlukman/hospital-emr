import type { HospitalFamily } from "./hospitalFamily";
import type { FamilyRegistrationMode } from "./hospitalFamily";
import type { PatientAccountMoney } from "./patientAccount";

export type RegistrationCardType = "individual" | "family";

export type RegistrationPaymentStatus = "UNPAID" | "PAID";

export interface RegistrationVisitInfo {
  uuid: string;
  startDatetime: string;
  open: boolean;
  visitType: string;
  location: string;
}

export interface RegistrationCardOption {
  id: RegistrationCardType;
  label: string;
  amount: PatientAccountMoney;
}

export interface RegistrationChargePayload {
  status: "ok" | "error";
  patient: { uuid: string; name: string; mrn: string };
  visit: RegistrationVisitInfo | null;
  cardType?: RegistrationCardType;
  cards?: RegistrationCardOption[];
  feeName: string;
  feeAmount: PatientAccountMoney;
  paymentStatus: RegistrationPaymentStatus;
  hasCharge: boolean;
  canCreateCharge: boolean;
  cardAlreadyRegistered?: boolean;
  familyCardIssued?: boolean;
  family?: HospitalFamily | null;
  admissionActive?: boolean;
  blockReason: string | null;
  partnerFound?: boolean;
  alreadyCreated?: boolean;
  recordedBy?: string;
  tax?: PatientAccountMoney;
  outstanding?: PatientAccountMoney;
  message?: string | null;
  code?: string;
}

export interface RegistrationFieldOption {
  uuid: string;
  name: string;
  label: string;
  searchable?: boolean;
}

export interface RegistrationAddressField {
  name: string;
  label: string;
}

export interface RegistrationLocationOption {
  uuid: string;
  name: string;
}

export interface RegistrationVisitTypeOption {
  uuid: string;
  name: string;
  label: string;
  helper?: string;
  bucket: string;
  locations: RegistrationLocationOption[];
  defaultLocationUuid: string;
}

export interface RegistrationIdentifierMeta {
  uuid: string;
  name: string;
  required: boolean;
  prefix: string;
  sourceName: string;
  note: string;
  otherTypes: Array<{ uuid: string; name: string; required: boolean }>;
}

export interface RegistrationMetadata {
  status: "ok" | "error";
  identifier: RegistrationIdentifierMeta;
  personAttributes: RegistrationFieldOption[];
  addressFields: RegistrationAddressField[];
  relationshipTypes: Array<{ uuid: string; label: string; aIsToB: string; bIsToA: string }>;
  visitTypes: RegistrationVisitTypeOption[];
  locations: RegistrationLocationOption[];
  cards: RegistrationCardOption[];
  queueAvailable: boolean;
  duplicateCheck: string;
  message?: string;
  code?: string;
}

export interface RegistrationMatch {
  uuid: string;
  display: string;
  name: string;
  mrn: string;
  age: string;
  sex: string;
}

export interface RegistrationPatientDraft {
  givenName: string;
  middleName: string;
  familyName: string;
  gender: "M" | "F" | "O" | "";
  birthdate: string;
  birthdateEstimated: boolean;
  age: string;
  attributes: Record<string, string>;
  address: Record<string, string>;
  otherIdentifiers: Array<{ identifierType: string; identifier: string }>;
  nextOfKin: {
    givenName: string;
    familyName: string;
    relationshipType: string;
    gender: string;
  };
  familyMode: FamilyRegistrationMode;
  familyId: string;
  householdName: string;
  familyRelationship: string;
  nhis: boolean;
}

export interface RegistrationCreateResult {
  status: "ok" | "error";
  uuid?: string;
  identifier?: string;
  display?: string;
  identifierSource?: string;
  matches?: RegistrationMatch[];
  families?: HospitalFamily[];
  family?: HospitalFamily | null;
  newCardCreated?: boolean;
  feeWillBeGenerated?: boolean;
  familyWarning?: string;
  message?: string;
  code?: string;
}

export interface RegistrationPatientProfile {
  status: "ok" | "error";
  uuid: string;
  personUuid: string;
  identifier: string;
  givenName: string;
  middleName: string;
  familyName: string;
  gender: string;
  birthdate: string;
  birthdateEstimated: boolean;
  age?: number | null;
  attributes: Record<string, string>;
  address: Record<string, string>;
  identifiers: Array<{ uuid: string; identifier: string; preferred: boolean; type: string }>;
  family?: HospitalFamily | null;
  nhis?: boolean;
  message?: string;
}

export interface RegistrationVisitContext {
  status: "ok" | "error";
  patient: { uuid: string; name: string; mrn: string };
  visit: RegistrationVisitInfo | null;
  visitTypes?: RegistrationVisitTypeOption[];
  admissionActive: boolean;
  canStartVisit: boolean;
  code?: string | null;
  message?: string | null;
}

export interface RegistrationStartedVisit {
  status: "ok" | "existing" | "error";
  created?: boolean;
  uuid: string;
  visitType: string;
  visitTypeLabel: string;
  location: string;
  locationUuid: string;
  startDatetime: string;
  dailyVisitNumber?: string;
  open: boolean;
  message?: string;
  code?: string;
}

export interface RegistrationClosedVisit {
  status: "ok" | "error";
  uuid: string;
  visitType: string;
  visitTypeLabel: string;
  location: string;
  startDatetime: string;
  stopDatetime: string;
  open: boolean;
  message?: string;
  code?: string;
}
