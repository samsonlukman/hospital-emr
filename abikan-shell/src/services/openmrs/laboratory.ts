import type { LabOrderSummary, LabResultSummary } from "../../types";
import { formatClinicalWhen } from "../../utils/datetime";
import { PatientAccountRequestError } from "../patientAccount";
import { fetchLaboratoryOrderDetail, fetchReleasedLaboratoryResults } from "../laboratoryBilling";
import { openmrsGet } from "./client";
import { parsePatientDisplay } from "./clinicalPatient";
import { markAmbiguousLabResults } from "./laboratoryResult";

export const LAB_ORDER_TYPE_UUID = "d3560b17-5e07-11ef-8f7c-0242ac120002";

interface NamedValue {
  uuid?: string;
  name?: string;
  display?: string;
}

interface BahmniOrderResponse {
  uuid?: string;
  orderUuid?: string;
  orderNumber?: string;
  dateCreated?: string;
  dateActivated?: string;
  orderDate?: string;
  urgency?: string;
  commentToFulfiller?: string;
  accessionNumber?: string;
  provider?: string | NamedValue;
  concept?: NamedValue;
  conceptName?: string;
  patientUuid?: string;
  patient?: { uuid?: string; display?: string };
}

interface LabOrderResultsResponse {
  results?: Array<{
    orderUuid?: string;
    accessionUuid?: string;
    accessionDateTime?: string | number;
    testName?: string;
    panelName?: string;
    result?: string;
    testUnitOfMeasurement?: string;
    minNormal?: number | string | null;
    maxNormal?: number | string | null;
    abnormal?: boolean | null;
    notes?: string;
    provider?: string;
    resultDateTime?: string | number;
  }>;
}

function displayOf(value: string | NamedValue | undefined): string {
  if (!value) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  return value.display || value.name || "";
}

function mapOrder(raw: BahmniOrderResponse): LabOrderSummary {
  const patientDisplay = raw.patient?.display || "";
  const parsed = parsePatientDisplay(patientDisplay);
  return {
    uuid: raw.uuid || raw.orderUuid || "",
    orderNumber: raw.orderNumber || "—",
    testName: raw.conceptName || displayOf(raw.concept) || "Laboratory order",
    patientUuid: raw.patientUuid || raw.patient?.uuid || "",
    patientName: parsed.name || "Unknown patient",
    mrn: parsed.mrn,
    ordered: formatClinicalWhen(raw.dateActivated || raw.dateCreated || raw.orderDate),
    urgency: raw.urgency === "STAT" ? "STAT" : raw.urgency || "Routine",
    comment: raw.commentToFulfiller || "",
    provider: displayOf(raw.provider) || "—",
    accession: raw.accessionNumber || "—",
  };
}

function rangeValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
}

function mapResult(raw: NonNullable<LabOrderResultsResponse["results"]>[number]): LabResultSummary {
  return {
    orderUuid: raw.orderUuid || "",
    accessionUuid: raw.accessionUuid || "",
    testName: raw.testName || "Laboratory result",
    panelName: raw.panelName || "",
    result: raw.result || "—",
    unit: raw.testUnitOfMeasurement || "",
    minNormal: rangeValue(raw.minNormal),
    maxNormal: rangeValue(raw.maxNormal),
    abnormal: typeof raw.abnormal === "boolean" ? raw.abnormal : null,
    notes: raw.notes || "",
    provider: raw.provider || "—",
    resultAt: formatClinicalWhen(raw.resultDateTime),
    accessionAt: formatClinicalWhen(raw.accessionDateTime),
    mappingStatus: "unique",
    mappingMessage: "",
  };
}

export async function fetchLabOrders(patientUuid: string): Promise<LabOrderSummary[]> {
  const query = new URLSearchParams({
    patientUuid,
    orderTypeUuid: LAB_ORDER_TYPE_UUID,
  });
  const response = await openmrsGet<BahmniOrderResponse[] | { results?: BahmniOrderResponse[] }>(
    `/openmrs/ws/rest/v1/bahmnicore/orders?${query.toString()}`,
  );
  const rows = Array.isArray(response) ? response : response.results ?? [];
  return rows.map(mapOrder).filter((row) => row.uuid);
}

export async function fetchLabOrder(
  orderUuid: string,
  patientUuid?: string,
  visitUuid?: string,
): Promise<LabOrderSummary | null> {
  const selected = orderUuid.trim();
  if (!selected) {
    return null;
  }
  try {
    const body = await fetchLaboratoryOrderDetail(selected, patientUuid, visitUuid);
    const raw = body.order;
    if (!raw?.uuid) {
      return null;
    }
    return {
      uuid: raw.uuid,
      orderNumber: raw.orderNumber || "—",
      testName: raw.testName || "Laboratory order",
      patientUuid: raw.patientUuid || "",
      visitUuid: raw.visitUuid || "",
      patientName: raw.patientName || "Unknown patient",
      mrn: raw.mrn || "",
      age: raw.age || "",
      ordered: formatClinicalWhen(raw.ordered),
      urgency: raw.urgency === "STAT" ? "STAT" : raw.urgency || "Routine",
      comment: raw.comment || "",
      provider: raw.provider || "—",
      accession: raw.accession || "—",
    };
  } catch (error) {
    if (error instanceof PatientAccountRequestError) {
      if (error.status === 404 && error.code === "order_not_found") {
        return null;
      }
      if (error.status === 409) {
        throw error;
      }
    }
    throw error;
  }
}

export async function fetchLabResults(patientUuid: string): Promise<LabResultSummary[]> {
  const query = new URLSearchParams({ patientUuid });
  const [response, released] = await Promise.all([
    openmrsGet<LabOrderResultsResponse>(
      `/openmrs/ws/rest/v1/bahmnicore/labOrderResults?${query.toString()}`,
    ),
    fetchReleasedLaboratoryResults(patientUuid).catch(() => ({ results: [] })),
  ]);
  const sourceRows = response.results ?? [];
  const releasedRows = (released.results ?? []) as NonNullable<LabOrderResultsResponse["results"]>;
  const releasedOrders = new Set(releasedRows.map((row) => `${row.orderUuid}:${row.testName}`));
  const rows = [
    ...sourceRows.filter((row) => !releasedOrders.has(`${row.orderUuid}:${row.testName}`)),
    ...releasedRows,
  ];
  return markAmbiguousLabResults(rows.map(mapResult));
}

export function resultFlag(result: LabResultSummary): string {
  if (result.abnormal === true) {
    return "Abnormal";
  }
  if (result.abnormal === false && result.result !== "—") {
    return "Normal";
  }
  return "—";
}
