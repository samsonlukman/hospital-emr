import type { PatientAccountMoney } from "./patientAccount";
import type { LaboratoryPaymentStatus } from "./laboratoryBilling";

export interface LaboratoryCatalogueTest {
  id: string;
  sourceSn?: string;
  name: string;
  openmrsName?: string;
  department?: string;
  type?: string;
  specimen?: string;
  tat?: string;
  outsourced: boolean;
  notStat?: boolean;
  orderable: boolean;
  conceptUuid: string | null;
  conceptClass?: string;
  price: PatientAccountMoney | null;
  availability?: string;
  note?: string;
  enabled?: boolean;
  managed?: boolean;
}

export interface LaboratoryCataloguePayload {
  status: "ok" | "error";
  currency: { code: string; symbol: string };
  tests: LaboratoryCatalogueTest[];
  message?: string;
  code?: string;
}

export interface LaboratoryMasterTest {
  conceptUuid: string;
  name: string;
  conceptClass: string;
  type: string;
  synonyms: string[];
  alreadyEnabled: boolean;
}

export interface LaboratoryMasterSearchPayload {
  status: "ok" | "error";
  q: string;
  tests: LaboratoryMasterTest[];
  message?: string;
  code?: string;
}

export interface LaboratoryHospitalTestsPayload {
  status: "ok" | "error";
  canManage: boolean;
  currency: { code: string; symbol: string };
  tests: LaboratoryCatalogueTest[];
  message?: string;
  code?: string;
}

export interface LaboratoryHospitalTestMutationPayload {
  status: "ok" | "error";
  alreadyEnabled?: boolean;
  message?: string;
  test?: LaboratoryCatalogueTest;
  conceptUuid?: string;
  code?: string;
}

export interface LaboratoryCustomTestProperty {
  name: string;
  values: string[];
}

export interface LaboratoryCustomTest {
  id: string;
  name: string;
  price: number | null;
  priceLabel?: string | null;
  columns: string[];
  properties: LaboratoryCustomTestProperty[];
  createdAt?: string;
  createdBy?: string;
  source?: string;
}

export interface LaboratoryCustomTestsPayload {
  tests: LaboratoryCustomTest[];
  message?: string;
}

export interface LaboratoryCustomTestCreatePayload {
  test: LaboratoryCustomTest;
  message?: string;
}

export type LaboratoryBoardStage = "pending" | "processing" | "completed" | "unknown";
export type LaboratoryResultMapping = "unique" | "ambiguous" | "none";
export type LaboratoryRequestSource =
  | "doctor_order"
  | "laboratory_direct"
  | "external_referral"
  | string;
export type LaboratoryPatientType = "registered" | "external" | string;

export interface LaboratoryBoardOrder {
  uuid: string;
  orderNumber: string;
  testName: string;
  testNames?: string[];
  orderUuids?: string[];
  charges?: Array<{
    orderUuid: string;
    testName: string;
    hasCharge: boolean;
    paymentStatus: LaboratoryPaymentStatus | string;
  }>;
  patientUuid: string;
  visitUuid: string;
  patientName: string;
  mrn: string;
  age?: string;
  ordered: string;
  urgency: string;
  accession: string;
  provider: string;
  comment: string;
  outsourced: boolean;
  stage: LaboratoryBoardStage;
  laboratoryStatus: string;
  resultMapping: LaboratoryResultMapping;
  statusMessage: string;
  hasResult: boolean;
  paymentStatus: LaboratoryPaymentStatus;
  hasCharge: boolean;
  feeAmount?: PatientAccountMoney | null;
  feeFormatted?: string;
  requestSource?: LaboratoryRequestSource;
  requestSourceLabel?: string;
  patientType?: LaboratoryPatientType;
  patientTypeLabel?: string;
  isExternal?: boolean;
  externalId?: string;
  buyerPhone?: string;
  buyerSex?: string;
  buyerDob?: string;
  buyerAddress?: string;
  referrer?: string;
}

export interface LaboratoryBoardPayload {
  status: "ok" | "error";
  orders: LaboratoryBoardOrder[];
  pending: LaboratoryBoardOrder[];
  processing: LaboratoryBoardOrder[];
  completed: LaboratoryBoardOrder[];
  unknown: LaboratoryBoardOrder[];
  openelisUrl?: string;
  processingNote?: string;
  message?: string;
  code?: string;
}

