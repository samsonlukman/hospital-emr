import type {
  PharmacyCatalogue,
  PharmacyCatalogueDraft,
  PharmacyGenericOption,
  PharmacyAdjustDraft,
  PharmacyInventoryHistory,
  PharmacyInventoryItem,
  PharmacyInventoryList,
  PharmacyPrescription,
  PharmacyQueue,
  PharmacyReceiveDraft,
  PharmacySale,
  PharmacySaleList,
  PharmacySalesHistoryDetail,
  PharmacySalesHistoryList,
  PharmacySalesHistoryQuery,
} from "../types/pharmacy";
import { resolvedDosageForm } from "../workspaces/Pharmacy/pharmacyView";
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
      body.message || "This action requires the Pharmacy workspace.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Unable to complete the pharmacy request.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchPharmacyQueue(): Promise<PharmacyQueue> {
  return readJson<PharmacyQueue>("/openmrs/abikan-api/pharmacy/queue");
}

export function fetchPharmacyCatalogue(query = ""): Promise<PharmacyCatalogue> {
  const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
  return readJson<PharmacyCatalogue>(`/openmrs/abikan-api/pharmacy/catalogue${suffix}`);
}

export function fetchPharmacyCatalogueForms(): Promise<{ status: string; forms: string[] }> {
  return readJson<{ status: string; forms: string[] }>("/openmrs/abikan-api/pharmacy/catalogue/forms");
}

export function fetchPharmacyInventory(query = ""): Promise<PharmacyInventoryList> {
  const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
  return readJson<PharmacyInventoryList>(`/openmrs/abikan-api/pharmacy/inventory${suffix}`);
}

export function fetchPharmacyInventoryHistory(id: string): Promise<PharmacyInventoryHistory> {
  return readJson<PharmacyInventoryHistory>(
    `/openmrs/abikan-api/pharmacy/inventory/${encodeURIComponent(id)}/history`,
  );
}

export function receivePharmacyStock(
  id: string,
  draft: PharmacyReceiveDraft,
): Promise<{ status: string; item: PharmacyInventoryItem; receipt: { resultingOnHand: number; purchaseCost: number } }> {
  return readJson(`/openmrs/abikan-api/pharmacy/inventory/${encodeURIComponent(id)}/receive`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      quantity: Number(draft.quantity),
      purchasePrice: Number(draft.purchasePrice),
      supplier: draft.supplier.trim(),
      reference: draft.reference.trim(),
      note: draft.note.trim(),
    }),
  });
}

export function receivePharmacyStockBatch(payload: {
  supplier: string;
  reference: string;
  note: string;
  lines: Array<{ drugUuid: string; quantity: number; purchasePrice: number }>;
}): Promise<{
  status: string;
  count: number;
  message: string;
  receipts: Array<{ drugUuid: string; drugName: string; quantity: number; purchaseCost: number }>;
}> {
  return readJson(`/openmrs/abikan-api/pharmacy/inventory/receive`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
}

export function adjustPharmacyStock(
  id: string,
  draft: PharmacyAdjustDraft,
): Promise<{ status: string; item: PharmacyInventoryItem; adjustment: { resultingOnHand: number } }> {
  return readJson(`/openmrs/abikan-api/pharmacy/inventory/${encodeURIComponent(id)}/adjust`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      direction: draft.direction,
      quantity: Number(draft.quantity),
      reason: draft.reason,
      reference: draft.reference.trim(),
      note: draft.note.trim(),
    }),
  });
}

export function adjustPharmacyStockBatch(payload: {
  reference: string;
  note: string;
  lines: Array<{
    drugUuid: string;
    direction: "increase" | "decrease";
    quantity: number;
    reason: string;
  }>;
}): Promise<{
  status: "ok" | "partial";
  count: number;
  message: string;
  saved: Array<{ drugUuid: string; drugName: string }>;
  failed: Array<{ drugUuid: string; drugName: string; message: string; index?: number }>;
}> {
  return readJson(`/openmrs/abikan-api/pharmacy/inventory/adjust`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
}

export function createPharmacyCatalogueItem(draft: PharmacyCatalogueDraft): Promise<{ status: string; id: string; name: string }> {
  return readJson("/openmrs/abikan-api/pharmacy/catalogue", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      name: draft.name.trim(),
      brandName: draft.brandName.trim(),
      manufacturer: draft.manufacturer.trim(),
      strength: draft.strength.trim(),
      form: resolvedDosageForm(draft.form, draft.customForm),
      price: Number(draft.price),
      available: draft.available,
      conceptUuid: draft.conceptUuid.trim(),
      genericName: draft.genericName.trim(),
    }),
  });
}

