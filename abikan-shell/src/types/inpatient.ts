export interface InpatientBed {
  bedUuid: string;
  bedId: number | null;
  bedNumber: string;
  status: "AVAILABLE" | "OCCUPIED" | string;
  areaName: string;
  areaUuid: string;
  patientUuid?: string | null;
  patientName?: string | null;
  mrn?: string | null;
  sex?: string | null;
  age?: string | null;
  admitted?: string | null;
}

export interface InpatientArea {
  uuid: string;
  name: string;
  totalBeds: number;
  occupiedBeds: number;
  availableBeds: number;
  beds: InpatientBed[];
}

export interface InpatientAwaiting {
  patientUuid: string;
  patientName: string;
  mrn: string;
  sex: string;
  age: string;
  requested: string;
  visitUuid: string;
}

export interface InpatientBoard {
  status: string;
  areas: InpatientArea[];
  totalBeds: number;
  occupiedBeds: number;
  availableBeds: number;
  awaiting: InpatientAwaiting[];
  message?: string | null;
}

export interface InpatientStay {
  status: string;
  message?: string;
  patient: {
    uuid: string;
    name: string;
    mrn: string;
    sex: string;
    age: string;
  };
  assignment: {
    areaName: string;
    areaUuid?: string;
    bedNumber: string;
    bedUuid?: string;
    bedId?: number;
    status: string;
    admitted?: string | null;
  } | null;
  awaiting?: boolean;
  visitUuid?: string;
  visitStartDatetime?: string;
  admissionEncounterUuid?: string;
  previous?: { areaName?: string; bedNumber?: string };
  bedReleased?: boolean;
  alreadyRequested?: boolean;
  billing?: InpatientBilling | null;
}

export interface InpatientBillingMoney {
  amount: number;
  formatted: string;
  currencyCode?: string;
}

export interface InpatientBilling {
  status: "ok" | "tariff_missing" | "needs_attention" | "policy_required" | string;
  message?: string | null;
  paymentLabel?: "PAID" | "PARTIALLY PAID" | "OUTSTANDING" | string | null;
  chargeCount?: number;
  outstanding?: InpatientBillingMoney;
  paid?: InpatientBillingMoney;
  total?: InpatientBillingMoney;
}

export interface NursingNote {
  uuid: string;
  patientUuid: string;
  admissionEncounterUuid: string;
  visitUuid: string;
  authorUserUuid: string;
  authorPersonUuid: string;
  authorName: string;
  recordedAt: string;
  content: string;
  requestId: string;
}

export interface NursingNotesPayload {
  status: string;
  patientUuid: string;
  activeAdmissionEncounterUuid: string;
  notes: NursingNote[];
}

export interface NursingNoteCreateResult {
  status: string;
  patientUuid: string;
  activeAdmissionEncounterUuid: string;
  note: NursingNote;
  duplicate: boolean;
}

export type MarOutcome = "given" | "not-done" | "refused" | "held";
export type MarSlotStatus =
  | "SCHEDULED"
  | "COMPLETED"
  | "NOT_DONE"
  | "STOPPED"
  | "MISSED";

export interface MarAdministration {
  uuid: string;
  status: string;
  outcome: MarOutcome;
  reason: string;
  outsideWindow: boolean;
  lateDocumentation: boolean;
  scheduledTime: number;
  actualTime: number;
  documentedTime: number | null;
  nurseUserUuid: string;
  nursePersonUuid: string;
  nurseName: string;
}

export interface MarSlot {
  uuid: string;
  scheduleUuid: string;
  status: MarSlotStatus;
  scheduledTime: number;
  timing: {
    status: "eligible" | "early" | "late" | "unknown";
    canAdministerNormally: boolean;
    minutesFromScheduled: number | null;
  };
  administration: MarAdministration | null;
}

export interface MarOrder {
  orderUuid: string;
  orderNumber: string;
  medication: string;
  drugUuid: string;
  dose: number | null;
  doseUnits: string;
  route: string;
  frequency: string;
  asNeeded: boolean;
  instructions: string;
  slots: MarSlot[];
}

export interface MarScheduleIssue {
  orderUuid: string;
  orderNumber?: string;
  medication?: string;
  code: string;
  message: string;
}

export interface MarPayload {
  status: string;
  patientUuid: string;
  visitUuid: string;
  admissionEncounterUuid: string;
  activeAdmission: boolean;
  administrationWindow: {
    earlyMinutes: number;
    lateMinutes: number;
  };
  orders: MarOrder[];
  scheduleIssues?: MarScheduleIssue[];
}

export interface NursingTreatmentItem {
  visitUuid: string;
  patientUuid: string;
  patientName: string;
  treatmentVisitStarted: string;
  orderUuid: string;
  orderNumber: string;
  medication: string;
  instructions: string;
  dose?: number | string | null;
  doseUnits?: string;
  route: string;
  frequency: string;
  duration: number | string | null;
  durationUnits: string;
  status: "DUE" | "COMPLETED" | "WAITING";
  medications: Array<{
    medication: string;
    instructions: string;
    dose?: number | string | null;
    doseUnits?: string;
    route: string;
    frequency: string;
    duration: number | string | null;
    durationUnits: string;
    administrationMode?: string;
  }>;
  notes: NursingTreatmentNote[];
}

export interface NursingTreatmentQueue {
  status: string;
  items: NursingTreatmentItem[];
}

export interface NursingTreatmentNote {
  uuid: string;
  patientUuid: string;
  visitUuid: string;
  authorName: string;
  recordedAt: string;
  content: string;
  requestId: string;
}

export interface MedicationScheduleResult {
  status: string;
  patientUuid: string;
  visitUuid: string;
  admissionEncounterUuid: string;
  createdOrderUuids: string[];
  alreadyScheduledOrderUuids: string[];
  issues: MarScheduleIssue[];
}

export interface MarCreateResult {
  status: string;
  duplicate: boolean;
  slot: MarSlot;
}

export interface InpatientVitalObservation {
  uuid: string;
  key: string;
  label: string;
  value: string;
  unit: string;
  conceptUuid: string;
}

export interface InpatientVitalReading {
  requestId: string;
  recordedAt: string;
  recordedBy: string;
  authorUserUuid: string;
  authorPersonUuid: string;
  encounterUuid: string;
  visitUuid: string;
  observations: InpatientVitalObservation[];
}

export interface InpatientVitalsPayload {
  status: string;
  patientUuid: string;
  visitUuid: string;
  admissionEncounterUuid: string;
  activeAdmission: boolean;
  canRecord?: boolean;
  readings: InpatientVitalReading[];
}

export interface InpatientVitalsCreateResult extends InpatientVitalsPayload {
  reading: InpatientVitalReading;
  duplicate: boolean;
}