export interface LaboratoryOrderDraftItem {
  conceptUuid: string;
  name: string;
  unlisted?: boolean;
  type?: string;
  specimen?: string;
  price: PatientAccountMoney | null;
  outsourced: boolean;
}

export interface LaboratoryOrderCreateResult {
  status: "ok" | "error";
  encounterUuid?: string;
  visitUuid?: string;
  orders: Array<{
    uuid: string;
    orderNumber?: string;
    testName?: string;
    visitUuid?: string;
  }>;
  requestSource?: string;
  requestSourceLabel?: string;
  message?: string;
  chargeError?: string | null;
  code?: string;
}

export interface LaboratoryWorkflowTest {
  testId: string;
  analysisId: string;
  resultId: string;
  resultType: string;
  name: string;
  orderedAs?: string;
  orderUuid?: string;
  status: string;
  resultValue: string;
  qualifiedResultValue: string;
  note: string;
  referenceLow: string;
  referenceHigh: string;
  referenceText?: string;
  referenceSource?: string;
  referencePublisher?: string;
  referenceVersion?: string;
  referenceUrl?: string;
  referenceAccessed?: string;
  referenceMethod?: string;
  referenceLimitations?: string;
  referenceNote?: string;
  referenceLowInclusive?: boolean;
  referenceHighInclusive?: boolean;
  flag: string;
  unit: string;
  options: Array<{ value: string; label?: string } | string>;
  sampleTypeId: string;
}

export interface LaboratoryWorkflowPayload {
  status: "ok" | "error";
  order: {
    uuid: string;
    patientUuid: string;
    patientName: string;
    mrn: string;
    age?: string;
    testName: string;
    accession: string;
    encounterUuid: string;
  };
  sample: {
    status: "waiting" | "collected" | string;
    accession: string;
    sampleTypeId: string;
    sampleSourceId: string;
  };
  tests: LaboratoryWorkflowTest[];
  validation: { status: "pending" | "validated" | string; validatedBy?: string };
  message?: string;
  code?: string;
}

export interface DeletedLabOrderRow {
  id: number;
  orderUuid: string;
  orderNumber: string;
  testName: string;
  patientName: string;
  hospitalNumber: string;
  patientUuid: string | null;
  reason: string;
  deletedBy: string;
  deletedAt: string;
}

export interface DeletedLabOrdersPayload {
  status: "ok" | "error";
  items: DeletedLabOrderRow[];
  total: number;
  offset: number;
  limit: number;
  message?: string;
}

export interface LaboratoryHistoryPayload {
  status: "ok" | "error";
  items: LaboratoryBoardOrder[];
  total: number;
  offset: number;
  limit: number;
  message?: string;
  code?: string;
}

export interface LaboratoryHistoryQuery {
  q?: string;
  from?: string;
  to?: string;
  requestSource?: string;
  patientType?: string;
  offset?: number;
  limit?: number;
}

export interface LaboratoryConsumableItem {
  id: string;
  name: string;
  kind: string;
  kindLabel: string;
  unit: string;
  onHand: number;
  reorderLevel: number;
  purchasePrice: number | null;
  status: string;
  notes?: string;
  updatedAt?: string;
}

export interface LaboratoryConsumablesPayload {
  items: LaboratoryConsumableItem[];
  kinds: string[];
  adjustReasons: string[];
  message?: string;
}

export interface LaboratoryConsumableMutationPayload {
  item: LaboratoryConsumableItem;
  message?: string;
}

export interface LaboratoryTestFrequencyItem {
  name: string;
  count: number;
}

export interface LaboratoryTestFrequency {
  status: "ok" | "unavailable";
  period?: { label?: string };
  total: number | null;
  tests: LaboratoryTestFrequencyItem[];
  message?: string;
}

export interface BloodBankUnit {
  id: string;
  component: string;
  abo: string;
  rh: string;
  bloodGroupLabel: string;
  bagNumber: string;
  volumeMl: number | null;
  collectedOn: string;
  expiresOn: string;
  status: string;
  statusLabel: string;
  patientUuid: string;
  patientName: string;
  source: string;
  discardReason: string;
  notes: string;
  createdBy?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface BloodBankUnitsPayload {
  units: BloodBankUnit[];
  components: string[];
  aboGroups: string[];
  rhTypes: string[];
  statuses: string[];
  counts: {
    available: number;
    reserved: number;
    total: number;
    expiringOrExpired: number;
  };
  message?: string;
}

export interface BloodBankUnitMutationPayload {
  unit: BloodBankUnit;
  message?: string;
}