export function createPharmacyCatalogueBatch(lines: PharmacyCatalogueDraft[]): Promise<{
  status: "ok" | "partial";
  count: number;
  message: string;
  saved: Array<{ index: number; id?: string; name: string }>;
  failed: Array<{ index: number; name: string; message: string }>;
}> {
  return readJson("/openmrs/abikan-api/pharmacy/catalogue/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      lines: lines.map((draft) => ({
        name: draft.name.trim(),
        brandName: draft.brandName.trim(),
        manufacturer: draft.manufacturer.trim(),
        strength: draft.strength.trim(),
        form: resolvedDosageForm(draft.form, draft.customForm),
        price: Number(draft.price),
        available: draft.available,
        conceptUuid: draft.conceptUuid.trim(),
        genericName: draft.genericName.trim(),
      })),
    }),
  });
}

export function searchPharmacyGenerics(query: string): Promise<{ status: string; generics: PharmacyGenericOption[] }> {
  const q = query.trim();
  const suffix = q ? `?q=${encodeURIComponent(q)}` : "";
  return readJson(`/openmrs/abikan-api/pharmacy/catalogue/generics${suffix}`);
}

export function createPharmacyGeneric(name: string): Promise<{ status: string; uuid: string; name: string; created: boolean }> {
  return readJson("/openmrs/abikan-api/pharmacy/catalogue/generics", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ name: name.trim() }),
  });
}

