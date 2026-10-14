export interface NamedRef {
  uuid?: string;
  name?: string;
  display?: string;
  retired?: boolean;
}

export interface OpenmrsSession {
  authenticated: boolean;
  locale?: string;
  user?: {
    uuid?: string;
    username?: string;
    display?: string;
    roles?: NamedRef[];
    privileges?: NamedRef[];
    userProperties?: Record<string, string>;
    person?: {
      uuid?: string;
      display?: string;
    };
  };
  sessionLocation?: {
    uuid?: string;
    display?: string;
    name?: string;
  };
}

export interface OpenmrsUser {
  uuid: string;
  username: string;
  roles: NamedRef[];
  privileges: NamedRef[];
  userProperties?: Record<string, string>;
  person?: {
    display?: string;
  };
}

export interface OpenmrsLocation {
  uuid: string;
  name: string;
  display?: string;
  tags: NamedRef[];
}

export interface LoginLocationOption {
  uuid: string;
  name: string;
}

export interface WorkspaceContext {
  username: string;
  displayName: string;
  userUuid: string;
  roles: string[];
  privileges: string[];
  userProperties?: Record<string, string>;
  location: {
    uuid: string;
    name: string;
    tags: string[];
  };
}

export type RegistrationCardType = "individual" | "family";

export interface ReceptionAppointment {
  uuid: string;
  time: string;
  patientName: string;
  patientUuid: string;
  mrn: string;
  doctor: string;
  department: string;
  status: string;
}

export interface ReceptionVisit {
  uuid: string;
  time: string;
  patientName: string;
  patientUuid: string;
  mrn: string;
  visitType: string;
  status: string;
  dailyVisitNumber: string;
  startDatetime?: string;
  attendedBy?: string;
}

export interface PatientSearchHit {
  uuid: string;
  display: string;
}

export interface ReceptionRegistration {
  uuid: string;
  time: string;
  date: string;
  patientName: string;
  mrn: string;
}

export interface DoctorQueueRow {
  id: string;
  patientUuid: string;
  visitUuid: string;
  patientName: string;
  mrn: string;
  visitType: string;
  time: string;
  status: string;
  dailyVisitNumber: string;
  visitStart?: string;
}

export interface MyPatientRow {
  id: string;
  patientUuid: string;
  patientName: string;
  mrn: string;
  ageSex: string;
  visitType: string;
  lastAttended: string;
  dailyVisitNumber: string;
  attendedBy: string;
}

export interface PatientIdentity {
  uuid: string;
  name: string;
  mrn: string;
  age: string;
  sex: string;
  birthdate: string;
}

export interface PatientVisitSummary {
  uuid: string;
  start: string;
  startDate: string;
  startDatetime: string;
  stop: string | null;
  visitType: string;
  location: string;
  open: boolean;
  dailyVisitNumber: string;
  attendedBy: string;
}

export interface VitalReading {
  key: string;
  label: string;
  value: string;
  unit: string;
  recordedAt: string;
  recordedBy: string;
  recordedAtIso: string;
}

export type ClinicalMedicationStatus = "Ordered" | "Stopped" | "Expired";

export interface DrugOrderSummary {
  uuid: string;
  display: string;
  drugName?: string;
  dose?: string;
  route?: string;
  frequency?: string;
  duration?: string;
  quantity?: string;
  instructions?: string;
  administrationMode?: "HOME" | "HOSPITAL_FOLLOW_UP" | "INPATIENT";
  status?: ClinicalMedicationStatus;
  visitUuid?: string;
}

export interface WardBed {
  uuid: string;
  bedNumber: string;
  status: string;
  patientUuid?: string;
  patientName?: string;
  mrn?: string;
  sex?: string;
  age?: string;
  admitted?: string;
}

export interface WardSummary {
  uuid: string;
  name: string;
  totalBeds: number;
  occupiedBeds: number;
  availableBeds: number;
  beds: WardBed[];
}

export interface WardPatient {
  visitUuid: string;
  patientUuid: string;
  patientName: string;
  mrn: string;
  visitType: string;
  started: string;
}

export interface PatientBedAssignment {
  wardUuid: string;
  wardName: string;
  bedUuid: string;
  bedNumber: string;
  admitted?: string | null;
  sex?: string | null;
  age?: string | null;
}

export interface LabOrderSummary {
  uuid: string;
  orderNumber: string;
  testName: string;
  patientUuid: string;
  visitUuid?: string;
  patientName: string;
  mrn: string;
  age?: string;
  ordered: string;
  urgency: string;
  comment: string;
  provider: string;
  accession: string;
}

