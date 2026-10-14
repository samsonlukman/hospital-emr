import type { PatientIdentity, PharmacyOrderStatus, PharmacyOrderSummary } from "../../types";
import { formatClinicalWhen } from "../../utils/datetime";
import { openmrsGet } from "./client";
import { fetchPatientIdentity, parsePatientDisplay } from "./clinicalPatient";
import { displayedDoseUnit } from "./drugOrderMap";
import { attachDosageForms } from "./drugOrders";

interface NamedValue {
  uuid?: string;
  name?: string;
  display?: string;
}

interface DosingInstructions {
  dose?: number | string;
  doseUnits?: string;
  route?: string;
  frequency?: string;
  asNeeded?: boolean;
  administrationInstructions?: string;
  quantity?: number | string;
  quantityUnits?: string;
  numberOfRefills?: number;
}

interface DrugRef {
  uuid?: string;
  name?: string;
  display?: string;
  form?: string;
  strength?: string;
}

interface BahmniDrugOrderResponse {
  uuid?: string;
  orderNumber?: string;
  action?: string;
  careSetting?: string;
  dateActivated?: string | number;
  dateStopped?: string | number | null;
  autoExpireDate?: string | number;
  scheduledDate?: string | number;
  effectiveStartDate?: string | number;
  effectiveStopDate?: string | number;
  duration?: number | string;
  durationUnits?: string;
  instructions?: string;
  commentToFulfiller?: string;
  creatorName?: string;
  encounterUuid?: string;
  drug?: DrugRef;
  drugNonCoded?: string;
  dosingInstructions?: DosingInstructions;
  provider?: string | NamedValue;
  patient?: { uuid?: string; display?: string };
  patientUuid?: string;
  orderAttributes?: Array<{ name?: string; value?: string | boolean }> | null;
  drugOrder?: BahmniDrugOrderResponse;
}

interface PatientHint {
  uuid?: string;
  name?: string;
  mrn?: string;
}

