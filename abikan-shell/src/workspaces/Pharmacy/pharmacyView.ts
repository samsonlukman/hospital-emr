import type {
  PharmacyAdjustDraft,
  PharmacyAdjustLineDraft,
  PharmacyCatalogueDraft,
  PharmacyCatalogueItem,
  PharmacyCatalogueLineDraft,
  PharmacyInventoryItem,
  PharmacyPrescription,
  PharmacyReceiveDraft,
  PharmacyReceiveLineDraft,
} from "../../types/pharmacy";

export type PharmacyView =
  | "dashboard"
  | "prescriptions"
  | "new-sale"
  | "ready"
  | "sales-history"
  | "catalogue"
  | "pricing"
  | "inventory";

export function pharmacyViewFromNav(navItemId: string | null): PharmacyView {
  if (navItemId === "ready") {
    // Ready-to-dispense is handled inside Prescriptions → detail, not a separate desk.
    return "prescriptions";
  }
  if (
    navItemId === "prescriptions" ||
    navItemId === "new-sale" ||
    navItemId === "sales-history" ||
    navItemId === "catalogue" ||
    navItemId === "pricing" ||
    navItemId === "inventory"
  ) {
    return navItemId;
  }
  if (navItemId === "dispensed") {
    return "sales-history";
  }
  return "dashboard";
}

export function matchesCatalogueSearch(row: PharmacyCatalogueItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return [row.name, row.hospitalName, row.listedAs, row.brandName, row.strength, row.form].some((value) =>
    (value || "").toLowerCase().includes(needle),
  );
}

export function catalogueStockLabel(row: Pick<PharmacyCatalogueItem, "stockOnHand" | "stockUnits">): string {
  const qty = Number(row.stockOnHand);
  if (!Number.isFinite(qty) || qty <= 0) {
    return "None in stock";
  }
  const units = row.stockUnits || "";
  const qtyText = String(qty).replace(/\.0$/, "");
  return units ? `${qtyText} in stock · ${units}` : `${qtyText} in stock`;
}

export const UNLISTED_DOSAGE_FORM = "Not listed";

export function dosageFormChoices(forms: string[], current = ""): string[] {
  const extras = ["Consumables"];
  const seen = new Set(forms.map((form) => form.trim().toLowerCase()).filter(Boolean));
  const choices = forms.map((form) => form.trim()).filter(Boolean);
  for (const extra of extras) {
    if (!seen.has(extra.toLowerCase())) {
      choices.push(extra);
      seen.add(extra.toLowerCase());
    }
  }
  const currentForm = current.trim();
  if (currentForm && !seen.has(currentForm.toLowerCase()) && !isUnlistedDosageForm(currentForm)) {
    choices.push(currentForm);
    seen.add(currentForm.toLowerCase());
  }
  if (!seen.has(UNLISTED_DOSAGE_FORM.toLowerCase())) {
    choices.push(UNLISTED_DOSAGE_FORM);
  }
  return choices;
}

export function isUnlistedDosageForm(form: string): boolean {
  return form.trim().toLowerCase() === UNLISTED_DOSAGE_FORM.toLowerCase();
}

export function resolvedDosageForm(form: string, customForm = ""): string {
  if (isUnlistedDosageForm(form)) {
    return customForm.trim();
  }
  return form.trim();
}

export function emptyCatalogueDraft(): PharmacyCatalogueDraft {
  return {
    name: "",
    brandName: "",
    manufacturer: "",
    strength: "",
    form: "Tablet",
    customForm: "",
    price: "100",
    available: true,
    conceptUuid: "",
    genericName: "",
  };
}

