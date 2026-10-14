import { DRUG_OTHER_CONCEPT } from "../../config/clinicalConcepts.ts";
import type { ClinicalMedicationStatus, DrugOrderSummary } from "../../types";

export const FLEXIBLE_DOSING_INSTRUCTIONS_CLASS =
  "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions";

export type MedicationAdministrationMode = "HOME" | "HOSPITAL_FOLLOW_UP" | "INPATIENT";

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
}

interface DrugRef {
  uuid?: string;
  name?: string;
  display?: string;
  form?: string;
  strength?: string;
  concept?: NamedValue;
  dosageForm?: NamedValue;
  retired?: boolean;
}

export interface BahmniDrugOrderRaw {
  uuid?: string;
  action?: string;
  dateActivated?: string | number;
  dateStopped?: string | number | null;
  autoExpireDate?: string | number;
  duration?: number | string;
  durationUnits?: string;
  instructions?: string;
  drug?: DrugRef;
  drugNonCoded?: string;
  dosingInstructions?: DosingInstructions;
  drugOrder?: BahmniDrugOrderRaw;
  drugOrders?: BahmniDrugOrderRaw[];
  visitUuid?: string;
  visit?: { uuid?: string };
  encounter?: { visit?: { uuid?: string } };
  visitDrugOrders?: BahmniDrugOrderRaw[];
  results?: BahmniDrugOrderRaw[];
}

export interface DrugOrderConfigOption {
  name: string;
  frequencyPerDay?: number;
}

export interface DrugOrderConfig {
  doseUnits: DrugOrderConfigOption[];
  routes: DrugOrderConfigOption[];
  frequencies: DrugOrderConfigOption[];
  durationUnits: DrugOrderConfigOption[];
  dispensingUnits: DrugOrderConfigOption[];
  instructions: DrugOrderConfigOption[];
}

export interface DrugCatalogueHit {
  uuid: string;
  name: string;
  strength: string;
  form: string;
  genericName: string;
  conceptUuid?: string;
  price?: string;
  stockLabel?: string;
}

export interface PrescriptionDraftItem {
  id: string;
  drugUuid: string;
  drugName: string;
  dose: number;
  doseUnits: string;
  route: string;
  frequency: string;
  duration: number;
  durationUnits: string;
  quantity: number;
  quantityUnits: string;
  instructions: string;
  administrationMode: MedicationAdministrationMode;
  nonCoded?: boolean;
  conceptUuid?: string;
}

export interface PrescriptionInput {
  drugUuid: string;
  drugName?: string;
  dose: number | string;
  doseUnits: string;
  route: string;
  frequency: string;
  duration: number | string;
  durationUnits: string;
  quantity: number | string;
  quantityUnits: string;
  instructions?: string;
  administrationMode?: MedicationAdministrationMode;
}

export interface BahmniDrugOrderPayload {
  careSetting: "OUTPATIENT" | "INPATIENT";
  staffName?: string;
  drug?: { uuid: string };
  drugNonCoded?: string;
  concept?: { uuid: string };
  orderType: "Drug Order";
  dosingInstructionType: string;
  dosingInstructions: {
    dose: number;
    doseUnits: string;
    route: string;
    frequency: string;
    asNeeded: boolean;
    administrationInstructions?: string;
    quantity: number;
    quantityUnits: string;
    numberOfRefills: number;
  };
  duration: number;
  durationUnits: string;
}

function named(value: unknown): string {
  if (!value) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "object") {
    const row = value as NamedValue;
    return row.name || row.display || "";
  }
  return "";
}

function flattenDrugOrder(raw: BahmniDrugOrderRaw): BahmniDrugOrderRaw {
  const nested = raw.drugOrder;
  if (!nested) {
    return raw;
  }
  return {
    ...nested,
    ...raw,
    uuid: raw.uuid || nested.uuid,
    action: raw.action || nested.action,
    dateActivated: raw.dateActivated ?? nested.dateActivated,
    dateStopped: raw.dateStopped ?? nested.dateStopped,
    autoExpireDate: raw.autoExpireDate ?? nested.autoExpireDate,
    duration: raw.duration ?? nested.duration,
    durationUnits: raw.durationUnits || nested.durationUnits,
    instructions: raw.instructions || nested.instructions,
    drug: raw.drug || nested.drug,
    drugNonCoded: raw.drugNonCoded || nested.drugNonCoded,
    dosingInstructions: raw.dosingInstructions || nested.dosingInstructions,
    visitUuid: raw.visitUuid || nested.visitUuid,
    visit: raw.visit || nested.visit,
    encounter: raw.encounter || nested.encounter,
  };
}

function visitUuidOf(row: BahmniDrugOrderRaw): string {
  return (row.visitUuid || row.visit?.uuid || row.encounter?.visit?.uuid || "").trim();
}

