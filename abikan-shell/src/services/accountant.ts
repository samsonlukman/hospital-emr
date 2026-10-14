import type {
  AccountantAttentionRow,
  AccountantDashboard,
  AccountantJournal,
  AccountantPaymentRow,
  AccountantRefundRow,
  DeletedBillRow,
  WaivedBillRow,
} from "../types/accountant";
import type { PatientAccountMoney, PatientAccountPayload } from "../types/patientAccount";
import { PatientAccountRequestError } from "./patientAccount";

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = (await response.json().catch(() => ({}))) as {
    message?: string;
    code?: string;
  };
  if (response.status === 401) {
    throw new PatientAccountRequestError("Sign in required.", 401, "unauthenticated");
  }
  if (response.status === 403) {
    throw new PatientAccountRequestError(
      body.message || "This action requires the Accountant / Cashier workspace.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Unable to complete the accountant request.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchAccountantDashboard(): Promise<AccountantDashboard> {
  return readJson<AccountantDashboard>("/openmrs/abikan-api/accountant/dashboard");
}

export function fetchAccountantPayment(paymentId: number): Promise<{
  status: string;
  payment: AccountantPaymentRow;
  receiptAvailable?: boolean;
}> {
  return readJson(`/openmrs/abikan-api/accountant/payment/${paymentId}`);
}

export function fetchAccountantPayments(query: Record<string, string | number | undefined>): Promise<{
  status: string;
  items: AccountantPaymentRow[];
  total: number;
  offset: number;
  limit: number;
}> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString() ? `?${params}` : "";
  return readJson(`/openmrs/abikan-api/accountant/payments${suffix}`);
}

export function fetchAccountantOutstanding(query: Record<string, string | number | undefined>): Promise<{
  status: string;
  items: AccountantAttentionRow[];
  total: number;
  offset: number;
  limit: number;
}> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString() ? `?${params}` : "";
  return readJson(`/openmrs/abikan-api/accountant/outstanding${suffix}`);
}

export function fetchAccountantRefunds(query: Record<string, string | number | undefined>): Promise<{
  status: string;
  items: AccountantRefundRow[];
  total: number;
  offset: number;
  limit: number;
}> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString() ? `?${params}` : "";
  return readJson(`/openmrs/abikan-api/accountant/refunds${suffix}`);
}

export function refundAccountantPayment(
  paymentId: number,
  body: { requestId: string; amount?: number; reason?: string },
): Promise<{
  status: string;
  message?: string;
  refundStatus?: string;
  processedBy?: string;
  payment?: AccountantPaymentRow;
  duplicate?: boolean;
}> {
  return readJson(`/openmrs/abikan-api/accountant/payment/${paymentId}/refund`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function registerAccountantPayment(body: {
  requestId: string;
  patientUuid: string;
  invoiceIds: number[];
  discountPercentage: number;
  amount: number;
  journalId: number;
  expectedResiduals: Record<string, number>;
}): Promise<{
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
}> {
  return readJson("/openmrs/abikan-api/accountant/payment", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchDeletedBills(query: Record<string, string | number | undefined>): Promise<{
  status: string;
  items: DeletedBillRow[];
  total: number;
  offset: number;
  limit: number;
}> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString() ? `?${params}` : "";
  return readJson(`/openmrs/abikan-api/accountant/deleted-bills${suffix}`);
}

export function fetchWaivedBills(query: Record<string, string | number | undefined>): Promise<{
  status: string;
  items: WaivedBillRow[];
  total: number;
  offset: number;
  limit: number;
}> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString() ? `?${params}` : "";
  return readJson(`/openmrs/abikan-api/accountant/waived-bills${suffix}`);
}

export function createAccountantBill(body: {
  patientUuid?: string;
  patientName?: string;
  amount: string;
  description: string;
  requestId: string;
}): Promise<{
  status: string;
  success?: boolean;
  invoiceId: number;
  billNumber: string;
  amount: PatientAccountMoney;
  description: string;
  createdBy: string;
  patient: { uuid: string; name: string };
}> {
  return readJson("/openmrs/abikan-api/accountant/create-bill", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteAccountantBill(body: {
  invoiceId: number;
  reason: string;
  patientUuid?: string;
}): Promise<{
  status: string;
  success?: boolean;
  message?: string;
  account?: PatientAccountPayload;
}> {
  return readJson("/openmrs/abikan-api/accountant/delete-bill", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function waiveAccountantBills(body: {
  patientUuid: string;
  invoiceIds: number[];
  expectedResiduals: Record<string, number>;
}): Promise<{
  status: "ok" | "error";
  success?: boolean;
  account?: PatientAccountPayload;
  message?: string;
}> {
  return readJson("/openmrs/abikan-api/accountant/waive", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function accountantReceiptHref(paymentId: number): string {
  return `/openmrs/abikan-api/accountant/payment/${paymentId}/receipt`;
}

export function newPaymentRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `pay-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function moneyAmount(value: PatientAccountMoney | undefined): number {
  return Number(value?.amount) || 0;
}