export function updatePharmacyCatalogueItem(
  id: string,
  draft: Partial<PharmacyCatalogueDraft>,
): Promise<{ status: string; id: string }> {
  return readJson(`/openmrs/abikan-api/pharmacy/catalogue/${encodeURIComponent(id)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      name: draft.name?.trim(),
      brandName: draft.brandName?.trim(),
      strength: draft.strength?.trim(),
      form: draft.form === undefined ? undefined : resolvedDosageForm(draft.form, draft.customForm),
      price: draft.price === undefined || draft.price === "" ? undefined : Number(draft.price),
      available: draft.available,
    }),
  });
}

export function fetchPharmacyPatientQueue(patientUuid: string): Promise<PharmacyQueue> {
  return readJson<PharmacyQueue>(
    `/openmrs/abikan-api/pharmacy/patient/${encodeURIComponent(patientUuid)}`,
  );
}

export function fetchPharmacyPrescription(orderUuid: string): Promise<PharmacyPrescription> {
  return readJson<PharmacyPrescription>(
    `/openmrs/abikan-api/pharmacy/prescription/${encodeURIComponent(orderUuid)}`,
  );
}

export function dispensePharmacyPrescription(
  orderUuid: string,
  requestId: string,
): Promise<PharmacyPrescription> {
  return readJson<PharmacyPrescription>(
    `/openmrs/abikan-api/pharmacy/prescription/${encodeURIComponent(orderUuid)}/dispense`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ requestId }),
    },
  );
}

export function dispensePharmacyPrescriptions(
  orderUuids: string[],
  requestId: string,
): Promise<PharmacyPrescription> {
  return readJson<PharmacyPrescription>("/openmrs/abikan-api/pharmacy/prescriptions/dispense", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ orderUuids, requestId }),
  });
}

export function cancelPharmacyPrescription(orderUuid: string): Promise<{
  status: "ok";
  alreadyCancelled?: boolean;
  orderUuid: string;
  message?: string;
  patientUuid?: string;
}> {
  return readJson(
    `/openmrs/abikan-api/pharmacy/prescription/${encodeURIComponent(orderUuid)}/cancel`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: "{}",
    },
  );
}

export interface PharmacyPrescriptionEdit {
  drugUuid: string;
  drugName: string;
  conceptUuid?: string;
  dose: number;
  doseUnits: string;
  route: string;
  frequency: string;
  duration: number;
  durationUnits: string;
  quantity: number;
  quantityUnits: string;
  instructions?: string;
}

export function billPharmacyPrescription(
  orderUuid: string,
  lines: Array<{ orderUuid: string; quantity: number }>,
): Promise<PharmacyPrescription> {
  return readJson<PharmacyPrescription>(
    `/openmrs/abikan-api/pharmacy/prescription/${encodeURIComponent(orderUuid)}/bill`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ lines }),
    },
  );
}

export function addPharmacyPrescriptionMedicine(
  orderUuid: string,
  body: PharmacyPrescriptionEdit,
): Promise<PharmacyPrescription> {
  return readJson<PharmacyPrescription>(
    `/openmrs/abikan-api/pharmacy/prescription/${encodeURIComponent(orderUuid)}/medicines`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function revisePharmacyPrescriptionMedicine(
  orderUuid: string,
  body: PharmacyPrescriptionEdit,
): Promise<PharmacyPrescription> {
  return readJson<PharmacyPrescription>(
    `/openmrs/abikan-api/pharmacy/prescription/${encodeURIComponent(orderUuid)}/revise`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function cancelPharmacyPrescriptions(orderUuids: string[]): Promise<{
  status: "ok";
  count: number;
  message?: string;
  patientUuid?: string;
  errors?: Array<{ orderUuid: string; code: string; message: string }>;
}> {
  return readJson("/openmrs/abikan-api/pharmacy/prescriptions/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ orderUuids }),
  });
}

export function announcePharmacyPrescriptions(input: {
  orderUuids?: string[];
  patientUuid?: string;
  priorOrderUuids?: string[];
  expectedCount?: number;
}): Promise<{
  status: "ok";
  count: number;
  message?: string;
}> {
  return readJson("/openmrs/abikan-api/pharmacy/prescriptions/announce", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      orderUuids: input.orderUuids ?? [],
      patientUuid: input.patientUuid ?? "",
      priorOrderUuids: input.priorOrderUuids ?? [],
      expectedCount: input.expectedCount ?? 0,
    }),
  });
}

export function newDispenseRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `dispense-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function refundPharmacySale(
  saleId: string,
  body: {
    requestId: string;
    mode?: "full" | "line";
    lineId?: string;
    quantity?: number;
  },
): Promise<{
  status: "ok";
  duplicate?: boolean;
  refunded?: boolean;
  refundStatus?: string;
  message?: string;
  refundAmount?: number;
  sale?: PharmacySalesHistoryDetail;
}> {
  return readJson(`/openmrs/abikan-api/pharmacy/sales-history/${encodeURIComponent(saleId)}/refund`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function cancelPharmacySalePrescription(saleId: string): Promise<{
  status: "ok";
  message?: string;
  saleId?: string;
}> {
  return readJson(
    `/openmrs/abikan-api/pharmacy/sales-history/${encodeURIComponent(saleId)}/cancel-prescription`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: "{}",
    },
  );
}

export function newRefundRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `refund-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createPharmacySale(body: {
  requestId: string;
  buyerType: "registered" | "other";
  patientUuid?: string;
  buyerName?: string;
  buyerPhone?: string;
  dispense?: boolean;
  lines: Array<{
    drugUuid: string;
    quantity: number;
    dose?: string;
    instructions?: string;
  }>;
}): Promise<PharmacySale> {
  return readJson<PharmacySale>("/openmrs/abikan-api/pharmacy/sales", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchPharmacySales(): Promise<PharmacySaleList> {
  return readJson<PharmacySaleList>("/openmrs/abikan-api/pharmacy/sales");
}

export function fetchPharmacySalesHistory(
  query: PharmacySalesHistoryQuery = {},
): Promise<PharmacySalesHistoryList> {
  const params = new URLSearchParams();
  const entries: Array<[keyof PharmacySalesHistoryQuery, string | number | undefined]> = [
    ["period", query.period],
    ["from", query.from],
    ["to", query.to],
    ["q", query.q],
    ["paymentStatus", query.paymentStatus],
    ["dispensingStatus", query.dispensingStatus],
    ["buyerType", query.buyerType],
    ["transactionType", query.transactionType],
    ["careSetting", query.careSetting],
    ["pharmacist", query.pharmacist],
    ["transactionId", query.transactionId],
    ["patientId", query.patientId],
    ["offset", query.offset],
    ["limit", query.limit],
  ];
  for (const [key, value] of entries) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<PharmacySalesHistoryList>(`/openmrs/abikan-api/pharmacy/sales-history${suffix}`);
}

export function fetchPharmacySalesHistoryItem(saleId: string): Promise<PharmacySalesHistoryDetail> {
  return readJson<PharmacySalesHistoryDetail>(
    `/openmrs/abikan-api/pharmacy/sales-history/${encodeURIComponent(saleId)}`,
  );
}

export function dispensePharmacySale(saleId: string, requestId: string): Promise<PharmacySale> {
  return readJson<PharmacySale>(
    `/openmrs/abikan-api/pharmacy/sales/${encodeURIComponent(saleId)}/dispense`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ requestId }),
    },
  );
}

export function quantityLabel(row: Pick<PharmacyPrescription, "quantity" | "quantityUnits">): string {
  return stockLabel(row.quantity, row.quantityUnits);
}

export function stockLabel(qty: number | string | null | undefined, units?: string | null): string {
  const base = units || "Tablet";
  const numeric = Number(qty);
  const qtyText = Number.isFinite(numeric) ? String(numeric).replace(/\.0$/, "") : "—";
  const plural =
    numeric === 1 || /s$/i.test(base) ? base : `${base}s`;
  return `${qtyText} ${plural}`;
}