export function emptyCatalogueLine(form = "Tablet"): PharmacyCatalogueLineDraft {
  return {
    key: `cat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    ...emptyCatalogueDraft(),
    form,
    fieldErrors: {},
  };
}

export function catalogueLineErrors(line: PharmacyCatalogueLineDraft): PharmacyCatalogueLineDraft["fieldErrors"] {
  const errors: PharmacyCatalogueLineDraft["fieldErrors"] = {};
  if (line.name.trim().length < 3) {
    errors.name = "Enter the medicine or product name.";
  }
  if (!line.conceptUuid.trim()) {
    errors.generic = "Search and select a generic.";
  }
  if (!line.strength.trim()) {
    errors.strength = "Enter the strength as written on the pack.";
  }
  if (!resolvedDosageForm(line.form, line.customForm || "").trim()) {
    errors.form = isUnlistedDosageForm(line.form) ? "Write the dosage form." : "Choose a dosage form.";
  }
  const price = Number(line.price);
  if (!Number.isFinite(price) || price < 0) {
    errors.price = "Enter a selling price of 0 or more.";
  }
  return errors;
}

export function draftFromCatalogueItem(row: PharmacyCatalogueItem): PharmacyCatalogueDraft {
  return {
    name: row.name || row.hospitalName || "",
    brandName: row.brandName || "",
    manufacturer: "",
    strength: row.strength || "",
    form: row.form || "Tablet",
    customForm: "",
    price: row.price ? String(row.price.amount) : "100",
    available: row.available,
    conceptUuid: "",
    genericName: row.hospitalName || "",
  };
}

export function catalogueDraftError(draft: PharmacyCatalogueDraft, mode: "add" | "edit" = "add"): string {
  if (draft.name.trim().length < 3) {
    return "Enter the medicine or product name.";
  }
  if (mode === "add" && !draft.conceptUuid.trim()) {
    return "Search and select a generic.";
  }
  if (!draft.strength.trim()) {
    return "Enter the strength as written on the pack.";
  }
  if (!resolvedDosageForm(draft.form, draft.customForm || "").trim()) {
    return isUnlistedDosageForm(draft.form) ? "Write the dosage form." : "Choose a dosage form.";
  }
  const price = Number(draft.price);
  if (!Number.isFinite(price) || price < 0) {
    return "Enter a selling price of 0 or more.";
  }
  return "";
}

export const ADJUST_REASONS = [
  "Incorrect opening stock",
  "Physical stock count",
  "Damaged stock",
  "Expired stock",
  "Lost/missing stock",
  "Correction",
];

export function matchesInventorySearch(row: PharmacyInventoryItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return [row.name, row.hospitalName, row.listedAs, row.brandName, row.strength, row.form].some((value) =>
    (value || "").toLowerCase().includes(needle),
  );
}

export function emptyReceiveDraft(): PharmacyReceiveDraft {
  return {
    quantity: "",
    purchasePrice: "",
    supplier: "",
    reference: "",
    note: "",
  };
}

export function emptyReceiveLine(seed?: PharmacyInventoryItem | null): PharmacyReceiveLineDraft {
  return {
    key: `recv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    drugUuid: seed?.id || "",
    drugName: seed?.name || "",
    strength: seed?.strength || "",
    form: seed?.form || "",
    onHand: seed?.onHand ?? 0,
    sellingPriceLabel: seed?.sellingPrice?.formatted || "",
    quantity: "",
    purchasePrice: "",
    fieldErrors: {},
  };
}

export function receiveLineErrors(
  line: PharmacyReceiveLineDraft,
): PharmacyReceiveLineDraft["fieldErrors"] {
  const errors: PharmacyReceiveLineDraft["fieldErrors"] = {};
  if (!line.drugUuid) {
    errors.drug = "Choose a medicine.";
  }
  const quantity = Number(line.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    errors.quantity = "Enter how many units arrived.";
  }
  const price = Number(line.purchasePrice);
  if (!Number.isFinite(price) || price <= 0) {
    errors.purchasePrice = "Enter the purchase price paid. This is not the selling price.";
  }
  return errors;
}

export function receiveDraftError(draft: PharmacyReceiveDraft): string {
  const quantity = Number(draft.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    return "Enter how many units arrived.";
  }
  const price = Number(draft.purchasePrice);
  if (!Number.isFinite(price) || price <= 0) {
    return "Enter the purchase price paid for this receipt. This is not the selling price.";
  }
  return "";
}

export function emptyAdjustDraft(): PharmacyAdjustDraft {
  return {
    direction: "increase",
    quantity: "",
    reason: "",
    reference: "",
    note: "",
  };
}

