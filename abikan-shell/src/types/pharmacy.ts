export type PharmacyPaymentStatus = "UNPAID" | "PAID" | "PARTIALLY PAID" | "NOT BILLED";

export type PharmacyDispensingStatus =
  | "UNPAID"
  | "PAID"
  | "READY TO DISPENSE"
  | "PARTIALLY DISPENSED"
  | "DISPENSED"
  | "STOPPED"
  | "NOT IN PHARMACY";

export interface PharmacyPrescription {
  status: "ok";
  orderUuid: string;
  orderNumber: string;
  patientUuid: string;
  patientName: string;
  mrn: string;
  prescriber: string;
  ordered: string;
  doctorNotes?: Array<{ content: string; recordedAt: string; authorName: string }>;
  drugUuid?: string;
  drugName: string;
  strength: string;
  dose: string;
  doseUnits: string;
  route: string;
  frequency: string;
  duration: string;
  instructions: string;
  quantity: number;
  quantityUnits: string;
  paymentStatus: PharmacyPaymentStatus;
  dispensingStatus: PharmacyDispensingStatus;
  canDispense: boolean;
  blockReason: string | null;
  notInPharmacy?: boolean;
  encounterUuid?: string;
  groupKey?: string;
  stockOnHand: number;
  stockAfter: number;
  delivered: number;
  success?: boolean;
  alreadyDispensed?: boolean;
  recordedBy?: string;
  message?: string;
  code?: string;
  saleId?: string | null;
  saleName?: string | null;
  medicines?: PharmacyPrescription[];
  medicineCount?: number;
  groupDispensingStatus?: PharmacyDispensingStatus | string;
  groupPaymentStatus?: PharmacyPaymentStatus | string;
  nhis?: boolean;
  dispenseErrors?: Array<{ orderUuid: string; code: string; message: string }>;
}

export interface PharmacyQueue {
  status: "ok" | "error";
  ready: PharmacyPrescription[];
  other: PharmacyPrescription[];
  nhis?: boolean;
  message?: string;
  code?: string;
}

export interface PharmacyCataloguePrice {
  amount: number;
  formatted: string;
  currencyCode: string;
  currencySymbol: string;
}

export interface PharmacyCatalogueItem {
  id: string;
  name: string;
  hospitalName: string;
  listedAs: string;
  brandName: string;
  strength: string;
  form: string;
  stockOnHand: number;
  stockUnits: string;
  price: PharmacyCataloguePrice | null;
  developmentPrice: boolean;
  developmentPriceNote: string;
  available: boolean;
  status: string;
  canEdit?: boolean;
}

export interface PharmacyCatalogue {
  status: "ok" | "error";
  currency?: { code: string; symbol: string };
  developmentPrice?: boolean;
  developmentPriceNote?: string;
  canManage?: boolean;
  count?: number;
  items: PharmacyCatalogueItem[];
  message?: string;
  code?: string;
}

export interface PharmacyCatalogueDraft {
  name: string;
  brandName: string;
  manufacturer: string;
  strength: string;
  form: string;
  customForm?: string;
  price: string;
  available: boolean;
  conceptUuid: string;
  genericName: string;
}

export interface PharmacyCatalogueLineDraft extends PharmacyCatalogueDraft {
  key: string;
  fieldErrors: Partial<
    Record<"name" | "generic" | "strength" | "form" | "price", string>
  >;
}

export interface PharmacyGenericOption {
  uuid: string;
  name: string;
}

export interface PharmacyInventoryItem {
  id: string;
  name: string;
  hospitalName: string;
  listedAs: string;
  brandName: string;
  strength: string;
  form: string;
  stockUnits: string;
  onHand: number;
  reserved: number;
  available: number;
  status: string;
  sellingPrice: PharmacyCataloguePrice | null;
  canReceive: boolean;
  canAdjust: boolean;
  protectedTest?: boolean;
}

export interface PharmacyInventoryList {
  status: "ok" | "error";
  canManageInventory?: boolean;
  count?: number;
  items: PharmacyInventoryItem[];
  adjustmentReasons?: string[];
  message?: string;
  code?: string;
}

export interface PharmacyInventoryHistoryRow {
  id: string;
  productName: string;
  previousQuantity: number;
  movementQuantity: number;
  resultingQuantity: number;
  movementType: string;
  purchasePricePerUnit: number | null;
  purchaseCost: number | null;
  supplier: string;
  reason: string;
  user: string;
  when: string;
  reference: string;
}

export interface PharmacyInventoryHistory {
  status: "ok" | "error";
  item: PharmacyInventoryItem;
  movements: PharmacyInventoryHistoryRow[];
}

export interface PharmacyReceiveDraft {
  quantity: string;
  purchasePrice: string;
  supplier: string;
  reference: string;
  note: string;
}