function stampVisit(row: BahmniDrugOrderRaw, inherited: string): BahmniDrugOrderRaw {
  const visitUuid = visitUuidOf(row) || inherited;
  return visitUuid ? { ...row, visitUuid } : row;
}

function expandOrder(row: BahmniDrugOrderRaw, inherited = ""): BahmniDrugOrderRaw[] {
  const visitUuid = visitUuidOf(row) || inherited;
  if (Array.isArray(row.drugOrders) && row.drugOrders.length > 0) {
    return row.drugOrders.flatMap((item) => expandOrder(item, visitUuid));
  }
  if (
    Array.isArray(row.visitDrugOrders) &&
    !row.uuid &&
    !row.drugOrder &&
    !row.drug &&
    !row.drugNonCoded
  ) {
    return row.visitDrugOrders.flatMap((item) => expandOrder(item, visitUuid));
  }
  if (row.uuid || row.drugOrder || row.drug || row.drugNonCoded) {
    return [stampVisit(row, visitUuid)];
  }
  return [];
}

export function extractDrugOrderRows(payload: unknown): BahmniDrugOrderRaw[] {
  if (Array.isArray(payload)) {
    return payload.flatMap((item) =>
      item && typeof item === "object" ? expandOrder(item as BahmniDrugOrderRaw) : [],
    );
  }
  if (!payload || typeof payload !== "object") {
    return [];
  }
  const row = payload as BahmniDrugOrderRaw;
  if (Array.isArray(row.visitDrugOrders)) {
    return row.visitDrugOrders.flatMap((item) => expandOrder(item));
  }
  if (Array.isArray(row.results)) {
    return row.results.flatMap((item) => expandOrder(item));
  }
  return expandOrder(row);
}

function toMillis(value: string | number | null | undefined): number | null {
  if (value === undefined || value === null || value === "") {
    return null;
  }
  const date = typeof value === "number" ? new Date(value) : new Date(value);
  const time = date.getTime();
  return Number.isNaN(time) ? null : time;
}

function looksLikeTablet(value: string): boolean {
  const text = value.trim().toLowerCase().replace(/\./g, "");
  return text === "tablet" || text === "tablets" || text === "tablet(s)" || text === "tab" || text === "tabs";
}

function genericDoseUnit(value: string): boolean {
  const text = value.trim().toLowerCase().replace(/\./g, "").replace("(s)", "");
  return looksLikeTablet(text) || text === "unit" || text === "units";
}

export function dosingUnitForForm(form: string, options: Array<{ name: string }>): string {
  const names = options.map((item) => item.name).filter(Boolean);
  const wanted = form.trim();
  const recognised = (name: string) =>
    names.find((option) => option.toLowerCase().replace(/\(s\)$/, "").replace(/s$/, "") === name);
  if (wanted && wanted !== "—") {
    const exact = names.find((name) => name.toLowerCase() === wanted.toLowerCase());
    if (exact) {
      return exact;
    }
    const stem = wanted.toLowerCase().replace(/\(s\)$/, "").replace(/s$/, "");
    const stemmed = names.find((name) => name.toLowerCase().replace(/\(s\)$/, "").replace(/s$/, "") === stem);
    if (stemmed) {
      return stemmed;
    }
    if (!looksLikeTablet(wanted)) {
      return recognised("unit") || recognised("milliliter") || recognised("ml") || names[0] || "Unit";
    }
  }
  return names.find((name) => looksLikeTablet(name)) || names[0] || "Tablet";
}

export function displayedDoseUnit(saved: string, form: string): string {
  const chosen = form.trim();
  const current = saved.trim();
  if (!chosen || chosen === "—") {
    return current;
  }
  if (looksLikeTablet(chosen)) {
    return current || chosen;
  }
  if (!current || genericDoseUnit(current)) {
    return chosen;
  }
  return current;
}

function text(value: number | string | undefined): string {
  if (value === undefined || value === null || value === "") {
    return "";
  }
  return String(value);
}

function administrationData(value: string | undefined): {
  instructions: string;
  administrationMode?: MedicationAdministrationMode;
} {
  if (!value) {
    return { instructions: "" };
  }
  try {
    const parsed = JSON.parse(value) as {
      instructions?: unknown;
      administrationMode?: unknown;
    };
    const mode =
      parsed.administrationMode === "HOME" ||
      parsed.administrationMode === "HOSPITAL_FOLLOW_UP" ||
      parsed.administrationMode === "INPATIENT"
        ? parsed.administrationMode
        : undefined;
    return {
      instructions: typeof parsed.instructions === "string" ? parsed.instructions : value,
      administrationMode: mode,
    };
  } catch {
    return { instructions: value };
  }
}

