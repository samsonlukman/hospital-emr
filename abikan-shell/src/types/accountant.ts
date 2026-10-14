import type { PatientAccountMoney, PatientAccountPayload } from "./patientAccount";

export interface AccountantJournal {
  id: number;
  name: string;
  code: string;
  type: string;
}

export interface AccountantAttentionRow {
  id: number;
  number: string;
  date?: string;
  arrivedAt?: string;
  department: string;
  paymentState: string;
  paymentStateLabel: string;
  total: PatientAccountMoney;
  outstanding: PatientAccountMoney;
  patientName: string;
  mrn: string;
  patientUuid: string | null;
  nhis?: boolean;
  createdBy?: string;
  purpose?: string;
}

export interface AccountantPaymentRow {
  id: number;
  reference: string;
  date: string;
  actedAt?: string;
  amount: PatientAccountMoney;
  journal: string;
  journalId: number | null;
  method: string;
  state: string;
  patientName: string;
  mrn: string;
  patientUuid: string | null;
  relatedInvoices: Array<{ id: number; number: string }>;
  discountNote?: string;
  createUid: string;
  createDate: string;
  amountRefunded?: number;
  amountRefundable?: number;
  refundStatus?: string;
  canRefund?: boolean;
  recordedBy?: string;
}

export interface WaivedBillRow {
  invoiceId: number;
  billNumber: string;
  patientName: string;
  hospitalNumber: string;
  patientUuid: string | null;
  amount: string;
  waivedBy: string;
  waivedAt: string;
  statusLabel: string;
}

export interface DeletedBillRow {
  id: number;
  invoiceId: number;
  billNumber: string;
  patientName: string;
  hospitalNumber: string;
  patientUuid: string | null;
  department: string;
  amount: string;
  reason: string;
  deletedBy: string;
  deletedAt: string;
}

export interface AccountantRefundRow {
  id: number;
  reference: string;
  date: string;
  actedAt?: string;
  amount: PatientAccountMoney;
  paymentState: string;
  paymentStateLabel: string;
  origin: string;
  reason: string;
  ref: string;
  patientName: string;
  mrn: string;
  patientUuid: string | null;
  processedBy: string;
  createUid: string;
  createDate: string;
  sourcePaymentId: number | null;
  source: string;
}

export interface AccountantDashboard {
  status: "ok" | "error";
  currency?: {
    code: string;
    symbol: string;
    decimalPlaces: number;
    position: string;
  };
  journals?: AccountantJournal[];
  today?: {
    date: string;
    paymentsReceivedByCurrency: PatientAccountMoney[];
    paymentCount: number;
    outstandingByCurrency: PatientAccountMoney[];
    outstandingCount: number;
    refundsByCurrency?: PatientAccountMoney[];
    refundCount?: number;
    netByCurrency?: PatientAccountMoney[];
  };
  attention?: AccountantAttentionRow[];
  attentionTotal?: number;
  recentPayments?: AccountantPaymentRow[];
  recentPaymentsTotal?: number;
  recentRefunds?: AccountantRefundRow[];
  recentRefundsTotal?: number;
  message?: string;
  code?: string;
}

export interface AccountantPaymentResult {
  status: "ok" | "error";
  success?: boolean;
  requestId?: string;
  recordedBy?: string;
  patient?: { uuid: string; name: string; mrn: string };
  journal?: AccountantJournal;
  payment?: AccountantPaymentRow;
  account?: PatientAccountPayload;
  receiptAvailable?: boolean;
  idempotentReplay?: boolean;
  message?: string;
  code?: string;
}