function flattenActiveOrder(raw: BahmniDrugOrderResponse): BahmniDrugOrderResponse {
  const nested = raw.drugOrder;
  if (!nested) {
    return raw;
  }
  return {
    ...nested,
    ...raw,
    uuid: raw.uuid || nested.uuid,
    orderNumber: raw.orderNumber || nested.orderNumber,
    action: raw.action || nested.action,
    careSetting: raw.careSetting || nested.careSetting,
    dateActivated: raw.dateActivated ?? nested.dateActivated,
    dateStopped: raw.dateStopped ?? nested.dateStopped,
    autoExpireDate: raw.autoExpireDate ?? nested.autoExpireDate,
    effectiveStartDate: raw.effectiveStartDate ?? nested.effectiveStartDate,
    effectiveStopDate: raw.effectiveStopDate ?? nested.effectiveStopDate,
    duration: raw.duration ?? nested.duration,
    durationUnits: raw.durationUnits || nested.durationUnits,
    instructions: raw.instructions || nested.instructions,
    creatorName: raw.creatorName || nested.creatorName,
    encounterUuid: raw.encounterUuid || nested.encounterUuid,
    drug: raw.drug || nested.drug,
    drugNonCoded: raw.drugNonCoded || nested.drugNonCoded,
    dosingInstructions: raw.dosingInstructions || nested.dosingInstructions,
    provider: raw.provider || nested.provider,
    patient: raw.patient || nested.patient,
    patientUuid: raw.patientUuid || nested.patientUuid,
    orderAttributes: raw.orderAttributes ?? nested.orderAttributes,
  };
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

function text(value: number | string | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
}

function parseInstructions(raw: string | undefined): string {
  if (!raw) {
    return "";
  }
  try {
    const parsed = JSON.parse(raw) as { instructions?: string };
    if (parsed.instructions) {
      return parsed.instructions;
    }
  } catch {
    /* plain text */
  }
  return raw;
}

function isDispensed(raw: BahmniDrugOrderResponse): boolean {
  return (raw.orderAttributes ?? []).some((item) => {
    const name = (item.name || "").toLowerCase();
    if (name !== "dispensed") {
      return false;
    }
    const value = item.value;
    if (typeof value === "boolean") {
      return value;
    }
    const textValue = String(value || "").toLowerCase();
    return textValue === "true" || textValue === "yes" || textValue === "dispensed";
  });
}

function statusOf(raw: BahmniDrugOrderResponse, dispensed: boolean): PharmacyOrderStatus {
  if (dispensed) {
    return "Dispensed";
  }
  if (raw.dateStopped || raw.action === "DISCONTINUE") {
    return "Stopped";
  }
  return "Ordered";
}

function applyPatientHint(
  mapped: PharmacyOrderSummary,
  hint?: PatientHint,
): PharmacyOrderSummary {
  if (!hint) {
    return mapped;
  }
  return {
    ...mapped,
    patientUuid: mapped.patientUuid || hint.uuid || "",
    patientName:
      mapped.patientName && mapped.patientName !== "Unknown patient"
        ? mapped.patientName
        : hint.name || mapped.patientName,
    mrn: mapped.mrn && mapped.mrn !== "—" ? mapped.mrn : hint.mrn || mapped.mrn,
  };
}

export function mapPharmacyOrder(
  raw: BahmniDrugOrderResponse,
  hint?: PatientHint,
): PharmacyOrderSummary {
  const order = flattenActiveOrder(raw);
  const dosing = order.dosingInstructions ?? {};
  const parsed = parsePatientDisplay(order.patient?.display || "");
  const dispensed = isDispensed(order);
  const duration =
    order.duration !== undefined && order.duration !== null && order.duration !== ""
      ? `${order.duration} ${order.durationUnits || ""}`.trim()
      : "—";
  return applyPatientHint(
    {
      uuid: order.uuid || "",
      orderNumber: order.orderNumber || "—",
      drugName: order.drug?.name || order.drug?.display || order.drugNonCoded || "Medication",
      strength: order.drug?.strength || "—",
      dose: text(dosing.dose),
      doseUnits: displayedDoseUnit(dosing.doseUnits || "", order.drug?.form || ""),
      route: dosing.route || "—",
      frequency: dosing.frequency || "—",
      duration,
      quantity: text(dosing.quantity),
      quantityUnits: displayedDoseUnit(dosing.quantityUnits || "", order.drug?.form || ""),
      instructions:
        parseInstructions(dosing.administrationInstructions) || order.instructions || "",
      patientUuid: order.patientUuid || order.patient?.uuid || hint?.uuid || "",
      patientName: parsed.name || hint?.name || "Unknown patient",
      mrn: parsed.mrn !== "—" ? parsed.mrn : hint?.mrn || parsed.mrn,
      ordered: formatClinicalWhen(order.dateActivated || order.effectiveStartDate),
      provider: displayOf(order.provider) || order.creatorName || "—",
      careSetting: order.careSetting || "—",
      action: order.action || "—",
      dateStopped: formatClinicalWhen(order.dateStopped ?? undefined),
      autoExpireDate: formatClinicalWhen(order.autoExpireDate),
      dispensed,
      status: statusOf(order, dispensed),
    },
    hint,
  );
}

async function identityHint(patientUuid: string): Promise<PatientHint> {
  try {
    const identity: PatientIdentity = await fetchPatientIdentity(patientUuid);
    return { uuid: identity.uuid, name: identity.name, mrn: identity.mrn };
  } catch {
    return { uuid: patientUuid };
  }
}

export async function fetchPharmacyOrders(patientUuid: string): Promise<PharmacyOrderSummary[]> {
  const query = new URLSearchParams({ patientUuid });
  const response = await openmrsGet<
    BahmniDrugOrderResponse[] | { results?: BahmniDrugOrderResponse[] }
  >(`/openmrs/ws/rest/v1/bahmnicore/drugOrders/active?${query.toString()}`);
  const rows = Array.isArray(response) ? response : response.results ?? [];
  if (rows.length === 0) {
    return [];
  }
  await attachDosageForms(rows);
  const hint = await identityHint(patientUuid);
  return rows.map((row) => mapPharmacyOrder(row, hint)).filter((row) => row.uuid);
}

export async function fetchPharmacyQueue(): Promise<PharmacyOrderSummary[]> {
  const query = new URLSearchParams({
    includeInactive: "false",
    v: "custom:(uuid,patient:(uuid,display))",
    limit: "100",
  });
  const data = await openmrsGet<{
    results?: Array<{ patient?: { uuid?: string; display?: string } }>;
  }>(`/openmrs/ws/rest/v1/visit?${query.toString()}`);
  const patients = new Map<string, string>();
  for (const visit of data.results ?? []) {
    const uuid = visit.patient?.uuid;
    if (uuid && !patients.has(uuid)) {
      patients.set(uuid, visit.patient?.display || "");
    }
  }
  const batches = await Promise.allSettled(
    [...patients.entries()].map(async ([uuid, display]) => {
      const orders = await fetchPharmacyOrders(uuid);
      const parsed = parsePatientDisplay(display);
      return orders.map((order) =>
        applyPatientHint(order, {
          uuid,
          name: parsed.name,
          mrn: parsed.mrn,
        }),
      );
    }),
  );
  return batches.flatMap((result) => (result.status === "fulfilled" ? result.value : []));
}

export async function fetchPharmacyOrder(
  orderUuid: string,
): Promise<PharmacyOrderSummary | null> {
  try {
    const response = await openmrsGet<BahmniDrugOrderResponse>(
      `/openmrs/ws/rest/v1/bahmnicore/drugOrders/${encodeURIComponent(orderUuid)}`,
    );
    let hint: PatientHint | undefined;
    try {
      const core = await openmrsGet<{
        patient?: { uuid?: string; display?: string };
      }>(
        `/openmrs/ws/rest/v1/order/${encodeURIComponent(orderUuid)}?v=custom:(uuid,patient:(uuid,display))`,
      );
      const parsed = parsePatientDisplay(core.patient?.display || "");
      hint = {
        uuid: core.patient?.uuid,
        name: parsed.name,
        mrn: parsed.mrn,
      };
      if (hint.uuid) {
        const identity = await identityHint(hint.uuid);
        hint = { ...hint, ...identity, uuid: identity.uuid || hint.uuid };
      }
    } catch {
      hint = undefined;
    }
    await attachDosageForms([response]);
    const mapped = mapPharmacyOrder(response, hint);
    return mapped.uuid ? mapped : null;
  } catch {
    return null;
  }
}

export function pharmacyStatusTone(
  status: PharmacyOrderStatus,
): "info" | "neutral" | "success" {
  if (status === "Dispensed") {
    return "success";
  }
  if (status === "Stopped") {
    return "neutral";
  }
  return "info";
}