export function clinicalMedicationStatus(
  raw: BahmniDrugOrderRaw,
  now = Date.now(),
): ClinicalMedicationStatus {
  const action = String(raw.action || "").toUpperCase();
  if (raw.dateStopped || action === "DISCONTINUE") {
    return "Stopped";
  }
  const expire = toMillis(raw.autoExpireDate ?? undefined);
  if (expire != null && expire < now) {
    return "Expired";
  }
  return "Ordered";
}

export function mapClinicalMedication(
  raw: BahmniDrugOrderRaw,
  now = Date.now(),
): DrugOrderSummary | null {
  const order = flattenDrugOrder(raw);
  const dosing = order.dosingInstructions ?? {};
  const drugName =
    order.drug?.name || order.drug?.display || order.drugNonCoded || "";
  if (!order.uuid && !drugName) {
    return null;
  }
  const form = named(order.drug?.dosageForm) || order.drug?.form || "";
  const doseUnit = displayedDoseUnit(dosing.doseUnits || "", form);
  const quantityUnit = displayedDoseUnit(dosing.quantityUnits || "", form);
  const doseParts = [text(dosing.dose), doseUnit].filter(Boolean);
  const durationParts = [text(order.duration), order.durationUnits || ""].filter(Boolean);
  const status = clinicalMedicationStatus(order, now);
  const dose = doseParts.join(" ") || "—";
  const route = dosing.route || "—";
  const frequency = dosing.frequency || "—";
  const duration = durationParts.join(" ") || "—";
  const quantityText = [text(dosing.quantity), quantityUnit].filter(Boolean).join(" ");
  const data = administrationData(dosing.administrationInstructions || order.instructions);
  const instructions = data.instructions;
  return {
    uuid: order.uuid || drugName,
    display: drugName || "Medication",
    drugName: drugName || "Medication",
    dose,
    route,
    frequency,
    duration,
    quantity: quantityText,
    instructions,
    administrationMode: data.administrationMode,
    status,
    visitUuid: visitUuidOf(order),
  };
}

export interface DoseAdministration {
  status: string;
  outcome?: string;
}

export interface OrderAdministration {
  orderUuid: string;
  slots: DoseAdministration[];
}

function doseStillOpen(slot: DoseAdministration): boolean {
  const outcome = (slot.outcome || "").toLowerCase();
  if (outcome === "not-done" || outcome === "refused" || outcome === "held") {
    return true;
  }
  const status = slot.status.toUpperCase();
  if (status === "SCHEDULED" || status === "MISSED" || status === "NOT_DONE") {
    return true;
  }
  if (status === "COMPLETED" || status === "STOPPED") {
    return false;
  }
  return outcome !== "given";
}

function inpatientOrderStillCurrent(
  row: DrugOrderSummary,
  administration: OrderAdministration[] | null | undefined,
): boolean {
  if (row.status === "Stopped") {
    return false;
  }
  if (row.administrationMode && row.administrationMode !== "INPATIENT") {
    return true;
  }
  if (!administration) {
    return true;
  }
  const record = administration.find((item) => item.orderUuid === row.uuid);
  if (!record || record.slots.length === 0) {
    return true;
  }
  return record.slots.some((slot) => doseStillOpen(slot));
}

export function medicationsForChart(
  rows: DrugOrderSummary[],
  scope: {
    visitUuid: string;
    inpatient: boolean;
    administration?: OrderAdministration[] | null;
  },
): DrugOrderSummary[] {
  const visitUuid = scope.visitUuid.trim();
  if (!visitUuid) {
    return [];
  }
  const onVisit = rows.filter((row) => (row.visitUuid || "") === visitUuid);
  if (!scope.inpatient) {
    return onVisit;
  }
  return onVisit.filter((row) => inpatientOrderStillCurrent(row, scope.administration));
}

export function mergeClinicalMedications(
  groups: BahmniDrugOrderRaw[][],
  now = Date.now(),
): DrugOrderSummary[] {
  const seen = new Set<string>();
  const mapped: Array<{ row: DrugOrderSummary; activated: number }> = [];
  groups.flat().forEach((raw) => {
    const order = flattenDrugOrder(raw);
    const summary = mapClinicalMedication(order, now);
    if (!summary) {
      return;
    }
    if (seen.has(summary.uuid)) {
      return;
    }
    seen.add(summary.uuid);
    mapped.push({
      row: summary,
      activated: toMillis(order.dateActivated) ?? 0,
    });
  });
  return mapped
    .sort((left, right) => right.activated - left.activated)
    .map((item) => item.row);
}

function optionNames(rows: unknown): DrugOrderConfigOption[] {
  if (!Array.isArray(rows)) {
    return [];
  }
  const mapped: DrugOrderConfigOption[] = [];
  rows.forEach((item) => {
    if (!item || typeof item !== "object") {
      return;
    }
    const row = item as { name?: string; frequencyPerDay?: number };
    if (!row.name) {
      return;
    }
    mapped.push(
      typeof row.frequencyPerDay === "number"
        ? { name: row.name, frequencyPerDay: row.frequencyPerDay }
        : { name: row.name },
    );
  });
  return mapped;
}