export interface LabResultSummary {
  orderUuid: string;
  accessionUuid: string;
  testName: string;
  panelName: string;
  result: string;
  unit: string;
  minNormal: string;
  maxNormal: string;
  abnormal: boolean | null;
  notes: string;
  provider: string;
  resultAt: string;
  accessionAt: string;
  mappingStatus: "unique" | "ambiguous";
  mappingMessage: string;
}

export interface RadiologyOrderSummary {
  uuid: string;
  orderNumber: string;
  investigation: string;
  conceptUuid?: string;
  visitUuid?: string;
  encounterUuid?: string;
  encounterTypeUuid?: string;
  encounterDatetime?: string;
  visitType?: string;
  dailyVisitNumber?: string;
  patientUuid: string;
  patientName: string;
  mrn: string;
  ordered: string;
  urgency: string;
  comment: string;
  clinicalIndication?: string;
  requestSource?: "doctor_order" | "radiology_direct" | string;
  requestSourceLabel?: string;
  provider: string;
  accession: string;
  billingStatus?: "Price pending" | "Unpaid" | "Partially paid" | "Paid";
  feeFormatted?: string;
}

export interface RadiologyNoteSummary {
  uuid: string;
  value: string;
  observedAt: string;
  obsDatetime?: string;
  encounterUuid: string;
  orderUuid: string;
  visitUuid: string;
  patientUuid: string;
  reportedBy: string;
}

export interface RadiologyEncounterSummary {
  uuid: string;
  display: string;
  encounterDatetime: string;
}

export type PacsQueryStatus = "ok" | "unconfigured" | "error" | "skipped";

export interface PacsStudySummary {
  studyUid: string;
  accessionNumber: string;
  started: string;
  status: string;
}

export interface PacsQueryState {
  status: PacsQueryStatus;
  message: string;
  studies: PacsStudySummary[];
}

export type PharmacyOrderStatus = "Ordered" | "Stopped" | "Dispensed";

export interface PharmacyOrderSummary {
  uuid: string;
  orderNumber: string;
  drugName: string;
  strength: string;
  dose: string;
  doseUnits: string;
  route: string;
  frequency: string;
  duration: string;
  quantity: string;
  quantityUnits: string;
  instructions: string;
  patientUuid: string;
  patientName: string;
  mrn: string;
  ordered: string;
  provider: string;
  careSetting: string;
  action: string;
  dateStopped: string;
  autoExpireDate: string;
  dispensed: boolean;
  status: PharmacyOrderStatus;
}

export interface ConditionSummary {
  uuid: string;
  display: string;
}

export interface DiagnosisRecord {
  uuid: string;
  display: string;
  order?: "PRIMARY" | "SECONDARY";
  certainty?: string;
  conceptUuid?: string;
}

export interface DiagnosisDraftItem {
  conceptUuid: string;
  conceptName: string;
  matchedName?: string;
  order: "PRIMARY" | "SECONDARY";
}

export interface EncounterSummary {
  uuid: string;
  date: string;
  time: string;
  type: string;
}

export interface AllergyRecord {
  uuid: string;
  allergen: string;
  allergenType: string;
  allergenTypeLabel: string;
  severity: string;
  reactions: string[];
  comment: string;
  display: string;
}

export type AllergyState =
  | { status: "recorded"; items: string[]; records: AllergyRecord[]; canWrite: boolean }
  | { status: "none-recorded"; canWrite?: boolean }
  | { status: "unavailable"; canWrite?: boolean };

export type AppIconName =
  | "dashboard"
  | "search"
  | "userPlus"
  | "user"
  | "users"
  | "calendar"
  | "calendarPlus"
  | "clipboardPlus"
  | "clipboardList"
  | "creditCard"
  | "receipt"
  | "chart"
  | "fileText"
  | "settings"
  | "bell"
  | "menu"
  | "logOut"
  | "naira"
  | "activity"
  | "stethoscope"
  | "bed"
  | "image"
  | "folder"
  | "flask"
  | "pill"
  | "message"
  | "phoneCall";

type NavItemBase = {
  id: string;
  label: string;
  icon: AppIconName;
};

export type NavItem =
  | (NavItemBase & { kind: "link"; href: string })
  | (NavItemBase & { kind: "action"; action: "register" | "search" })
  | (NavItemBase & { kind: "anchor"; href: string })
  | (NavItemBase & { kind: "route"; href: string })
  | (NavItemBase & { kind: "soon" });

export interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
}

export type WorkspaceId =
  | "registration-desk"
  | "doctor"
  | "nursing"
  | "coming-soon"
  | "access-denied";

export interface WorkspaceDefinition {
  id: Exclude<WorkspaceId, "coming-soon" | "access-denied">;
  label: string;
  match: (context: WorkspaceContext) => boolean;
}

export type LoadState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "error"; message: string }
  | { status: "ready"; context: WorkspaceContext; workspaceId: WorkspaceId };
