export interface PatientAccountMoney {
  amount: number;
  formatted: string;
  currencyCode: string;
  currencySymbol: string;
  decimalPlaces: number;
}

export interface PatientAccountCurrency {
  code: string;
  symbol: string;
  decimalPlaces: number;
  position: string;
}

export interface PatientAccountIdentity {
  uuid: string;
  name: string;
  mrn: string;
  nhis?: boolean;
}

export interface PatientAccountInvoiceLine {
  description: string;
  quantity: number;
  unitPrice: PatientAccountMoney;
  discountPercent?: number;
  subtotal: PatientAccountMoney;
  total: PatientAccountMoney;
  taxNames: string[];
}

export interface PatientAccountInvoice {
  id: number;
  number: string;
  date: string;
  department: string;
  departmentIdentified: boolean;
  state: string;
  paymentState: string;
  paymentStateLabel: string;
  origin: string;
  description: string;
  untaxed: PatientAccountMoney;
  tax: PatientAccountMoney;
  hasTax: boolean;
  total: PatientAccountMoney;
  paid: PatientAccountMoney;
  outstanding: PatientAccountMoney;
  lines: PatientAccountInvoiceLine[];
  pharmacyStatus: string | null;
  waivedBy?: string;
  createdBy?: string;
}

export interface PatientAccountActivity {
  kind: "invoice" | "unbilled_order";
  department: string;
  departmentIdentified: boolean;
  description: string;
  invoiceNumber: string | null;
  invoiceId: number | null;
  statusLabel: string;
  amount: PatientAccountMoney;
  outstanding: PatientAccountMoney;
  pharmacyStatus: string | null;
  orderName?: string;
}

export interface PatientAccountPayment {
  id: number;
  reference: string;
  date: string;
  amount: PatientAccountMoney;
  journal: string;
  method: string;
  state: string;
  relatedInvoices: Array<{ id: number; number?: string | null }>;
  allocationConfirmed: boolean;
  recordedBy?: string;
}

export interface PatientAccountPharmacyRow {
  orderName: string;
  description: string;
  invoiceNumber: string | null;
  invoiceId: number | null;
  paymentStateLabel: string;
  dispensingStatus: string;
  pickingName: string | null;
  pickingState: string | null;
}

export interface PatientAccountPayload {
  status: "ok" | "account_not_found" | "no_activity" | "error";
  readOnly: boolean;
  patient: PatientAccountIdentity;
  partnerFound: boolean;
  message?: string | null;
  currency?: PatientAccountCurrency;
  summary?: {
    outstandingByCurrency: PatientAccountMoney[];
    paidByCurrency: PatientAccountMoney[];
    billedByCurrency: PatientAccountMoney[];
  };
  departments?: string[];
  activity?: PatientAccountActivity[];
  invoices?: PatientAccountInvoice[];
  payments?: PatientAccountPayment[];
  pharmacy?: PatientAccountPharmacyRow[];
  limitations?: {
    paymentAllocation: "confirmed" | "unavailable";
    partialPaymentExample: boolean;
  };
  code?: string;
}

export interface PatientAccountInvoicePayload {
  status: "ok" | "account_not_found" | "error";
  readOnly: boolean;
  patient: PatientAccountIdentity;
  invoice?: PatientAccountInvoice;
  message?: string;
  code?: string;
}