export function mapDrugOrderConfig(payload: unknown): DrugOrderConfig {
  const row = (payload && typeof payload === "object" ? payload : {}) as Record<string, unknown>;
  return {
    doseUnits: optionNames(row.doseUnits),
    routes: optionNames(row.routes),
    frequencies: optionNames(row.frequencies),
    durationUnits: optionNames(row.durationUnits),
    dispensingUnits: optionNames(row.dispensingUnits),
    instructions: optionNames(row.dosingInstructions),
  };
}

export function mapDrugCatalogueHits(payload: unknown): DrugCatalogueHit[] {
  const rows =
    payload && typeof payload === "object" && Array.isArray((payload as { results?: unknown[] }).results)
      ? ((payload as { results: DrugRef[] }).results ?? [])
      : Array.isArray(payload)
        ? (payload as DrugRef[])
        : [];
  return rows
    .filter((row) => row.uuid && row.name && !row.retired)
    .map((row) => ({
      uuid: row.uuid as string,
      name: row.name as string,
      strength: row.strength || "—",
      form: named(row.dosageForm) || named(row.form) || "—",
      genericName: named(row.concept) || "—",
      conceptUuid: row.concept?.uuid || "",
    }));
}

export function suggestedQuantity(
  dose: number,
  frequencyPerDay: number | undefined,
  duration: number,
  durationUnits: string,
): number | null {
  if (!Number.isFinite(dose) || dose <= 0 || !Number.isFinite(duration) || duration <= 0) {
    return null;
  }
  const times = frequencyPerDay && frequencyPerDay > 0 ? frequencyPerDay : 1;
  const unit = durationUnits.toLowerCase();
  let days = duration;
  if (unit.startsWith("week")) {
    days = duration * 7;
  } else if (!unit.startsWith("day")) {
    return null;
  }
  return dose * times * days;
}

export function typedMedicineName(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function validatePrescription(
  input: PrescriptionInput,
  config: DrugOrderConfig,
): string[] {
  const errors: string[] = [];
  const named = typedMedicineName(input.drugName || "");
  if (!input.drugUuid.trim() && named.length < 3) {
    errors.push("Choose a medicine from the list, or type the medicine name.");
  }
  if (!config.routes.some((item) => item.name === input.route)) {
    errors.push("Choose how the medicine is given.");
  }
  if (!config.frequencies.some((item) => item.name === input.frequency)) {
    errors.push("Choose how often the medicine is given.");
  }
  if (!Number.isFinite(Number(input.duration)) || Number(input.duration) <= 0) {
    errors.push("Enter how long the medicine should be taken.");
  }
  if (!Number.isFinite(Number(input.quantity)) || Number(input.quantity) <= 0) {
    errors.push("Enter the quantity.");
  }
  if (!config.durationUnits.some((item) => item.name === input.durationUnits)) {
    errors.push("Choose a duration from the list.");
  }
  if (!input.instructions?.trim()) {
    errors.push("Enter instructions for this medicine.");
  }
  return errors;
}

export function careSettingForVisitType(visitType?: string): "OUTPATIENT" | "INPATIENT" {
  return visitType === "IPD" ? "INPATIENT" : "OUTPATIENT";
}

export function buildDrugOrderPayload(
  draft: PrescriptionDraftItem,
  careSetting: "OUTPATIENT" | "INPATIENT" = "OUTPATIENT",
): BahmniDrugOrderPayload {
  const instructions = draft.instructions.trim();
  const named = typedMedicineName(draft.drugName);
  const coded = Boolean(draft.drugUuid.trim()) && !draft.nonCoded;
  return {
    careSetting,
    staffName: named || "Medication",
    ...(coded
      ? {
          drug: { uuid: draft.drugUuid },
          ...(draft.conceptUuid ? { concept: { uuid: draft.conceptUuid } } : {}),
        }
      : { drugNonCoded: named, concept: { uuid: DRUG_OTHER_CONCEPT.uuid } }),
    orderType: "Drug Order",
    dosingInstructionType: FLEXIBLE_DOSING_INSTRUCTIONS_CLASS,
    dosingInstructions: {
      dose: draft.dose,
      doseUnits: draft.doseUnits,
      route: draft.route,
      frequency: draft.frequency,
      asNeeded: false,
      administrationInstructions: instructions
        ? JSON.stringify({
            instructions,
            administrationMode: draft.administrationMode,
          })
        : undefined,
      quantity: draft.quantity,
      quantityUnits: draft.quantityUnits,
      numberOfRefills: 0,
    },
    duration: draft.duration,
    durationUnits: draft.durationUnits,
  };
}