export function emptyAdjustLine(seed?: PharmacyInventoryItem | null): PharmacyAdjustLineDraft {
  return {
    key: `adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    drugUuid: seed?.id || "",
    drugName: seed?.name || "",
    strength: seed?.strength || "",
    form: seed?.form || "",
    onHand: seed?.onHand ?? 0,
    reserved: seed?.reserved ?? 0,
    direction: "increase",
    quantity: "",
    reason: "",
    fieldErrors: {},
  };
}

export function adjustLineErrors(
  line: PharmacyAdjustLineDraft,
): PharmacyAdjustLineDraft["fieldErrors"] {
  const errors: PharmacyAdjustLineDraft["fieldErrors"] = {};
  if (!line.drugUuid) {
    errors.drug = "Choose a medicine.";
  }
  if (line.direction !== "increase" && line.direction !== "decrease") {
    errors.direction = "Choose whether to increase or decrease stock.";
  }
  const quantity = Number(line.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    errors.quantity = "Enter how many units to adjust.";
  }
  if (!line.reason.trim()) {
    errors.reason = "Choose why the stock is being adjusted.";
  }
  if (!errors.quantity && line.drugUuid) {
    const resulting = resultingOnHand(line.onHand, line.direction, quantity);
    if (resulting < 0) {
      errors.quantity = "Stock cannot go below zero.";
    } else if (resulting + 0.0001 < line.reserved) {
      errors.quantity = "Some of this medicine is already reserved. Enter a smaller decrease.";
    }
  }
  return errors;
}

export function adjustDraftError(draft: PharmacyAdjustDraft, currentOnHand: number, reserved = 0): string {
  if (draft.direction !== "increase" && draft.direction !== "decrease") {
    return "Choose whether to increase or decrease stock.";
  }
  const quantity = Number(draft.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    return "Enter how many units to adjust.";
  }
  if (!draft.reason.trim()) {
    return "Choose why the stock is being adjusted.";
  }
  const resulting = resultingOnHand(currentOnHand, draft.direction, quantity);
  if (resulting < 0) {
    return "Stock cannot go below zero.";
  }
  if (resulting + 0.0001 < reserved) {
    return "Some of this medicine is already reserved for a prescription. Enter a smaller decrease.";
  }
  return "";
}

export function resultingOnHand(current: number, direction: "increase" | "decrease", quantity: number): number {
  const delta = direction === "increase" ? quantity : -quantity;
  return Number((current + delta).toFixed(4));
}

export function formatStockQty(value: number | null | undefined): string {
  const qty = Number(value);
  if (!Number.isFinite(qty)) {
    return "0";
  }
  return String(qty).replace(/\.0$/, "");
}

export function pharmacyStaffError(reason: unknown, fallback: string): string {
  const code =
    reason && typeof reason === "object" && "code" in reason
      ? String((reason as { code?: string }).code || "")
      : "";
  const message = reason instanceof Error ? reason.message : "";
  if (code === "already_dispensed") {
    return "Already dispensed.";
  }
  if (code === "not_in_pharmacy") {
    return message || "Not in Pharmacy — do not dispense.";
  }
  if (code === "insufficient_stock") {
    return message || "Not enough stock to dispense this medication.";
  }
  if (code === "unpaid") {
    return message || "Payment is still outstanding. Dispensing can continue; settle payment at the cashier when ready.";
  }
  if (code === "partial_not_supported") {
    return (
      message ||
      "Another medicine on this delivery still needs stock. Dispense the ready medicine again, or receive stock for the other medicine first."
    );
  }
  if (code === "dispense_in_progress") {
    return "This prescription is already being dispensed.";
  }
  if (code === "missing_generic") {
    return "This generic is not in the hospital dictionary yet. Search again or create the generic first.";
  }
  if (code === "ambiguous_generic") {
    return "Several generics matched that search. Select the exact generic from the list.";
  }
  if (code === "concept_required" || code === "invalid_concept") {
    return "Search and select a generic. The medicine name is not used to choose the generic.";
  }
  if (code === "invalid_form") {
    return message || "Choose a dosage form, or write the form if it is not listed.";
  }
  if (code === "missing_form") {
    return message || "That dosage form could not be saved. Try again.";
  }
  if (code === "invalid_generic") {
    return "Enter the generic name.";
  }
  if (code === "protected_test") {
    return "The dedicated TEST medicine cannot be changed from this screen.";
  }
  if (code === "sync_timeout") {
    return "The medicine was saved but is not ready at the counter yet. Wait a moment and refresh.";
  }
  if (code === "invalid_quantity") {
    return "Enter a quantity greater than zero.";
  }
  if (code === "invalid_price") {
    return "Enter the purchase price paid for this receipt. This is not the selling price.";
  }
  if (code === "missing_reason") {
    return "Choose why the stock is being adjusted.";
  }
  if (code === "invalid_direction") {
    return "Choose whether to increase or decrease stock.";
  }
  if (code === "stock_reserved") {
    return "Some of this medicine is already reserved for a prescription. Enter a smaller decrease.";
  }
  if (code === "stock_update_failed") {
    return message || "The stock change could not be recorded. Shelf quantity was left unchanged.";
  }
  if (code === "unmapped_product") {
    return "This medicine is not ready for stock yet.";
  }
  return message || fallback;
}

export function matchesPharmacySearch(row: PharmacyPrescription, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return [row.patientName, row.mrn, row.drugName, row.strength, row.orderNumber].some((value) =>
    (value || "").toLowerCase().includes(needle),
  );
}

export interface PharmacyPatientGroup {
  patientUuid: string;
  patientName: string;
  mrn: string;
  lines: PharmacyPrescription[];
}

/** One list row per pharmacy sale / prescription group. */
export interface PharmacyPrescriptionListRow {
  key: string;
  orderUuid: string;
  patientUuid: string;
  patientName: string;
  mrn: string;
  summary: string;
  medicineCount: number;
  paymentStatus: PharmacyPrescription["paymentStatus"];
  lines: PharmacyPrescription[];
}

export function medicineDisplayName(row: PharmacyPrescription): string {
  if (row.strength && !row.drugName.toLowerCase().includes(row.strength.toLowerCase())) {
    return `${row.drugName} · ${row.strength}`;
  }
  return row.drugName || "Medicine";
}

export function truncatePrescriptionLabel(label: string, max = 42): string {
  const text = label.trim();
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

export function prescriptionListSummary(lines: PharmacyPrescription[]): string {
  if (lines.length === 0) {
    return "Prescription";
  }
  const countLabel = lines.length === 1 ? "1 medicine" : `${lines.length} medicines`;
  const names = lines.map((line) => medicineDisplayName(line)).filter(Boolean);
  if (names.length === 0) {
    return countLabel;
  }
  return `${countLabel}: ${names.join(", ")}`;
}

/**
 * Collapse queue lines into one list card per sale (or per order when no sale).
 * List shows patient + truncated order summary; detail holds the medicines.
 */
export function groupPrescriptionsForList(rows: PharmacyPrescription[]): PharmacyPrescriptionListRow[] {
  const groups: PharmacyPrescriptionListRow[] = [];
  const index = new Map<string, PharmacyPrescriptionListRow>();
  for (const row of rows) {
    const key = row.groupKey || row.encounterUuid || row.saleId || row.orderUuid;
    const existing = index.get(key);
    if (existing) {
      existing.lines.push(row);
      existing.summary = prescriptionListSummary(existing.lines);
      existing.medicineCount = existing.lines.length;
      existing.paymentStatus = listPaymentStatus(existing.lines);
      continue;
    }
    const group: PharmacyPrescriptionListRow = {
      key,
      orderUuid: row.orderUuid,
      patientUuid: row.patientUuid,
      patientName: row.patientName,
      mrn: row.mrn,
      summary: prescriptionListSummary([row]),
      medicineCount: 1,
      paymentStatus: listPaymentStatus([row]),
      lines: [row],
    };
    index.set(key, group);
    groups.push(group);
  }
  return groups;
}

function listPaymentStatus(lines: PharmacyPrescription[]): PharmacyPrescription["paymentStatus"] {
  const billed = lines.filter((row) => !row.notInPharmacy && row.paymentStatus !== "NOT BILLED");
  if (billed.length === 0) {
    return "NOT BILLED";
  }
  const statuses = new Set(billed.map((row) => row.paymentStatus));
  if (statuses.has("PARTIALLY PAID") || (statuses.has("PAID") && statuses.has("UNPAID"))) {
    return "PARTIALLY PAID";
  }
  if (statuses.size === 1) {
    return billed[0]?.paymentStatus || "UNPAID";
  }
  return "PARTIALLY PAID";
}

export function groupPrescriptionsByPatient(rows: PharmacyPrescription[]): PharmacyPatientGroup[] {
  const groups: PharmacyPatientGroup[] = [];
  const index = new Map<string, PharmacyPatientGroup>();
  for (const row of rows) {
    const key = row.patientUuid || row.orderUuid;
    const existing = index.get(key);
    if (existing) {
      existing.lines.push(row);
      continue;
    }
    const group: PharmacyPatientGroup = {
      patientUuid: row.patientUuid,
      patientName: row.patientName,
      mrn: row.mrn,
      lines: [row],
    };
    index.set(key, group);
    groups.push(group);
  }
  return groups;
}

export function needsAttention(rows: PharmacyPrescription[]): PharmacyPrescription[] {
  return rows.filter(
    (row) =>
      !row.notInPharmacy &&
      (row.dispensingStatus === "READY TO DISPENSE" ||
        row.dispensingStatus === "UNPAID" ||
        row.paymentStatus === "UNPAID" ||
        row.paymentStatus === "PARTIALLY PAID"),
  );
}

export function isDispensed(row: PharmacyPrescription): boolean {
  return row.dispensingStatus === "DISPENSED";
}

export function isReady(row: PharmacyPrescription): boolean {
  return row.dispensingStatus === "READY TO DISPENSE";
}

export function paymentNeeded(row: PharmacyPrescription): boolean {
  if (row.notInPharmacy || row.paymentStatus === "NOT BILLED") {
    return false;
  }
  return row.paymentStatus === "UNPAID" || row.paymentStatus === "PARTIALLY PAID";
}

export function canDeletePharmacyMedicine(row: PharmacyPrescription): boolean {
  if (
    row.dispensingStatus === "DISPENSED" ||
    row.dispensingStatus === "PARTIALLY DISPENSED" ||
    row.dispensingStatus === "STOPPED"
  ) {
    return false;
  }
  if (row.paymentStatus === "PARTIALLY PAID") {
    return false;
  }
  return true;
}

export function canChangePharmacyMedicine(row: PharmacyPrescription): boolean {
  if (row.notInPharmacy || row.dispensingStatus === "NOT IN PHARMACY") {
    return false;
  }
  if (
    row.dispensingStatus === "DISPENSED" ||
    row.dispensingStatus === "PARTIALLY DISPENSED" ||
    row.dispensingStatus === "STOPPED"
  ) {
    return false;
  }
  if (row.paymentStatus === "PAID" || row.paymentStatus === "PARTIALLY PAID") {
    return false;
  }
  return true;
}

export function medicineNeedsQuantity(row: PharmacyPrescription): boolean {
  if (row.notInPharmacy || row.dispensingStatus === "NOT IN PHARMACY") {
    return false;
  }
  if (row.dispensingStatus === "DISPENSED" || row.dispensingStatus === "STOPPED") {
    return false;
  }
  return row.paymentStatus === "NOT BILLED";
}

export function pharmacyLineStatusLabel(row: PharmacyPrescription): string {
  if (row.notInPharmacy || row.dispensingStatus === "NOT IN PHARMACY") {
    return "Not in Pharmacy — do not dispense";
  }
  if (medicineNeedsQuantity(row)) {
    return "Not billed";
  }
  if (row.dispensingStatus === "DISPENSED") {
    return "Dispensed";
  }
  if (row.dispensingStatus === "PARTIALLY DISPENSED") {
    return "Part dispensed";
  }
  if (row.dispensingStatus === "STOPPED") {
    return "Stopped";
  }
  return "Not dispensed";
}

/** How many medicines on one prescription have already been handed over. */
export function prescriptionDispenseLabel(lines: PharmacyPrescription[]): string | null {
  const active = lines.filter(
    (row) => !row.notInPharmacy && row.dispensingStatus !== "NOT IN PHARMACY" && row.dispensingStatus !== "STOPPED",
  );
  if (active.length === 0) {
    return null;
  }
  const handed = active.filter(
    (row) => row.dispensingStatus === "DISPENSED" || row.dispensingStatus === "PARTIALLY DISPENSED",
  ).length;
  if (handed === 0) {
    return "Not dispensed";
  }
  const full = active.filter((row) => row.dispensingStatus === "DISPENSED").length;
  if (full === active.length) {
    return "Dispensed";
  }
  if (active.length === 1) {
    return "Part dispensed";
  }
  return `${handed} of ${active.length} dispensed`;
}

export function pharmacyLinePaymentLabel(row: PharmacyPrescription): string | null {
  if (row.notInPharmacy || row.paymentStatus === "NOT BILLED") {
    return null;
  }
  return row.paymentStatus;
}

export function listIsNotInPharmacy(lines: PharmacyPrescription[]): boolean {
  return (
    lines.length > 0 &&
    lines.every((row) => Boolean(row.notInPharmacy) || row.dispensingStatus === "NOT IN PHARMACY")
  );
}
