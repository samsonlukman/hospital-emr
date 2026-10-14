/** CIEL / OpenMRS concepts present on this server. Used only for reading and writing observations. */

export interface VitalConcept {
  uuid: string;
  name: string;
  label: string;
  unit: string;
  key: string;
  dataType: "Numeric";
  lowAbsolute: number;
  hiAbsolute: number;
  lowNormal: number | null;
  hiNormal: number | null;
}

export const VITAL_CONCEPTS = {
  systolic: {
    uuid: "5085AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    name: "Systolic blood pressure",
    label: "Systolic",
    unit: "mmHg",
    key: "systolic",
    dataType: "Numeric",
    lowAbsolute: 0,
    hiAbsolute: 250,
    lowNormal: 100,
    hiNormal: 140,
  },
  diastolic: {
    uuid: "5086AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    name: "Diastolic blood pressure",
    label: "Diastolic",
    unit: "mmHg",
    key: "diastolic",
    dataType: "Numeric",
    lowAbsolute: 0,
    hiAbsolute: 150,
    lowNormal: 60,
    hiNormal: 90,
  },
  pulse: {
    uuid: "5087AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    name: "Pulse",
    label: "Pulse",
    unit: "bpm",
    key: "pulse",
    dataType: "Numeric",
    lowAbsolute: 0,
    hiAbsolute: 230,
    lowNormal: 60,
    hiNormal: 100,
  },
  temperature: {
    uuid: "5088AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    name: "Temperature (C)",
    label: "Temperature",
    unit: "°C",
    key: "temperature",
    dataType: "Numeric",
    lowAbsolute: 25,
    hiAbsolute: 47,
    lowNormal: 35,
    hiNormal: 37.7,
  },
  spo2: {
    uuid: "5092AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    name: "Arterial blood oxygen saturation (pulse oximeter)",
    label: "SpO₂",
    unit: "%",
    key: "spo2",
    dataType: "Numeric",
    lowAbsolute: 0,
    hiAbsolute: 100,
    lowNormal: 95,
    hiNormal: null,
  },
  weight: {
    uuid: "5089AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    name: "Weight (kg)",
    label: "Weight",
    unit: "kg",
    key: "weight",
    dataType: "Numeric",
    lowAbsolute: 0,
    hiAbsolute: 250,
    lowNormal: null,
    hiNormal: null,
  },
  respiratoryRate: {
    uuid: "5242AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    name: "Respiratory rate",
    label: "Respiratory Rate",
    unit: "/min",
    key: "respiratoryRate",
    dataType: "Numeric",
    lowAbsolute: 0,
    hiAbsolute: 99,
    lowNormal: 12,
    hiNormal: 18,
  },
  height: {
    uuid: "5090AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    name: "Height (cm)",
    label: "Height",
    unit: "cm",
    key: "height",
    dataType: "Numeric",
    lowAbsolute: 10,
    hiAbsolute: 272,
    lowNormal: null,
    hiNormal: null,
  },
} as const satisfies Record<string, VitalConcept>;

export type VitalConceptKey = keyof typeof VITAL_CONCEPTS;

export const CONSULTATION_ENCOUNTER_TYPE = "d34fe3ab-5e07-11ef-8f7c-0242ac120002";
export const OPD_VISIT_TYPE_UUID = "54f43754-c6ce-4472-890e-0f28acaeaea6";
export const OPD_VISIT_TYPE_NAME = "OPD";

/** Live GET /visittype names included in Clinical Today's Patients. */
export const CLINICAL_TODAY_VISIT_TYPE_NAMES = ["OPD", "Special OPD", "Follow Up", "ANC"] as const;
export const CLINICAL_TODAY_EXCLUDED_VISIT_TYPE_NAMES = ["IPD", "EMERGENCY"] as const;

export const CONSULTATION_NOTE_CONCEPT = {
  uuid: "d37294c5-5e07-11ef-8f7c-0242ac120002",
  name: "Consultation Note",
  dataType: "Text",
} as const;

export const HPI_CONCEPT = {
  uuid: "1390AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  name: "History of present illness",
  dataType: "Text",
} as const;

/** Existing Bahmni set. Do not replace with CIEL Chief complaint (5219), which has 0 answers here. */
export const CHIEF_COMPLAINT_RECORD_CONCEPT = {
  uuid: "da47a35d-5806-48b7-b467-e29902759491",
  name: "Chief Complaint Record",
  dataType: "N/A",
} as const;

export const CHIEF_COMPLAINT_CODED_CONCEPT = {
  uuid: "9bb0795c-4ff0-0305-1990-000000000002",
  name: "Chief Complaint Coded",
  dataType: "Coded",
} as const;

export const CHIEF_COMPLAINT_TEXT_CONCEPT = {
  uuid: "160531AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  name: "Chief complaint (text)",
  dataType: "Text",
} as const;

export const CHIEF_COMPLAINT_DURATION_VALUE_CONCEPT = {
  uuid: "1731AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  name: "Sign/symptom duration",
  dataType: "Numeric",
} as const;

export const CHIEF_COMPLAINT_DURATION_UNIT_CONCEPT = {
  uuid: "9bb0795c-4ff0-0305-1990-000000000003",
  name: "Chief Complaint Duration",
  dataType: "Coded",
} as const;

/** Existing answer on Chief Complaint Coded. Used when the list has no matching term. */
export const OTHER_GENERIC_COMPLAINT_UUID = "9bb0795c-4ff0-0305-1990-000000000001";

/** Live answers on Chief Complaint Duration. CIEL hours/days/weeks/months/years. */
export const CHIEF_COMPLAINT_DURATION_UNITS = [
  { uuid: "1822AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", name: "Hours" },
  { uuid: "1072AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", name: "Days" },
  { uuid: "1073AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", name: "Weeks" },
  { uuid: "1074AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", name: "Months" },
  { uuid: "1734AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", name: "Years" },
] as const;

export const DISPOSITION_ANSWERS = [
  { code: "ADMIT", display: "Admit Patient", uuid: "d36dd2e4-5e07-11ef-8f7c-0242ac120002" },
  { code: "DISCHARGE", display: "Discharge Patient", uuid: "d36e1435-5e07-11ef-8f7c-0242ac120002" },
  { code: "TRANSFER", display: "Transfer Patient", uuid: "d36e564b-5e07-11ef-8f7c-0242ac120002" },
  { code: "UNDO_DISCHARGE", display: "Undo Discharge", uuid: "d5fe696d-5e07-11ef-8f7c-0242ac120002" },
] as const;

export const LAB_ORDER_TYPE_UUID = "d3560b17-5e07-11ef-8f7c-0242ac120002";
export const RADIOLOGY_ORDER_TYPE_UUID = "d3561dc0-5e07-11ef-8f7c-0242ac120002";

/** Global property `drugOrder.drugOther`. Required when the doctor types a medicine name. */
export const DRUG_OTHER_CONCEPT = {
  uuid: "d726baf8-5e07-11ef-8f7c-0242ac120002",
  name: "DrugOther",
} as const;
