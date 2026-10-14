import type {
  LaboratoryChargePayload,
  LaboratoryExternalOrderPayload,
  LaboratoryExternalPatientPayload,
  LaboratoryExternalPatientSearchPayload,
  LaboratoryLinkedExternalPayload,
} from "../types/laboratoryBilling";
import type {
  LaboratoryBoardPayload,
  LaboratoryCataloguePayload,
  LaboratoryCustomTestCreatePayload,
  LaboratoryCustomTestsPayload,
  LaboratoryConsumableMutationPayload,
  LaboratoryConsumablesPayload,
  LaboratoryTestFrequency,
  BloodBankUnitMutationPayload,
  BloodBankUnitsPayload,
  DeletedLabOrdersPayload,
  LaboratoryHistoryPayload,
  LaboratoryHistoryQuery,
  LaboratoryHospitalTestMutationPayload,
  LaboratoryHospitalTestsPayload,
  LaboratoryMasterSearchPayload,
  LaboratoryOrderCreateResult,
  LaboratoryWorkflowPayload,
} from "../types/laboratoryCatalogue";
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
      body.message || "This action is not available in this department.",
      403,
      "forbidden",
    );
  }
  if (!response.ok) {
    throw new PatientAccountRequestError(
      body.message || "Unable to complete the laboratory request.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchLaboratoryChart(patientUuid: string): Promise<{
  orders: Array<{
    uuid: string;
    orderNumber?: string;
    testName?: string;
    patientUuid?: string;
    visitUuid?: string;
    ordered?: string;
    urgency?: string;
    comment?: string;
    provider?: string;
    accession?: string;
  }>;
  results: Array<Record<string, unknown>>;
}> {
  return readJson(
    `/openmrs/abikan-api/laboratory/patient/${encodeURIComponent(patientUuid)}/chart`,
  );
}

export function fetchLaboratoryCharge(patientUuid: string): Promise<LaboratoryChargePayload> {
  return readJson<LaboratoryChargePayload>(
    `/openmrs/abikan-api/laboratory/patient/${encodeURIComponent(patientUuid)}`,
  );
}

export function fetchReleasedLaboratoryResults(
  patientUuid: string,
): Promise<{ results: Array<Record<string, unknown>> }> {
  return readJson<{ results: Array<Record<string, unknown>> }>(
    `/openmrs/abikan-api/laboratory/patient/${encodeURIComponent(patientUuid)}/released-results`,
  );
}

export function createLaboratoryCharge(
  patientUuid: string,
  requestId: string,
  orderUuid?: string,
  orderUuids?: string[],
): Promise<LaboratoryChargePayload> {
  return readJson<LaboratoryChargePayload>(
    `/openmrs/abikan-api/laboratory/patient/${encodeURIComponent(patientUuid)}/charge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ requestId, orderUuid, orderUuids }),
    },
  );
}

export async function fetchLaboratoryResultPdf(
  orderUuid: string,
  patientUuid: string | undefined,
  action: "print" | "download",
): Promise<void> {
  const params = new URLSearchParams();
  if (patientUuid) {
    params.set("patient", patientUuid);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(
    `/openmrs/abikan-api/laboratory/order/${encodeURIComponent(orderUuid)}/result.pdf${suffix}`,
    { credentials: "include" },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { message?: string };
    throw new PatientAccountRequestError(body.message || "The result could not be prepared.", response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  if (action === "download") {
    const link = document.createElement("a");
    link.href = url;
    link.download = "laboratory-result.pdf";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    return;
  }
  const frame = document.createElement("iframe");
  frame.style.position = "fixed";
  frame.style.left = "-10000px";
  frame.style.top = "0";
  frame.style.width = "800px";
  frame.style.height = "1000px";
  frame.style.border = "0";
  frame.src = url;
  frame.onload = () => {
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
    window.setTimeout(() => {
      frame.remove();
      URL.revokeObjectURL(url);
    }, 60_000);
  };
  document.body.appendChild(frame);
}

export function newLaboratoryRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `lab-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function fetchLaboratoryCatalogue(query = ""): Promise<LaboratoryCataloguePayload> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<LaboratoryCataloguePayload>(`/openmrs/abikan-api/laboratory/catalogue${suffix}`);
}

export function fetchLaboratoryBoard(): Promise<LaboratoryBoardPayload> {
  return readJson<LaboratoryBoardPayload>("/openmrs/abikan-api/laboratory/board");
}

export function fetchLaboratoryTestFrequency(query = ""): Promise<LaboratoryTestFrequency> {
  const suffix = query ? `?${query}` : "";
  return readJson<LaboratoryTestFrequency>(`/openmrs/abikan-api/laboratory/test-frequency${suffix}`);
}

export function fetchDeletedLabOrders(query: {
  q?: string;
  offset?: number;
  limit?: number;
}): Promise<DeletedLabOrdersPayload> {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.offset != null) params.set("offset", String(query.offset));
  if (query.limit != null) params.set("limit", String(query.limit));
  const suffix = params.toString() ? `?${params}` : "";
  return readJson<DeletedLabOrdersPayload>(`/openmrs/abikan-api/laboratory/deleted-orders${suffix}`);
}

export function deleteLaboratoryOrder(body: {
  orderUuid: string;
  reason: string;
  patientUuid?: string;
}): Promise<{ status: string; success?: boolean; message?: string }> {
  return readJson(`/openmrs/abikan-api/laboratory/order/${encodeURIComponent(body.orderUuid)}/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ reason: body.reason, patientUuid: body.patientUuid }),
  });
}

export interface LaboratoryOrderDetailPayload {
  status: "ok" | "error";
  order: {
    uuid: string;
    orderNumber: string;
    testName: string;
    patientUuid: string;
    visitUuid: string;
    encounterUuid: string;
    patientName: string;
    mrn: string;
    age?: string;
    ordered: string;
    urgency: string;
    comment: string;
    provider: string;
    accession: string;
  };
  message?: string;
  code?: string;
}

export function fetchLaboratoryOrderDetail(
  orderUuid: string,
  patientUuid?: string,
  visitUuid?: string,
): Promise<LaboratoryOrderDetailPayload> {
  const params = new URLSearchParams();
  const patient = (patientUuid || "").trim();
  const visit = (visitUuid || "").trim();
  if (patient) {
    params.set("patient", patient);
  }
  if (visit) {
    params.set("visit", visit);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<LaboratoryOrderDetailPayload>(
    `/openmrs/abikan-api/laboratory/order/${encodeURIComponent(orderUuid)}${suffix}`,
  );
}

export function fetchLaboratoryWorkflow(
  orderUuid: string,
  patientUuid?: string,
  visitUuid?: string,
): Promise<LaboratoryWorkflowPayload> {
  const params = new URLSearchParams();
  if (patientUuid) params.set("patient", patientUuid);
  if (visitUuid) params.set("visit", visitUuid);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<LaboratoryWorkflowPayload>(
    `/openmrs/abikan-api/laboratory/order/${encodeURIComponent(orderUuid)}/workflow${suffix}`,
  );
}

export function collectLaboratorySample(
  orderUuid: string,
  input: {
    requestId: string;
    patientUuid?: string;
    sampleTypeId: string;
    sampleSourceId: string;
    receivedDate?: string;
    testIds: string[];
  },
): Promise<LaboratoryWorkflowPayload> {
  const suffix = input.patientUuid ? `?patient=${encodeURIComponent(input.patientUuid)}` : "";
  return readJson<LaboratoryWorkflowPayload>(
    `/openmrs/abikan-api/laboratory/order/${encodeURIComponent(orderUuid)}/workflow/collect${suffix}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function saveLaboratoryResults(
  orderUuid: string,
  input: {
    requestId: string;
    patientUuid?: string;
    accession?: string;
    results: Array<Record<string, string | boolean>>;
  },
): Promise<LaboratoryWorkflowPayload> {
  const suffix = input.patientUuid ? `?patient=${encodeURIComponent(input.patientUuid)}` : "";
  return readJson<LaboratoryWorkflowPayload>(
    `/openmrs/abikan-api/laboratory/order/${encodeURIComponent(orderUuid)}/workflow/results${suffix}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function validateLaboratoryResults(
  orderUuid: string,
  input: {
    requestId: string;
    patientUuid?: string;
    accession?: string;
    testSection?: string;
    testName?: string;
    results?: Array<Record<string, string>>;
    decision?: "accept" | "reject";
  },
): Promise<LaboratoryWorkflowPayload> {
  const suffix = input.patientUuid ? `?patient=${encodeURIComponent(input.patientUuid)}` : "";
  return readJson<LaboratoryWorkflowPayload>(
    `/openmrs/abikan-api/laboratory/order/${encodeURIComponent(orderUuid)}/workflow/validate${suffix}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function createLaboratoryOrders(
  patientUuid: string,
  input: {
    visitUuid: string;
    locationUuid: string;
    encounterUuid?: string;
    requestId: string;
    tests: Array<{ conceptUuid: string; name?: string; comment?: string }>;
  },
): Promise<LaboratoryOrderCreateResult> {
  return readJson<LaboratoryOrderCreateResult>(
    `/openmrs/abikan-api/laboratory/patient/${encodeURIComponent(patientUuid)}/orders`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function createLaboratoryDirectOrders(
  patientUuid: string,
  input: {
    visitUuid: string;
    locationUuid: string;
    encounterUuid?: string;
    requestId: string;
    indication?: string;
    tests: Array<{ conceptUuid: string; name?: string; comment?: string }>;
  },
): Promise<LaboratoryOrderCreateResult> {
  return readJson<LaboratoryOrderCreateResult>(
    `/openmrs/abikan-api/laboratory/patient/${encodeURIComponent(patientUuid)}/direct-orders`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function createExternalLaboratoryOrder(input: {
  requestId: string;
  buyerName: string;
  buyerPhone?: string;
  buyerSex?: string;
  buyerDob?: string;
  buyerAddress?: string;
  indication?: string;
  requestSource?: string;
  referrer?: string;
  externalId?: string;
  locationUuid?: string;
  tests: Array<{ conceptUuid: string; name?: string; comment?: string }>;
}): Promise<LaboratoryExternalOrderPayload> {
  return readJson<LaboratoryExternalOrderPayload>("/openmrs/abikan-api/laboratory/external-order", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
}

export function searchExternalLaboratoryPatients(
  query = "",
): Promise<LaboratoryExternalPatientSearchPayload> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<LaboratoryExternalPatientSearchPayload>(
    `/openmrs/abikan-api/laboratory/external-patients${suffix}`,
  );
}

export function fetchExternalLaboratoryPatient(
  externalId: string,
): Promise<LaboratoryExternalPatientPayload> {
  return readJson<LaboratoryExternalPatientPayload>(
    `/openmrs/abikan-api/laboratory/external-patient/${encodeURIComponent(externalId)}`,
  );
}

export function linkExternalLaboratoryPatient(
  externalId: string,
  patientUuid: string,
): Promise<LaboratoryExternalPatientPayload> {
  return readJson<LaboratoryExternalPatientPayload>(
    `/openmrs/abikan-api/laboratory/external-patient/${encodeURIComponent(externalId)}/link`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ patientUuid, confirm: true }),
    },
  );
}

export function fetchLinkedExternalLaboratoryOrders(
  patientUuid: string,
): Promise<LaboratoryLinkedExternalPayload> {
  return readJson<LaboratoryLinkedExternalPayload>(
    `/openmrs/abikan-api/laboratory/patient/${encodeURIComponent(patientUuid)}/linked-external`,
  );
}

export function fetchLaboratoryHistory(
  query: LaboratoryHistoryQuery = {},
): Promise<LaboratoryHistoryPayload> {
  const params = new URLSearchParams();
  const entries: Array<[keyof LaboratoryHistoryQuery, string | number | undefined]> = [
    ["q", query.q],
    ["from", query.from],
    ["to", query.to],
    ["requestSource", query.requestSource],
    ["patientType", query.patientType],
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
  return readJson<LaboratoryHistoryPayload>(`/openmrs/abikan-api/laboratory/history${suffix}`);
}

export function fetchHospitalLaboratoryTests(query = ""): Promise<LaboratoryHospitalTestsPayload> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<LaboratoryHospitalTestsPayload>(
    `/openmrs/abikan-api/laboratory/hospital-tests${suffix}`,
  );
}

export function searchMasterLaboratoryTests(query: string): Promise<LaboratoryMasterSearchPayload> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<LaboratoryMasterSearchPayload>(
    `/openmrs/abikan-api/laboratory/master-tests${suffix}`,
  );
}

export function enableHospitalLaboratoryTest(
  conceptUuid: string,
): Promise<LaboratoryHospitalTestMutationPayload> {
  return readJson<LaboratoryHospitalTestMutationPayload>(
    "/openmrs/abikan-api/laboratory/hospital-tests",
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ conceptUuid }),
    },
  );
}

export function disableHospitalLaboratoryTest(
  conceptUuid: string,
): Promise<LaboratoryHospitalTestMutationPayload> {
  return readJson<LaboratoryHospitalTestMutationPayload>(
    `/openmrs/abikan-api/laboratory/hospital-tests/${encodeURIComponent(conceptUuid)}/disable`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({}),
    },
  );
}

export function fetchCustomLaboratoryTests(): Promise<LaboratoryCustomTestsPayload> {
  return readJson<LaboratoryCustomTestsPayload>("/openmrs/abikan-api/laboratory/custom-tests");
}

export function createCustomLaboratoryTest(body: {
  name: string;
  price: number | null;
  columns: string[];
  properties: Array<{ name: string; values: string[] }>;
}): Promise<LaboratoryCustomTestCreatePayload> {
  return readJson<LaboratoryCustomTestCreatePayload>("/openmrs/abikan-api/laboratory/custom-tests", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchLaboratoryConsumables(query = ""): Promise<LaboratoryConsumablesPayload> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<LaboratoryConsumablesPayload>(`/openmrs/abikan-api/laboratory/inventory${suffix}`);
}

export function createLaboratoryConsumable(body: {
  name: string;
  kind: string;
  unit: string;
  onHand?: number;
  reorderLevel?: number;
  purchasePrice?: number | null;
  notes?: string;
}): Promise<LaboratoryConsumableMutationPayload> {
  return readJson<LaboratoryConsumableMutationPayload>("/openmrs/abikan-api/laboratory/inventory", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function adjustLaboratoryConsumable(
  id: string,
  body: {
    reason: string;
    note?: string;
    onHand?: number;
    delta?: number;
    direction?: string;
    purchasePrice?: number | null;
  },
): Promise<LaboratoryConsumableMutationPayload> {
  return readJson<LaboratoryConsumableMutationPayload>(
    `/openmrs/abikan-api/laboratory/inventory/${encodeURIComponent(id)}/adjust`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function fetchBloodBankUnits(query = "", status = ""): Promise<BloodBankUnitsPayload> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  if (status.trim()) {
    params.set("status", status.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson<BloodBankUnitsPayload>(`/openmrs/abikan-api/laboratory/blood-units${suffix}`);
}

export function receiveBloodBankUnit(body: {
  component: string;
  abo: string;
  rh: string;
  bagNumber: string;
  expiresOn: string;
  collectedOn?: string;
  volumeMl?: number | null;
  source?: string;
  notes?: string;
}): Promise<BloodBankUnitMutationPayload> {
  return readJson<BloodBankUnitMutationPayload>("/openmrs/abikan-api/laboratory/blood-units", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export interface LaboratoryReferenceRange {
  id: string;
  testName: string;
  specimen: string;
  resultType: string;
  purpose: string;
  low: string;
  high: string;
  unit: string;
  rangeText: string;
  ageText: string;
  ageMin: string;
  ageMinUnit: string;
  ageMax: string;
  ageMaxUnit: string;
  sex: string;
  appliesTo: string;
  method: string;
  descriptiveText: string;
  sourceTitle: string;
  sourcePublisher: string;
  sourceVersion: string;
  sourceUrl: string;
  sourceAccessed: string;
  limitations: string;
  conflictNote: string;
  status: string;
  statusLabel: string;
  usedOnResults: boolean;
  approvedBy?: string;
  approvedAt?: string;
}

export interface LaboratoryReferenceRangesPayload {
  status: string;
  items: LaboratoryReferenceRange[];
  proposed?: number;
  pendingReview?: number;
  approved?: number;
}

export function fetchReferenceRanges(query = "", status = ""): Promise<LaboratoryReferenceRangesPayload> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (status.trim()) params.set("status", status.trim());
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson(`/openmrs/abikan-api/laboratory/reference-ranges${suffix}`);
}

export function saveReferenceRange(body: {
  action: "save" | "submit" | "approve" | "inactivate" | "revise";
  id?: string;
  testName?: string;
  low?: string;
  high?: string;
  unit?: string;
  sex?: string;
  specimen?: string;
  ageMin?: string;
  ageMinUnit?: string;
  ageMax?: string;
  ageMaxUnit?: string;
  sourceTitle?: string;
  sourcePublisher?: string;
  sourceVersion?: string;
  sourceUrl?: string;
  method?: string;
  limitations?: string;
}): Promise<{ status: string; range: LaboratoryReferenceRange }> {
  return readJson("/openmrs/abikan-api/laboratory/reference-ranges", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function updateBloodBankUnitStatus(
  id: string,
  body: {
    status: string;
    patientUuid?: string;
    patientName?: string;
    discardReason?: string;
    notes?: string;
  },
): Promise<BloodBankUnitMutationPayload> {
  return readJson<BloodBankUnitMutationPayload>(
    `/openmrs/abikan-api/laboratory/blood-units/${encodeURIComponent(id)}/status`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    },
  );
}