export interface PharmacyReceiveLineDraft {
  key: string;
  drugUuid: string;
  drugName: string;
  strength: string;
  form: string;
  onHand: number;
  sellingPriceLabel: string;
  quantity: string;
  purchasePrice: string;
  fieldErrors: Partial<Record<"drug" | "quantity" | "purchasePrice", string>>;
}

export interface PharmacyAdjustDraft {
  direction: "increase" | "decrease";
  quantity: string;
  reason: string;
  reference: string;
  note: string;
}

export interface PharmacyAdjustLineDraft {
  key: string;
  drugUuid: string;
  drugName: string;
  strength: string;
  form: string;
  onHand: number;
  reserved: number;
  direction: "increase" | "decrease";
  quantity: string;
  reason: string;
  fieldErrors: Partial<Record<"drug" | "quantity" | "reason" | "direction", string>>;
}

export interface PharmacyStockBatchResult {
  status: "ok" | "partial" | "error";
  count: number;
  message: string;
  saved?: Array<{ drugUuid: string; drugName: string }>;
  failed?: Array<{ drugUuid: string; drugName: string; message: string; index?: number }>;
}

export type PharmacySaleBuyerType = "registered" | "other";

export interface PharmacySaleLineDraft {
  drugUuid: string;
  drugName: string;
  quantity: string;
  dose: string;
  instructions: string;
  unitPrice: number | null;
}

export interface PharmacySaleLine {
  lineId: string;
  externalOrderId: string;
  drugName: string;
  quantity: number;
  unitPrice: number;
  delivered: number;
  stockOnHand: number;
  instructions: string;
}

export interface PharmacySale {
  status: "ok";
  saleId: string;
  saleName: string;
  saleToken: string;
  buyerType: PharmacySaleBuyerType;
  patientUuid: string;
  buyerName: string;
  mrn: string;
  paymentStatus: PharmacyPaymentStatus;
  dispensingStatus: string;
  canDispense: boolean;
  blockReason: string | null;
  amountTotal: number;
  invoiceName: string;
  lines: PharmacySaleLine[];
  recordedBy?: string;
  transactionType: "direct_sale";
  code?: string;
  message?: string;
  alreadyCreated?: boolean;
  alreadyDispensed?: boolean;
  success?: boolean;
}

export interface PharmacySaleList {
  status: "ok" | "error";
  ready: PharmacySale[];
  other: PharmacySale[];
  sales: PharmacySale[];
  message?: string;
  code?: string;
}

export type PharmacySaleTransactionType = "direct_sale" | "prescription";

export interface PharmacySalesHistoryPeriod {
  period: string;
  label: string;
  timezone: string;
  startDate: string;
  endDate: string;
}

export interface PharmacySalesHistoryItem {
  saleId: string;
  saleName: string;
  dateOrder: string;
  transactionType: PharmacySaleTransactionType | string;
  buyerType: PharmacySaleBuyerType;
  buyerName: string;
  mrn: string;
  patientUuid: string;
  paymentStatus: PharmacyPaymentStatus | string;
  dispensingStatus: string;
  refundStatus?: string;
  refunded?: boolean;
  partiallyRefunded?: boolean;
  canRefund?: boolean;
  canDeletePrescription?: boolean;
  amountTotal: number;
  amountPaid: number;
  amountResidual: number;
  invoiceName: string;
  lineCount: number;
  quantityTotal: number;
  prescriptionRefs: string[];
  careSetting: string;
  admissionReference: string;
  createdBy: string;
  dispensedBy: string;
  dispensedAt: string;
  processedBy: string;
}

export interface PharmacySalesHistoryList {
  status: "ok" | "error";
  items: PharmacySalesHistoryItem[];
  total: number;
  offset: number;
  limit: number;
  truncated?: boolean;
  period?: PharmacySalesHistoryPeriod;
  message?: string;
  code?: string;
}

export interface PharmacySalesHistoryLine {
  lineId: string;
  externalOrderId: string;
  drugName: string;
  quantity: number;
  unitPrice: number;
  discount: number;
  lineTotal: number;
  delivered: number;
  quantityRefunded?: number;
  quantityRefundable?: number;
  canRefund?: boolean;
  refundAmountPerUnit?: number;
}

export interface PharmacySalesHistoryDetail extends PharmacySalesHistoryItem {
  status: "ok";
  createDate: string;
  writeDate: string;
  lines: PharmacySalesHistoryLine[];
  message?: string;
  code?: string;
}

export interface PharmacySalesHistoryQuery {
  period?: string;
  from?: string;
  to?: string;
  q?: string;
  paymentStatus?: string;
  dispensingStatus?: string;
  buyerType?: string;
  transactionType?: string;
  careSetting?: string;
  pharmacist?: string;
  transactionId?: string;
  patientId?: string;
  offset?: number;
  limit?: number;
}
